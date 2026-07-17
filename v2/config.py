from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping


_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class ConfigError(ValueError):
    """Raised when required V2 server configuration is unavailable."""


@dataclass(frozen=True)
class AppConfig:
    username: str
    password_hash: str
    database_url: str
    schema: str = "agent_v2"
    storage_url: str = ""
    storage_service_key: str = ""
    storage_bucket: str = "agent-v2-private"
    owner_id: str = "private-owner"
    legacy_database_url: str = ""
    legacy_output_roots: tuple[str, ...] = ()
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com"
    image_provider: str = "dashscope"
    image_model: str = "wan2.7-image-pro"
    image_api_key: str = ""
    image_base_url: str = ""
    session_idle_seconds: int = 8 * 60 * 60
    login_max_failures: int = 5
    login_cooldown_seconds: int = 15 * 60

    @classmethod
    def from_mapping(cls, values: Mapping[str, object]) -> "AppConfig":
        def read(name: str, default: str = "") -> str:
            return str(values.get(name, default) or "").strip()

        required = ("V2_USERNAME", "V2_PASSWORD_HASH", "V2_DATABASE_URL")
        missing = [name for name in required if not read(name)]
        if missing:
            raise ConfigError(f"缺少 V2 服务配置：{', '.join(missing)}")

        schema = read("V2_SCHEMA", "agent_v2")
        if not _IDENTIFIER.fullmatch(schema):
            raise ConfigError("V2_SCHEMA 必须是安全的 PostgreSQL 标识符。")

        legacy_output_roots = tuple(
            item.strip()
            for item in re.split(r"[;\n]", read("V2_LEGACY_OUTPUT_ROOTS"))
            if item.strip()
        )

        return cls(
            username=read("V2_USERNAME"),
            password_hash=read("V2_PASSWORD_HASH"),
            database_url=read("V2_DATABASE_URL"),
            schema=schema,
            storage_url=read("V2_STORAGE_URL"),
            storage_service_key=read("V2_STORAGE_SERVICE_KEY"),
            storage_bucket=read("V2_STORAGE_BUCKET", "agent-v2-private"),
            owner_id=read("V2_OWNER_ID", "private-owner"),
            legacy_database_url=read("V2_LEGACY_DATABASE_URL"),
            legacy_output_roots=legacy_output_roots,
            deepseek_api_key=read("V2_DEEPSEEK_API_KEY"),
            deepseek_model=read("V2_DEEPSEEK_MODEL", "deepseek-chat"),
            deepseek_base_url=read("V2_DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            image_provider=read("V2_IMAGE_PROVIDER", "dashscope"),
            image_model=read("V2_IMAGE_MODEL", "wan2.7-image-pro"),
            image_api_key=read("V2_IMAGE_API_KEY"),
            image_base_url=read("V2_IMAGE_BASE_URL"),
        )
