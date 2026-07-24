from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.application.generation import ConfirmationRequired, GenerationCommand, GenerationService
from v2.providers.text import TextResult


class LiveTextProvider:
    def generate(self, request):
        return TextResult("DeepSeek 增强后的完整设计方案", "live", "deepseek", "deepseek-chat")


class GenerationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo = KnowledgeRepository(
            f"sqlite:///{Path(self.temp_dir.name) / 'v2.sqlite3'}", "private-owner"
        )
        self.repo.initialize()
        self.service = GenerationService(self.repo, confirmation_secret=b"test-confirmation-secret")
        self.command = GenerationCommand(
            target_product="智能药盒",
            demand_text="提醒老人按时吃药",
            provider="dashscope",
            model="wan2.7-image-pro",
            image_count=8,
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_paid_images_require_exact_confirmation(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        with self.assertRaises(ConfirmationRequired):
            self.service.confirm_and_start(self.command, preview, provided_token="wrong")

    def test_valid_confirmation_creates_one_idempotent_run(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        first = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)
        second = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)

        self.assertEqual(first.id, second.id)
        self.assertEqual(self.repo.count_rows("pipeline_runs"), 1)

    def test_preview_exposes_model_count_and_no_secret(self) -> None:
        preview = self.service.preview(self.command, nonce="nonce-1")

        self.assertEqual(preview.provider, "dashscope")
        self.assertEqual(preview.model, "wan2.7-image-pro")
        self.assertEqual(preview.image_count, 8)
        self.assertNotIn("test-confirmation-secret", repr(preview))

    def test_design_generation_uses_private_evidence_and_persists_text_mode(self) -> None:
        imported = self.repo.ingest_comments(
            "智能药盒", "适老健康", "comments.csv", ["提醒声音太小，老人听不清"]
        )
        self.repo.add_requirement_once(
            imported.product_id,
            imported.batch_id,
            "提醒反馈",
            "提醒要明显",
            ["提醒"],
            "提醒声音太小，老人听不清",
            80,
        )
        preview = self.service.preview(self.command, nonce="design-run")
        run = self.service.confirm_and_start(self.command, preview, preview.confirmation_token)

        generated = self.service.generate_design(run.id, self.command, {}, LiveTextProvider())

        self.assertEqual(generated.package["design_text"], "DeepSeek 增强后的完整设计方案")
        self.assertEqual(generated.package["text_generation_mode"], "live")
        self.assertGreater(generated.context["evidence_count"], 0)
        graph = generated.package["requirement_function_structure_graph"]
        self.assertTrue(graph["requirements"])
        self.assertTrue(graph["functions"])
        self.assertTrue(graph["structures"])
        self.assertTrue(graph["links"])
        self.assertIsNotNone(self.repo.get_generation_run(run.id))


if __name__ == "__main__":
    unittest.main()
