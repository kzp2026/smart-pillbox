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
        paths = list(graph.get("used_graph_paths") or []) if graph.get("evidence_status") == "已审核图谱证据" else []
        if verified_graph_snapshot is not None and (graph.get("approved_mapping_count") != len({p.get('mapping_id') for p in paths}) or not paths):
            raise ValueError("正式图谱必须包含经实验审核并可追溯的映射路径。")
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
        graph_label = "已审核正式图谱" if paths else "候选设计推导（无正式图谱证据）"
        system_prompt = (
                    "你是工业设计研究专家。必须保留输入中的评论证据、需求—功能—结构关系，"
                    "输出可执行的中文产品设计方案，不得编造不存在的用户证据。"
                )
        user_prompt = (
                    f"目标产品：{command.target_product}\n需求：{command.demand_text}\n"
                    f"证据上下文：{json.dumps(to_json_safe(context), ensure_ascii=False)}\n"
                    f"{graph_label}：{json.dumps(to_json_safe(graph), ensure_ascii=False)}\n"
                    f"离线方案草稿：\n{package.get('design_text', '')}"
                )
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
