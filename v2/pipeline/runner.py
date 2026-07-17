from __future__ import annotations

import hashlib
import mimetypes
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Protocol

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import ArtifactStore
from v2.domain.models import ArtifactKind, RunStatus
from v2.pipeline.catalog import LEGACY_STAGES, STAGE_BY_ID, StageDefinition


@dataclass(frozen=True)
class GeneratedArtifact:
    name: str
    data: bytes
    mime_type: str


@dataclass(frozen=True)
class StageExecution:
    succeeded: bool
    artifacts: tuple[GeneratedArtifact, ...]
    error_summary: str


@dataclass(frozen=True)
class PipelineResult:
    status: RunStatus
    completed_stage_ids: tuple[str, ...]
    failed_stage_id: str
    artifact_ids: tuple[str, ...]


class StageExecutor(Protocol):
    def execute(self, stage: StageDefinition, context: Mapping[str, str]) -> StageExecution: ...


class PipelineRunner:
    def __init__(
        self,
        repository: KnowledgeRepository,
        store: ArtifactStore,
        executor: StageExecutor,
    ) -> None:
        self.repository = repository
        self.store = store
        self.executor = executor

    def run_all(self, run_id: str, product_name: str, input_path: str) -> PipelineResult:
        completed: list[str] = []
        artifact_ids: list[str] = []
        self.repository.update_pipeline_run(run_id, RunStatus.RUNNING)
        context = {"run_id": run_id, "product_name": product_name, "input_path": input_path}
        input_hash = hashlib.sha256(f"{product_name}\x1f{input_path}".encode("utf-8")).hexdigest()

        for stage in LEGACY_STAGES:
            self.repository.update_pipeline_run(run_id, RunStatus.RUNNING, current_stage=stage.id)
            try:
                execution = self.executor.execute(stage, context)
            except Exception as exc:
                execution = StageExecution(False, (), str(exc))
            if not execution.succeeded:
                status = RunStatus.PARTIAL if completed else RunStatus.FAILED
                self.repository.record_stage_run(
                    run_id, stage.id, RunStatus.FAILED, input_hash, execution.error_summary
                )
                self.repository.update_pipeline_run(
                    run_id, status, current_stage=stage.id, error_summary=execution.error_summary
                )
                return PipelineResult(status, tuple(completed), stage.id, tuple(artifact_ids))

            for generated in execution.artifacts:
                stored = self.store.put(run_id, generated.name, generated.data, generated.mime_type)
                artifact_id = self.repository.record_artifact(
                    run_id, self._artifact_kind(generated), stored
                )
                artifact_ids.append(artifact_id)
            self.repository.record_stage_run(run_id, stage.id, RunStatus.SUCCEEDED, input_hash)
            completed.append(stage.id)

        self.repository.update_pipeline_run(run_id, RunStatus.SUCCEEDED, current_stage="10")
        return PipelineResult(RunStatus.SUCCEEDED, tuple(completed), "", tuple(artifact_ids))

    def run_stage(
        self,
        run_id: str,
        stage_id: str,
        product_name: str,
        input_path: str,
    ) -> PipelineResult:
        stage = STAGE_BY_ID[stage_id]
        context = {"run_id": run_id, "product_name": product_name, "input_path": input_path}
        execution = self.executor.execute(stage, context)
        if not execution.succeeded:
            self.repository.record_stage_run(run_id, stage.id, RunStatus.FAILED, error_summary=execution.error_summary)
            self.repository.update_pipeline_run(run_id, RunStatus.FAILED, stage.id, execution.error_summary)
            return PipelineResult(RunStatus.FAILED, (), stage.id, ())
        artifact_ids = []
        for generated in execution.artifacts:
            stored = self.store.put(run_id, generated.name, generated.data, generated.mime_type)
            artifact_ids.append(
                self.repository.record_artifact(run_id, self._artifact_kind(generated), stored)
            )
        self.repository.record_stage_run(run_id, stage.id, RunStatus.SUCCEEDED)
        self.repository.update_pipeline_run(run_id, RunStatus.SUCCEEDED, stage.id)
        return PipelineResult(RunStatus.SUCCEEDED, (stage.id,), "", tuple(artifact_ids))

    @staticmethod
    def _artifact_kind(generated: GeneratedArtifact) -> ArtifactKind:
        if generated.mime_type.startswith("image/"):
            return ArtifactKind.IMAGE
        if generated.name.lower().endswith((".xlsx", ".xls", ".csv")):
            return ArtifactKind.TABLE
        if generated.name.lower().endswith(".zip"):
            return ArtifactKind.ARCHIVE
        return ArtifactKind.DOCUMENT


class SubprocessStageExecutor:
    def __init__(
        self,
        project_root: Path,
        output_root: Path,
        python_executable: str | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: int = 1800,
    ) -> None:
        self.project_root = project_root.resolve()
        self.output_root = output_root.resolve()
        self.python_executable = python_executable or sys.executable
        self.environment = dict(environment or {})
        self.timeout_seconds = timeout_seconds

    def build_command(self, stage: StageDefinition, context: Mapping[str, str]) -> list[str]:
        run_dir = self.output_root / context["run_id"]
        command = [
            self.python_executable,
            str(self.project_root / "scripts" / stage.script_name),
            "--output-dir",
            str(run_dir),
        ]
        if stage.accepts_input and context.get("input_path"):
            command.extend(["--input", context["input_path"]])
        if stage.accepts_product_name:
            command.extend(["--product-name", context["product_name"]])
        return command

    def execute(self, stage: StageDefinition, context: Mapping[str, str]) -> StageExecution:
        run_dir = self.output_root / context["run_id"]
        run_dir.mkdir(parents=True, exist_ok=True)
        before = self._file_hashes(run_dir)
        environment = os.environ.copy()
        environment.update(self.environment)
        process = subprocess.run(
            self.build_command(stage, context),
            cwd=self.project_root,
            capture_output=True,
            text=True,
            env=environment,
            timeout=self.timeout_seconds,
        )
        if process.returncode != 0:
            error = (process.stderr or process.stdout or "阶段运行失败").strip()
            return StageExecution(False, (), error[:1200])
        artifacts: list[GeneratedArtifact] = []
        for path in sorted(item for item in run_dir.rglob("*") if item.is_file()):
            relative = path.relative_to(run_dir).as_posix()
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            if before.get(relative) == digest:
                continue
            artifacts.append(
                GeneratedArtifact(
                    name=path.name,
                    data=data,
                    mime_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                )
            )
        return StageExecution(True, tuple(artifacts), "")

    @staticmethod
    def _file_hashes(root: Path) -> dict[str, str]:
        return {
            path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in root.rglob("*")
            if path.is_file()
        }
