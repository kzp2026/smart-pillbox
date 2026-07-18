from __future__ import annotations


def public_error_message(
    context: str,
    _exception: BaseException,
    *,
    guidance: str = "请检查管理应用中的服务配置后重试。",
) -> str:
    """Return an actionable UI message without exposing exception details."""

    return f"{context.rstrip('：:。.')}。{guidance}"
