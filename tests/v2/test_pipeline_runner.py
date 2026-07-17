from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore
from v2.domain.models import CreateRunCommand, RunStatus
from v2.pipeline.catalog import LEGACY_STAGES
from v2.pipeline.runner import GeneratedArtifact, PipelineRunner, StageExecution, SubprocessStageExecutor


class FailingSecondStageExecutor:
    def __init__(self) -> None:
        self.called: list[str] = []

    def execute(self, stage, context):
        self.called.append(stage.id)
        if stage.id == "02":
            return StageExecution(False, (), "关键词服务失败")
        return StageExecution(
            True,
            (GeneratedArtifact("cleaned_comments.xlsx", b"xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),),
            "",
        )


class SuccessfulExecutor:
    def execute(self, stage, context):
        return StageExecution(True, (GeneratedArtifact(f"{stage.id}.txt", stage.id.encode(), "text/plain"),), "")


class PipelineRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", "private-owner")
        self.repo.initialize()
        self.store = LocalArtifactStore(root / "storage")
        self.run = self.repo.create_pipeline_run(
            CreateRunCommand("智能药盒", "提醒老人吃药", "offline", "rules", 0),
            "pipeline-test",
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_failed_stage_stops_dependents_and_preserves_successful_artifacts(self) -> None:
        executor = FailingSecondStageExecutor()
        runner = PipelineRunner(self.repo, self.store, executor)

        result = runner.run_all(self.run.id, product_name="智能药盒", input_path="comments.csv")

        self.assertEqual(result.status, RunStatus.PARTIAL)
        self.assertEqual(result.completed_stage_ids, ("01",))
        self.assertEqual(result.failed_stage_id, "02")
        self.assertEqual(executor.called, ["01", "02"])
        self.assertEqual(self.repo.count_rows("artifacts"), 1)
        self.assertEqual(self.repo.get_pipeline_run(self.run.id).status, RunStatus.PARTIAL)

    def test_all_stages_complete_in_catalog_order(self) -> None:
        result = PipelineRunner(self.repo, self.store, SuccessfulExecutor()).run_all(
            self.run.id, product_name="智能药盒", input_path="comments.csv"
        )

        self.assertEqual(result.status, RunStatus.SUCCEEDED)
        self.assertEqual(result.completed_stage_ids, tuple(stage.id for stage in LEGACY_STAGES))
        self.assertEqual(self.repo.count_rows("stage_runs"), 10)

    def test_subprocess_command_preserves_original_script_arguments(self) -> None:
        executor = SubprocessStageExecutor(
            project_root=Path("D:/project"),
            output_root=Path("D:/project/output/v2-runs"),
            python_executable="python",
        )

        command = executor.build_command(
            LEGACY_STAGES[4],
            {"run_id": "run", "product_name": "智能药盒", "input_path": "comments.csv"},
        )

        self.assertIn("05_build_mapping_database.py", " ".join(command))
        self.assertIn("--product-name", command)
        self.assertIn("智能药盒", command)
        self.assertIn("--output-dir", command)


if __name__ == "__main__":
    unittest.main()
