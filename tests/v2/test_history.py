from __future__ import annotations

import json
import inspect
import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.history import HistoryService
from v2.domain.models import ArtifactKind, CreateRunCommand


class HistoryServiceTests(unittest.TestCase):
    def test_product_filter_remains_compatible_with_repository_cached_before_deploy(self) -> None:
        class CachedRepository:
            def list_pipeline_runs(self, limit: int = 50):
                return [
                    type("Run", (), {"target_product": "A"})(),
                    type("Run", (), {"target_product": "B"})(),
                ][:limit]

        service = HistoryService(CachedRepository(), object())  # type: ignore[arg-type]
        try:
            runs = service.list_runs(target_product="A")
        except TypeError:
            runs = None

        self.assertIsNotNone(runs)
        self.assertEqual([run.target_product for run in runs or []], ["A"])

    def test_history_api_supports_current_product_isolation(self) -> None:
        parameters = inspect.signature(HistoryService.list_runs).parameters

        self.assertIn("target_product", parameters)

    def test_history_only_returns_runs_for_the_current_product(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "private-owner")
            repo.initialize()
            store = LocalArtifactStore(root / "storage")
            repo.create_pipeline_run(CreateRunCommand("A", "A-1", "offline", "rules", 0), "a-1")
            repo.create_pipeline_run(CreateRunCommand("B", "B-1", "offline", "rules", 0), "b-1")
            repo.create_pipeline_run(CreateRunCommand("A", "A-2", "offline", "rules", 0), "a-2")

            runs = HistoryService(repo, store).list_runs(target_product="A")

            self.assertEqual([run.target_product for run in runs], ["A", "A"])

    def test_reopen_batches_only_requested_artifact_bytes(self) -> None:
        self.assertIn("data_mime_prefixes", inspect.signature(HistoryService.reopen).parameters)

        class BatchStore:
            def __init__(self) -> None:
                self.data: dict[str, bytes] = {}
                self.read_calls = 0
                self.read_many_calls = 0

            def read(self, path: str) -> bytes:
                self.read_calls += 1
                return self.data[path]

            def read_many(self, paths):
                self.read_many_calls += 1
                return {path: self.data[path] for path in paths}

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "private-owner")
            repo.initialize()
            store = BatchStore()
            run = repo.create_pipeline_run(
                CreateRunCommand("A", "render", "dashscope", "wan2.7-image-pro", 2),
                "batch-artifacts",
            )
            for index in range(2):
                stored = LocalArtifactStore(root / "staging").put(
                    run.id, f"image-{index}.png", f"PNG-{index}".encode(), "image/png"
                )
                store.data[stored.path] = f"PNG-{index}".encode()
                repo.record_artifact(run.id, ArtifactKind.IMAGE, stored)
            document = LocalArtifactStore(root / "staging").put(
                run.id, "design.md", b"design", "text/markdown"
            )
            store.data[document.path] = b"design"
            repo.record_artifact(run.id, ArtifactKind.DOCUMENT, document)

            detail = HistoryService(repo, store).reopen(
                run.id,
                include_artifact_data=True,
                data_mime_prefixes=("image/",),
            )

            self.assertEqual(store.read_many_calls, 1)
            self.assertEqual(store.read_calls, 0)
            self.assertEqual([item.data for item in detail.artifacts], [b"PNG-0", b"PNG-1", None])

    def test_reopen_loads_persisted_result_and_image_without_session_state(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "private-owner")
            repo.initialize()
            store = LocalArtifactStore(root / "storage")
            run = repo.create_pipeline_run(
                CreateRunCommand("智能药盒", "提醒老人吃药", "dashscope", "wan2.7-image-pro", 1),
                "history-test",
            )
            repo.save_generation_run(
                run.id,
                json.dumps({"evidence_count": 1}, ensure_ascii=False),
                json.dumps({"design_text": "持久化方案"}, ensure_ascii=False),
                88,
                "达标",
            )
            stored = store.put(run.id, "产品效果图.png", b"PNG", "image/png")
            repo.record_artifact(run.id, ArtifactKind.IMAGE, stored)

            detail = HistoryService(repo, store).reopen(run.id, include_artifact_data=True)

            self.assertEqual(detail.result["design_text"], "持久化方案")
            self.assertEqual(detail.context["evidence_count"], 1)
            self.assertEqual(detail.artifacts[0].sha256, stored.sha256)
            self.assertEqual(detail.artifacts[0].data, b"PNG")

    def test_history_list_is_ordered_by_latest_update(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "private-owner")
            repo.initialize()
            store = LocalArtifactStore(root / "storage")
            repo.create_pipeline_run(CreateRunCommand("A", "A", "offline", "rules", 0), "a")
            repo.create_pipeline_run(CreateRunCommand("B", "B", "offline", "rules", 0), "b")

            runs = HistoryService(repo, store).list_runs()

            self.assertEqual(len(runs), 2)
            self.assertEqual(runs[0].target_product, "B")


if __name__ == "__main__":
    unittest.main()
