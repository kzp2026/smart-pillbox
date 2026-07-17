from __future__ import annotations

import unittest

from v2.config import AppConfig, ConfigError


class AppConfigTests(unittest.TestCase):
    def test_required_secrets_build_private_v2_config(self) -> None:
        config = AppConfig.from_mapping(
            {
                "V2_USERNAME": "owner",
                "V2_PASSWORD_HASH": "scrypt$encoded",
                "V2_DATABASE_URL": "postgresql://example.invalid/postgres",
                "V2_STORAGE_URL": "https://project.supabase.co/storage/v1",
                "V2_STORAGE_SERVICE_KEY": "service-secret",
            }
        )

        self.assertEqual(config.username, "owner")
        self.assertEqual(config.schema, "agent_v2")
        self.assertEqual(config.storage_bucket, "agent-v2-private")
        self.assertEqual(config.session_idle_seconds, 8 * 60 * 60)

    def test_optional_provider_and_migration_settings_are_loaded(self) -> None:
        config = AppConfig.from_mapping(
            {
                "V2_USERNAME": "owner",
                "V2_PASSWORD_HASH": "scrypt$encoded",
                "V2_DATABASE_URL": "sqlite:///private.sqlite3",
                "V2_LEGACY_DATABASE_URL": "sqlite:///legacy.sqlite3",
                "V2_LEGACY_OUTPUT_ROOTS": "output;legacy-output",
                "V2_DEEPSEEK_API_KEY": "deepseek-secret",
                "V2_DEEPSEEK_MODEL": "deepseek-chat",
                "V2_IMAGE_PROVIDER": "dashscope",
                "V2_IMAGE_MODEL": "wan2.7-image-pro",
                "V2_IMAGE_API_KEY": "image-secret",
            }
        )

        self.assertEqual(config.legacy_database_url, "sqlite:///legacy.sqlite3")
        self.assertEqual(config.legacy_output_roots, ("output", "legacy-output"))
        self.assertEqual(config.deepseek_model, "deepseek-chat")
        self.assertEqual(config.image_provider, "dashscope")
        self.assertEqual(config.image_model, "wan2.7-image-pro")

    def test_missing_required_secret_names_field_without_leaking_values(self) -> None:
        with self.assertRaises(ConfigError) as caught:
            AppConfig.from_mapping(
                {
                    "V2_USERNAME": "owner",
                    "V2_PASSWORD_HASH": "top-secret-hash",
                    "V2_DATABASE_URL": "",
                }
            )

        message = str(caught.exception)
        self.assertIn("V2_DATABASE_URL", message)
        self.assertNotIn("top-secret-hash", message)

    def test_schema_name_must_be_a_safe_identifier(self) -> None:
        with self.assertRaises(ConfigError):
            AppConfig.from_mapping(
                {
                    "V2_USERNAME": "owner",
                    "V2_PASSWORD_HASH": "hash",
                    "V2_DATABASE_URL": "sqlite:///v2.sqlite3",
                    "V2_SCHEMA": "agent_v2; drop schema public",
                }
            )


if __name__ == "__main__":
    unittest.main()
