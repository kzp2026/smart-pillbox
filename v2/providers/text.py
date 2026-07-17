from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TextGenerationRequest:
    system_prompt: str
    user_prompt: str
    fallback_text: str


@dataclass(frozen=True)
class TextResult:
    text: str
    mode: str
    provider: str
    model: str
    warning: str = ""


class CompletionClient(Protocol):
    def create(self, **kwargs): ...


class DeepSeekTextProvider:
    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        completion_client: CompletionClient | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self._api_key = api_key.strip()
        self.model = model.strip() or "deepseek-chat"
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(1, int(timeout_seconds))
        self._completion_client = completion_client

    def generate(self, request: TextGenerationRequest) -> TextResult:
        if not self._api_key:
            return TextResult(
                request.fallback_text,
                "offline_fallback",
                "offline",
                "rules",
                "未配置 DeepSeek，当前结果由离线模板生成。",
            )
        try:
            client = self._completion_client or self._build_client()
            response = client.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": request.system_prompt},
                    {"role": "user", "content": request.user_prompt},
                ],
                temperature=0.35,
                timeout=self.timeout_seconds,
            )
            text = self._extract_text(response)
            if not text:
                raise ValueError("文本模型返回空内容。")
            return TextResult(text, "live", "deepseek", self.model)
        except Exception as exc:
            return TextResult(
                request.fallback_text,
                "offline_fallback",
                "offline",
                "rules",
                f"DeepSeek 调用失败，已使用离线模板：{self._redact(str(exc))[:300]}",
            )

    def _build_client(self) -> CompletionClient:
        from openai import OpenAI

        return OpenAI(api_key=self._api_key, base_url=self.base_url).chat.completions

    @staticmethod
    def _extract_text(response: object) -> str:
        if isinstance(response, dict):
            return str(response.get("choices", [{}])[0].get("message", {}).get("content", "")).strip()
        choices = getattr(response, "choices", [])
        if not choices:
            return ""
        return str(getattr(getattr(choices[0], "message", None), "content", "") or "").strip()

    def _redact(self, message: str) -> str:
        redacted = message.replace(self._api_key, "[REDACTED]") if self._api_key else message
        return re.sub(r"sk-[A-Za-z0-9_-]{6,}", "[REDACTED]", redacted)
