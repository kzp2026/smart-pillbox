from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.history import HistoryService
from v2.domain.models import ArtifactKind, CreateRunCommand


class HistoryServiceTests(unittest.TestCase):
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
