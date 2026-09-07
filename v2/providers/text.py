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

    def strict_request(self, system_prompt: str, user_prompt: str, parameters: dict) -> dict:
        """Research wire payload; deliberately separate from legacy fallback generation."""
        return dict(model=self.model, messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt}],
            temperature=parameters['temperature'], max_tokens=parameters['max_tokens'],
            stream=False, thinking={'type': 'disabled'})

    def generate_strict(self, payload: dict) -> dict:
        """One request, no SDK retry, fallback or old response reuse. Caller journals errors."""
        if not self._api_key:
            raise ValueError('未配置安全文字服务密钥')
        if self.base_url not in ('https://api.deepseek.com', 'https://api.deepseek.com/v1'):
            raise ValueError('研究请求只允许已审核的官方 DeepSeek HTTPS 地址')
        if self._completion_client is not None:
            response = self._completion_client.create(**payload, timeout=self.timeout_seconds)
            return response if isinstance(response, dict) else response.model_dump()
        import json
        import urllib.request
        request = urllib.request.Request(self.base_url + '/chat/completions',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Authorization': 'Bearer ' + self._api_key, 'Content-Type': 'application/json'},
            method='POST')
        # urllib does not retry. Reject redirects so credentials cannot follow another host.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                raise ValueError('文字服务重定向被拒绝')
        with urllib.request.build_opener(NoRedirect).open(request, timeout=self.timeout_seconds) as response:
            return json.load(response)

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
