from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from typing import Mapping, Protocol

from v2.adapters.postgres import KnowledgeRepository
from v2.domain.models import CreateRunCommand, PipelineRun
from v2.providers.text import TextGenerationRequest, TextResult


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
    _SEMANTIC_GRAPH_VERSION = "semantic-v2"
    _GRAPH_RULES = (
        (
            ("提醒", "反馈", "闹铃", "定时", "服药", "提示", "通知"),
            "多模态定时提醒与服药确认反馈",
            "高对比显示屏、扬声器、LED 指示灯与确认按键",
        ),
        (
            ("操作", "便利", "易用", "适老", "按键", "交互"),
            "一键操作与清晰状态引导",
            "大尺寸实体按键、倾斜操作面板与图文标识",
        ),
        (
            ("容量", "收纳", "分格", "药仓", "储物"),
            "按时段分格收纳与取用引导",
            "可拆卸分格药仓、透明翻盖与时段标签",
        ),
        (
            ("外观", "质感", "美观", "造型", "cmf", "颜色"),
            "情感化外观与耐用 CMF 设计",
            "圆角一体化外壳、哑光 ABS/PC 与软触包胶细节",
        ),
        (
            ("防潮", "密封", "受潮", "干燥", "防水"),
            "防潮密封与药品状态保护",
            "硅胶密封圈、密闭翻盖与独立干燥剂仓",
        ),
        (
            ("便携", "体积", "轻便", "携带", "旅行"),
            "轻量化携带与外出使用支持",
            "紧凑机身、圆角握持边缘与便携固定结构",
        ),
        (
            ("清洁", "卫生", "拆洗", "污渍"),
            "易拆洗与卫生维护",
            "可拆卸内胆、圆角无死角药仓与易擦拭表面",
        ),
        (
            ("远程", "连接", "同步", "app", "联网"),
            "远程状态同步与异常提醒",
            "无线通信模块区、配网按键与连接状态指示灯",
        ),
        (
            ("安全", "误服", "儿童锁", "上锁", "防误触"),
            "防误触与安全取用控制",
            "独立取药口、儿童锁结构与权限确认组件",
        ),
    )

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
    ) -> GeneratedDesign:
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
        package["requirement_function_structure_graph"] = self.build_graph_snapshot(
            command.demand_text,
            context,
            industrial_constraints,
        )
        text_result = text_provider.generate(
            TextGenerationRequest(
                system_prompt=(
                    "你是工业设计研究专家。必须保留输入中的评论证据、需求—功能—结构关系，"
                    "输出可执行的中文产品设计方案，不得编造不存在的用户证据。"
                ),
                user_prompt=(
                    f"目标产品：{command.target_product}\n需求：{command.demand_text}\n"
                    f"证据上下文：{json.dumps(to_json_safe(context), ensure_ascii=False)}\n"
                    f"离线方案草稿：\n{package.get('design_text', '')}"
                ),
                fallback_text=str(package.get("design_text") or ""),
            )
        )
        package["design_text"] = text_result.text
        package["text_generation_mode"] = text_result.mode
        package["text_provider"] = text_result.provider
        package["text_model"] = text_result.model
        package["text_warning"] = text_result.warning
        safe_context = to_json_safe(context)
        safe_package = to_json_safe(package)
        self.repository.save_generation_run(
            run_id,
            json.dumps(safe_context, ensure_ascii=False, default=str),
            json.dumps(safe_package, ensure_ascii=False, default=str),
            float(package.get("quality_score") or 0),
            str(package.get("quality_status") or ""),
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

        requirements = list(requirements_by_key.values())
        if not requirements:
            requirements = GenerationService._requirements_from_demand(demand_text)

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
        if value.get("version") != GenerationService._SEMANTIC_GRAPH_VERSION:
            return False
        return all(isinstance(value.get(key), list) for key in ("requirements", "functions", "structures", "links"))

    @staticmethod
    def _requirements_from_demand(demand_text: str) -> list[dict[str, str]]:
        demand = demand_text.strip()
        derived: list[dict[str, str]] = []
        for keywords, label, _structure in GenerationService._GRAPH_RULES:
            if any(keyword.lower() in demand.lower() for keyword in keywords):
                derived.append({"name": label, "detail": demand or label})
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
        title = name.lower()
        for keywords, function, structure in GenerationService._GRAPH_RULES:
            if any(keyword.lower() in title for keyword in keywords):
                return function, structure, "需求语义推导"

        detail_text = detail.lower()
        for keywords, function, structure in GenerationService._GRAPH_RULES:
            if any(keyword.lower() in detail_text for keyword in keywords):
                return function, structure, "需求语义推导"

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
