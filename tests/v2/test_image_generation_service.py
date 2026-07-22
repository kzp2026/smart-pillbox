from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.image_generation import ImageGenerationService
from v2.domain.models import CreateRunCommand
from v2.providers.images import ImageResult


class FakeImageProvider:
    def __init__(self) -> None:
        self.requests = []

    def generate(self, request):
        self.requests.append(request)
        if "fail" in request.prompt:
            return ImageResult(False, b"", "image/png", "fake", "model", "模拟失败")
        return ImageResult(True, b"png-bytes", "image/png", "fake", "model")


class ImageGenerationServiceTests(unittest.TestCase):
    def test_generates_selected_assets_and_persists_partial_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "owner")
            repo.initialize()
            store = LocalArtifactStore(root / "artifacts")
            run = repo.create_pipeline_run(
                CreateRunCommand("智能药盒", "更清晰的提醒", "fake", "model", 3),
                "image-service-test",
            )
            provider = FakeImageProvider()
            service = ImageGenerationService(repo, store, provider)

            result = service.generate(
                run.id,
                [
                    {"key": "hero", "label": "主效果图", "prompt": "hero prompt"},
                    {"key": "broken", "label": "失败图", "prompt": "fail prompt"},
                    {"key": "detail", "label": "细节图", "prompt": "detail prompt"},
                    {"key": "ignored", "label": "忽略", "prompt": "ignored prompt"},
                ],
                count=3,
            )

            self.assertEqual(result.requested_count, 3)
            self.assertEqual(result.succeeded_count, 2)
            self.assertEqual(len(result.failures), 1)
            self.assertEqual(len(provider.requests), 3)
            self.assertEqual(len(repo.list_artifacts_for_run(run.id)), 2)

    def test_reports_progress_after_each_image_attempt(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "owner")
            repo.initialize()
            run = repo.create_pipeline_run(
                CreateRunCommand("智能药盒", "更清晰的提醒", "fake", "model", 2),
                "image-progress-test",
            )
            progress = []

            ImageGenerationService(repo, LocalArtifactStore(root / "artifacts"), FakeImageProvider()).generate(
                run.id,
                [
                    {"key": "hero", "label": "主效果图", "prompt": "hero prompt"},
                    {"key": "detail", "label": "细节图", "prompt": "detail prompt"},
                ],
                count=2,
                on_progress=lambda completed, total, label, succeeded: progress.append(
                    (completed, total, label, succeeded)
                ),
            )

            self.assertEqual(progress, [(1, 2, "主效果图", True), (2, 2, "细节图", True)])


if __name__ == "__main__":
    unittest.main()
