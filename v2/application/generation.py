from __future__ import annotations

import hashlib
import hmac
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from v2.adapters.postgres import KnowledgeRepository
from v2.domain.models import CreateRunCommand, PipelineRun
from v2.providers.text import TextGenerationRequest, TextResult
from v2.application.visual_quality import qualify_visual_delivery
from experiment.pipeline.semantics import derive_requirements, semantic_mapping


class ConfirmationRequired(ValueError):
    """Raised when a paid generation request is not exactly confirmed."""


@dataclass(frozen=True)
class GenerationCommand:
    target_product: str
    demand_text: str
    provider: str
    model: str
    image_count: int = 8


@dataclass(frozen=True)
class GenerationPreview:
    provider: str
    model: str
    image_count: int
    nonce: str
    confirmation_token: str
    explanation: str


@dataclass(frozen=True)
class GeneratedDesign:
    run: PipelineRun
    context: dict
    package: dict


class TextProvider(Protocol):
    def generate(self, request: TextGenerationRequest) -> TextResult: ...


class GenerationService:
    _SEMANTIC_GRAPH_VERSION = "rfs-candidate-v2"
    _REVIEWED_GRAPH_EVIDENCE_STATUSES = frozenset(("已审核图谱证据", "研究者确认关系证据"))

    def __init__(self, repository: KnowledgeRepository, confirmation_secret: bytes) -> None:
        if len(confirmation_secret) < 16:
            raise ValueError("确认密钥长度不足。")
        self.repository = repository
        self._confirmation_secret = confirmation_secret

    def preview(self, command: GenerationCommand, nonce: str) -> GenerationPreview:
        canonical = self._canonical(command, nonce)
        token = hmac.new(self._confirmation_secret, canonical, hashlib.sha256).hexdigest()
        return GenerationPreview(
            provider=command.provider,
            model=command.model,
            image_count=max(0, int(command.image_count)),
            nonce=nonce,
            confirmation_token=token,
            explanation=(
                f"将使用 {command.provider} / {command.model} 生成 {max(0, int(command.image_count))} 张图片。"
                "图片接口可能按成功生成数量计费。"
            ),
        )

    def confirm_and_start(
        self,
        command: GenerationCommand,
        preview: GenerationPreview,
        provided_token: str | None,
    ) -> PipelineRun:
        expected = self.preview(command, preview.nonce)
        if command.image_count > 0 and not hmac.compare_digest(
            str(provided_token or ""), expected.confirmation_token
        ):
            raise ConfirmationRequired("请确认本次模型、数量和可能产生的费用。")
        idempotency_key = hashlib.sha256(
            f"generation:{expected.confirmation_token}".encode("ascii")
        ).hexdigest()
        return self.repository.create_pipeline_run(
            CreateRunCommand(
                target_product=command.target_product,
                demand_text=command.demand_text,
                provider=command.provider,
                model=command.model,
                image_count=command.image_count,
            ),
            idempotency_key=idempotency_key,
        )

    def generate_design(
        self,
        run_id: str,
        command: GenerationCommand,
        industrial_constraints: Mapping[str, object],
        text_provider: TextProvider,
        verified_graph_snapshot: Mapping[str, object] | None = None,
    ) -> GeneratedDesign:
        # Streamlit launches `v2/app.py` with `v2/` as the script directory.
        # Resolve the repository root explicitly so the shared generator remains
        # available both from the V2 entry point and from package-based tests.
        project_root = str(Path(__file__).resolve().parents[2])
        if project_root not in sys.path:
            sys.path.insert(0, project_root)
        from scripts.product_knowledge_base import generate_design_package, to_json_safe

        context = self.repository.search_context(
            f"{command.target_product} {command.demand_text}", limit=8
        )
        context["industrial_constraints"] = dict(industrial_constraints)
        package = generate_design_package(
            command.target_product,
            command.demand_text,
            context,
            industrial_constraints=dict(industrial_constraints),
        )
        visual_assets, visual_quality_gate = qualify_visual_delivery(
            command.target_product,
            list(package.get("visual_assets") or []),
            industrial_constraints,
        )
        package["visual_assets"] = visual_assets
        package["image_prompts"] = [str(asset.get("prompt") or "") for asset in visual_assets]
        package["image_prompt_text"] = package["image_prompts"][0] if visual_assets else ""
        package["visual_quality_gate"] = visual_quality_gate
        graph = dict(verified_graph_snapshot) if verified_graph_snapshot is not None else self.build_graph_snapshot(
            command.demand_text,
            context,
            industrial_constraints,
        )
        package["requirement_function_structure_graph"] = graph
        evidence_status = str(graph.get("evidence_status") or "")
        paths = list(graph.get("used_graph_paths") or []) if evidence_status in self._REVIEWED_GRAPH_EVIDENCE_STATUSES else []
        if verified_graph_snapshot is not None and (graph.get("approved_mapping_count") != len({p.get('mapping_id') for p in paths}) or not paths):
            raise ValueError("传入的审核关系必须包含可追溯的映射路径。")
        context.update(semantic_catalog_version="paper-repro-v2.0", actual_algorithm="not_clustered",
                       evidence_count=len(context.get("comments") or context.get("requirements") or []),
                       approved_mapping_count=int(graph.get("approved_mapping_count") or 0), generation_mode="pending",
                       independent_evaluation_completed=False, closed_loop_validated=False,
                       used_graph_paths=paths)
        package.update(semantic_catalog_version=context["semantic_catalog_version"],
                       actual_algorithm=context["actual_algorithm"],
                       evidence_count=context["evidence_count"], approved_mapping_count=context["approved_mapping_count"],
                       generation_mode="pending",
                       independent_evaluation_completed=False, closed_loop_validated=False,
                       used_graph_paths=paths,
                       graph_evidence_status=graph.get("evidence_status", "无正式图谱证据"))
        graph_label = (
            "研究者确认关系证据"
            if evidence_status == "研究者确认关系证据" and paths
            else "已审核正式图谱"
            if paths
            else "候选设计推导（无正式图谱证据）"
        )
        system_prompt = (
            "你是工业设计研究专家。必须保留输入中的评论证据编号和需求—功能—结构关系，"
            "输出可执行的中文概念方案。不得将候选关系、概念功能或用户确认事件写成已实现、已验证的产品事实。"
        )
        text_input = self._build_bounded_text_input(command, context, graph, industrial_constraints, graph_label)
        user_prompt = json.dumps(text_input, ensure_ascii=False, separators=(",", ":"))
        context["text_input_budget"] = {
            "max_characters": 12_000,
            "actual_characters": len(user_prompt),
            "comment_limit": len(text_input["评论来源标识"]),
            "requirement_limit": len(text_input["候选需求"]),
            "retrieval": "关键词得分排序，保留编号、批次与排序得分，不含评论正文",
        }
        text_result = text_provider.generate(
            TextGenerationRequest(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                fallback_text=str(package.get("design_text") or ""),
            )
        )
        package["design_text"] = text_result.text
        package["text_generation_mode"] = text_result.mode
        package["text_provider"] = text_result.provider
        package["text_model"] = text_result.model
        package["text_warning"] = text_result.warning
        context["generation_mode"] = text_result.mode
        package["generation_mode"] = text_result.mode
        package["text_generation_prompt"] = {"system_prompt": system_prompt, "user_prompt": user_prompt}
        package["text_input_budget"] = context["text_input_budget"]
        package["used_graph_path_ids"] = [str(path.get("path_id") or "") for path in paths]
        safe_context = to_json_safe(context)
        safe_package = to_json_safe(package)
        self.repository.save_generation_run(
            run_id,
            json.dumps(safe_context, ensure_ascii=False, default=str),
            json.dumps(safe_package, ensure_ascii=False, default=str),
            float(package.get("quality_score") or 0),
            "artifact_completeness_only",
        )
        return GeneratedDesign(
            run=self.repository.get_pipeline_run(run_id),
            context=safe_context,
            package=safe_package,
        )

    @staticmethod
    def _build_bounded_text_input(
        command: GenerationCommand,
        context: Mapping[str, object],
        graph: Mapping[str, object],
        industrial_constraints: Mapping[str, object],
        graph_label: str,
    ) -> dict[str, object]:
        """Keep model input auditable without serialising an entire comment database."""

        def clip(value: object, maximum: int) -> str:
            text = str(value or "").strip()
            return text if len(text) <= maximum else f"{text[:maximum - 1]}…"

        comments = []
        for item in list(context.get("comments") or [])[:8]:
            if not isinstance(item, Mapping):
                continue
            comments.append(
                {
                    "评论编号": str(item.get("id") or "未记录"),
                    "来源批次": str(item.get("batch_id") or "未记录"),
                    "检索得分": item.get("score") if item.get("score") is not None else "未记录",
                }
            )
        requirements = []
        for item in list(context.get("requirements") or [])[:8]:
            if not isinstance(item, Mapping):
                continue
            requirements.append(
                {
                    "需求编号": str(item.get("id") or "未记录"),
                    "需求名称": clip(item.get("title"), 100),
                    "触发词": clip(item.get("keywords"), 180),
                    "检索得分": item.get("score") if item.get("score") is not None else "未记录",
                }
            )
        links = []
        for item in list(graph.get("links") or [])[:8]:
            if not isinstance(item, Mapping):
                continue
            links.append(
                {
                    "映射编号": str(item.get("mapping_id") or "未记录"),
                    "需求": clip(item.get("requirement"), 100),
                    "功能候选": clip(item.get("function"), 180),
                    "结构候选": clip(item.get("structure"), 180),
                    "评论证据编号": list(item.get("comment_ids") or []),
                    "审核状态": str(item.get("review_status") or graph.get("review_status") or "未记录"),
                }
            )
        constraints = {
            str(key): clip(value, 240)
            for key, value in industrial_constraints.items()
            if str(key).strip() and str(value or "").strip()
        }
        return {
            "任务": {
                "产品": command.target_product,
                "设计目标": command.demand_text,
                "输出要求": "输出概念方案，逐项标注评论证据编号。服药确认只能描述为用户确认事件。",
            },
            "检索说明": {
                "方式": "普通关系表与评论表的关键词得分排序，不是图数据库检索",
                "返回数量": {"评论": len(comments), "候选需求": len(requirements), "关系": len(links)},
                "图谱状态": graph_label,
                "已审核图谱路径": list(graph.get("used_graph_paths") or []),
            },
            "评论来源标识": comments,
            "候选需求": requirements,
            "需求功能结构候选": links,
            "设计约束": constraints,
        }

    @staticmethod
    def build_graph_snapshot(
        demand_text: str,
        context: Mapping[str, object],
        industrial_constraints: Mapping[str, object],
    ) -> dict[str, object]:
        """Build a de-duplicated, requirement-specific design graph."""

        requirements_by_key: dict[str, dict[str, str]] = {}
        for item in list(context.get("requirements") or []):
            if not isinstance(item, Mapping):
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            detail = str(item.get("description") or item.get("evidence_text") or "").strip()
            if not title:
                continue
            key = GenerationService._normalize_graph_term(title)
            existing = requirements_by_key.get(key)
            if existing is None:
                requirements_by_key[key] = {"name": title, "detail": detail or title}
            elif detail and detail not in existing["detail"]:
                existing["detail"] = f"{existing['detail']}；{detail}"[:500]

        requirements = list(requirements_by_key.values()) or GenerationService._requirements_from_demand(demand_text)

        links: list[dict[str, str]] = []
        function_sources: dict[str, str] = {}
        structure_sources: dict[str, str] = {}
        for requirement in requirements:
            function, structure, source = GenerationService._semantic_graph_mapping(
                requirement["name"], requirement["detail"], industrial_constraints
            )
            function_sources.setdefault(function, source)
            structure_sources.setdefault(structure, source)
            links.append(
                {
                    "requirement": requirement["name"],
                    "function": function,
                    "structure": structure,
                    "evidence": requirement["detail"],
                }
            )

        return {
            "version": GenerationService._SEMANTIC_GRAPH_VERSION,
            "review_status": "pending_review",
            "approved_mapping_count": 0,
            "used_graph_paths": [],
            "requirements": requirements,
            "functions": [
                {"name": name, "source": source}
                for name, source in function_sources.items()
            ],
            "structures": [
                {"name": name, "source": source}
                for name, source in structure_sources.items()
            ],
            "links": links,
        }

    @staticmethod
    def _build_graph_snapshot(
        demand_text: str,
        context: Mapping[str, object],
        industrial_constraints: Mapping[str, object],
    ) -> dict[str, object]:
        """Backward-compatible alias for callers from earlier V2 releases."""
        return GenerationService.build_graph_snapshot(demand_text, context, industrial_constraints)

    @staticmethod
    def is_semantic_graph_snapshot(value: object) -> bool:
        if not isinstance(value, Mapping):
            return False
        if value.get("version") not in (GenerationService._SEMANTIC_GRAPH_VERSION, "semantic-v2"):
            return False
        return all(isinstance(value.get(key), list) for key in ("requirements", "functions", "structures", "links"))

    @staticmethod
    def _requirements_from_demand(demand_text: str) -> list[dict[str, str]]:
        demand = demand_text.strip()
        derived: list[dict[str, str]] = []
        records = [{"comment_id": "demand-1", "cleaned_comment": demand}]
        for item in derive_requirements(records):
            if item["review_status"] != "needs_naming":
                derived.append({"name": item["requirement_name"], "detail": demand or item["requirement_name"]})
        return derived or [{"name": "本次设计需求", "detail": demand or "待补充设计需求"}]

    @staticmethod
    def _semantic_graph_mapping(
        name: str,
        detail: str,
        industrial_constraints: Mapping[str, object],
    ) -> tuple[str, str, str]:
        # A derived requirement's evidence can mention several concerns.  Match
        # its explicit requirement title first, otherwise every row would be
        # captured by the first keyword occurring in the shared evidence text.
        function, structure, source = semantic_mapping(name, detail)
        if "缺少可判定语义" not in source:
            return function, structure, source

        product_type = str(industrial_constraints.get("product_type") or "").strip()
        prefix = f"{product_type}的" if product_type else ""
        return (
            f"实现“{name}”的可验证交互与服务功能",
            f"承载“{name}”的{prefix}独立组件与连接界面",
            "需求语义推导",
        )

    @staticmethod
    def _normalize_graph_term(value: str) -> str:
        return "".join(character for character in value.lower().strip() if character.isalnum())

    @staticmethod
    def _split_graph_terms(value: object) -> list[str]:
        raw = str(value or "").replace("\n", "、")
        for delimiter in ("；", ";", "，", ",", "。", "、", "/"):
            raw = raw.replace(delimiter, "|")
        seen: set[str] = set()
        values: list[str] = []
        for item in raw.split("|"):
            clean = item.strip(" -：:")
            if clean and clean not in seen:
                seen.add(clean)
                values.append(clean)
        return values[:6]

    @staticmethod
    def _canonical(command: GenerationCommand, nonce: str) -> bytes:
        return json.dumps(
            {
                "target_product": command.target_product.strip(),
                "demand_text": command.demand_text.strip(),
                "provider": command.provider.strip(),
                "model": command.model.strip(),
                "image_count": max(0, int(command.image_count)),
                "nonce": nonce,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
