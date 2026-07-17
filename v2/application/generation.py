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
