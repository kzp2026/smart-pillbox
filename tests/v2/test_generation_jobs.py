from __future__ import annotations

import json
from threading import Event
import tempfile
import time
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.application.generation import GenerationCommand
from v2.auth import hash_password
from v2.config import AppConfig
from v2.domain.models import CreateRunCommand, RunStatus


class GenerationJobRegistryTests(unittest.TestCase):
    def test_runs_design_work_in_background_and_reports_completion(self) -> None:
        from v2.application.generation_jobs import GenerationJobRegistry

        registry = GenerationJobRegistry()
        started = Event()
        release = Event()

        def work() -> None:
            started.set()
            release.wait(timeout=2)

        submitted_at = time.monotonic()
        self.assertTrue(registry.start("run-1", work))
        self.assertLess(time.monotonic() - submitted_at, 0.2)
        self.assertTrue(started.wait(timeout=1))
        self.assertEqual(registry.snapshot("run-1").status, "running")
        release.set()
        self.assertTrue(registry.wait("run-1", timeout=2))
        self.assertEqual(registry.snapshot("run-1").status, "completed")

    def test_reports_background_failure_without_blocking_the_ui_thread(self) -> None:
        from v2.application.generation_jobs import GenerationJobRegistry

        registry = GenerationJobRegistry()

        self.assertTrue(registry.start("run-2", lambda: (_ for _ in ()).throw(RuntimeError("boom"))))
        self.assertTrue(registry.wait("run-2", timeout=2))
        snapshot = registry.snapshot("run-2")

        self.assertEqual(snapshot.status, "failed")
        self.assertTrue(snapshot.error)

    def test_background_design_generation_persists_text_package_before_marking_success(self) -> None:
        from v2.app import (
            _GENERATION_JOB_REGISTRY,
            _generation_job_key,
            _schedule_design_generation,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = AppConfig.from_mapping(
                {
                    "V2_USERNAME": "owner",
                    "V2_PASSWORD_HASH": hash_password("password", salt=b"0" * 16),
                    "V2_DATABASE_URL": f"sqlite:///{root / 'private.sqlite3'}",
                }
            )
            repository = KnowledgeRepository(config.database_url, config.owner_id, config.schema)
            repository.initialize()
            imported = repository.ingest_comments(
                "验收药盒",
                "适老健康",
                "pm-acceptance.csv",
                [
                    "提醒声音太小，老人经常错过服药时间。",
                    "希望药盒能按早中晚分格收纳，还要防潮。",
                    "外观不要像普通收纳盒，希望有温和耐用的质感。",
                ],
            )
            for title, description, keywords, evidence in (
                ("提醒反馈", "老人需要听得见、看得见并确认服药提醒。", ["提醒", "反馈"], "提醒声音太小，老人经常错过服药时间。"),
                ("容量收纳", "按早中晚分格，减少错拿与遗漏。", ["分格", "收纳"], "希望药盒能按早中晚分格收纳。"),
                ("防潮密封", "药仓需要避免受潮，保护药品。", ["防潮", "密封"], "担心药品受潮。"),
                ("外观质感", "外观需要温和、耐用且不像普通收纳盒。", ["外观", "质感"], "希望有温和耐用的质感。"),
            ):
                repository.add_requirement_once(
                    imported.product_id,
                    imported.batch_id,
                    title,
                    description,
                    keywords,
                    evidence,
                    90,
                )
            run = repository.create_pipeline_run(
                CreateRunCommand(
                    "验收药盒",
                    "强化提醒反馈、分时段分格收纳、防潮密封和外观质感",
                    "dashscope",
                    "wan2.7-image-pro",
                    0,
                ),
                idempotency_key="background-generation-test",
            )
            command = GenerationCommand(
                "验收药盒",
                "强化提醒反馈、分时段分格收纳、防潮密封和外观质感",
                "dashscope",
                "wan2.7-image-pro",
                0,
            )

            self.assertTrue(
                _schedule_design_generation(
                    config,
                    repository,
                    LocalArtifactStore(root / "artifacts"),
                    run.id,
                    command,
                    {},
                )
            )
            self.assertTrue(_GENERATION_JOB_REGISTRY.wait(_generation_job_key(repository, run.id), timeout=5))

            completed = repository.get_pipeline_run(run.id)
            detail = repository.get_generation_run(run.id)
            self.assertEqual(
                completed.status,
                RunStatus.SUCCEEDED,
                f"run={completed} job={_GENERATION_JOB_REGISTRY.snapshot(_generation_job_key(repository, run.id))}",
            )
            self.assertIsNotNone(detail)
            result = json.loads(str(detail["result_json"]))
            self.assertTrue(result["design_text"].strip())
            self.assertTrue(result["industrial_design_prompt"].strip())
            self.assertEqual(result["quality_status"], "达标")
            self.assertGreaterEqual(result["quality_report"]["evidence_count"], 4)
            self.assertEqual(
                [item["label"] for item in result["visual_assets"]],
                [
                    "产品效果图 1",
                    "产品效果图 2",
                    "产品爆炸图",
                    "产品细节图",
                    "产品三视图",
                    "设计展板",
                    "产品使用效果图 1",
                    "产品使用效果图 2",
                ],
            )
            graph = result["requirement_function_structure_graph"]
            self.assertEqual(graph["version"], "semantic-v2")
            self.assertEqual(len(graph["links"]), 4)
            self.assertEqual(len({item["function"] for item in graph["links"]}), 4)
            self.assertEqual(len({item["structure"] for item in graph["links"]}), 4)


if __name__ == "__main__":
    unittest.main()
