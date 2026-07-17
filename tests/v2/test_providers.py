from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.providers.images import ExistingImageProvider, ImageGenerationRequest
from v2.providers.text import DeepSeekTextProvider, TextGenerationRequest


class RaisingTextClient:
    def create(self, **kwargs):
        raise TimeoutError("provider timeout with sk-secret-token")


class FakeImageModule:
    @staticmethod
    def generate_ai_image(prompt, output_path, size, reference_path=None, config=None):
        Path(output_path).write_bytes(b"PNG")
        return True


class ProviderTests(unittest.TestCase):
    def test_text_failure_returns_explicit_offline_fallback_without_secret(self) -> None:
        provider = DeepSeekTextProvider(
            api_key="sk-secret-token",
            model="deepseek-chat",
            completion_client=RaisingTextClient(),
        )

        result = provider.generate(
            TextGenerationRequest("system", "user", fallback_text="离线设计方案")
        )

        self.assertEqual(result.mode, "offline_fallback")
        self.assertEqual(result.text, "离线设计方案")
        self.assertNotIn("sk-secret-token", result.warning)

    def test_existing_image_provider_returns_generated_bytes(self) -> None:
        provider = ExistingImageProvider(
            config={"provider": "dashscope", "api_key": "secret", "model": "wan2.7-image-pro"},
            module_loader=lambda: FakeImageModule,
        )

        result = provider.generate(ImageGenerationRequest("产品效果图", "效果图.png", "1024x1024"))

        self.assertTrue(result.succeeded)
        self.assertEqual(result.data, b"PNG")
        self.assertEqual(result.provider, "dashscope")
        self.assertNotIn("secret", repr(result))


if __name__ == "__main__":
    unittest.main()
