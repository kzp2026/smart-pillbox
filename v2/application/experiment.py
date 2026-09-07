"""Adapter from the reproducible paper runner to V2 private history/storage."""
from __future__ import annotations

import copy
import hashlib
import io
import json
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

from experiment.pipeline.service import artifact, run_experiment, verify_run
from experiment import METHOD_VERSION
from v2.application.history import HistoryService
from v2.application.artifacts import ArchiveLimits, UnsafeArchive, extract_archive, inspect_archive
from v2.domain.models import ArtifactKind, CreateRunCommand, RunStatus


def load_example_config() -> dict:
    path = Path(__file__).resolve().parents[2] / "experiment" / "config.example.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_research_config() -> dict:
    path = Path(__file__).resolve().parents[2] / "experiment" / "config.research.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _archive_run(run: Path) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive_file:
        for path in sorted(run.rglob("*")):
            if path.is_file():
                archive_file.write(path, path.relative_to(run).as_posix())
    return buffer.getvalue()


class ExperimentService:
    """Run the same offline service as the CLI and save its complete output privately."""

    def __init__(self, repository, store):
        self.repository, self.store = repository, store

    def run(self, config: dict, input_path: Path, *, mapping_review: Path | None = None,
            reviews: Path | None = None, changes: Path | None = None,
            annotations: Path | None = None, parent_run: Path | None = None,
            request_id: str | None = None, stop_after: str | None = None,
            provider=None) -> dict:
        cfg = copy.deepcopy(config)
        input_path = Path(input_path)
        identity_data = json.dumps(cfg, ensure_ascii=False, sort_keys=True).encode("utf-8") + input_path.read_bytes()
        for optional_path in (mapping_review, reviews, changes, annotations):
            if optional_path: identity_data += Path(optional_path).read_bytes()
        if parent_run: identity_data += verify_run(Path(parent_run))["run_id"].encode("utf-8")
        content_digest = hashlib.sha256(identity_data + str(stop_after).encode()).hexdigest()
        identity = request_id.strip() + ':' + content_digest if request_id and request_id.strip() else content_digest
        pipeline = self.repository.create_pipeline_run(
            CreateRunCommand(cfg.get("product_name", ""), cfg.get("ordinary_requirements", ""),
                             "research", METHOD_VERSION, 0), "paper-repro-v2.1:" + identity)
        if pipeline.status in (RunStatus.SUCCEEDED, RunStatus.PARTIAL, RunStatus.FAILED):
            try:
                return {**self.load(pipeline.id), "pipeline_run_id": pipeline.id,
                        "provider": "research", "model": METHOD_VERSION}
            except ValueError:
                if pipeline.status != RunStatus.FAILED:
                    raise
        self.repository.update_pipeline_run(pipeline.id, RunStatus.RUNNING, current_stage="clean")
        with tempfile.TemporaryDirectory(prefix="v2-paper-") as temporary:
          run = None
          try:
            run = run_experiment(cfg, input_path, Path(temporary) / "runs",
                                 mapping_review=mapping_review, reviews=reviews, changes=changes,
                                 annotations=annotations, parent_run=parent_run,
                                 stop_after=stop_after, provider=provider)
            manifest = verify_run(run)
            if manifest['status']=='paused' and manifest['stages'].get('graph',{}).get('status')=='completed':
                from experiment.evaluation.materials import prepare_review_materials
                from experiment.pipeline.io import sha256, write_json
                prepare_review_materials(run,run/'review_materials')
                manifest['supplemental_artifacts']={p.relative_to(run).as_posix():sha256(p) for p in (run/'review_materials').rglob('*') if p.is_file()}
                manifest['artifacts']=sorted(set(manifest['artifacts'])|set(manifest['supplemental_artifacts']))
                write_json(run/'run_manifest.json',manifest)
            return self._persist(pipeline.id, cfg, run, manifest, requested_stop=stop_after)
          except Exception as exc:
            run = Path(getattr(exc, "run_path", run)) if getattr(exc, "run_path", run) else None
            if run is not None and run.is_dir() and (run / "run_manifest.json").is_file():
                manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
                self._persist(pipeline.id, cfg, run, manifest, requested_stop=stop_after)
            self.repository.update_pipeline_run(pipeline.id, RunStatus.FAILED,
                                                current_stage="experiment", error_summary="本地论文实验失败，请检查输入与配置。")
            self._invalidate()
            raise

    def _persist(self, pipeline_id: str, cfg: dict, run: Path, manifest: dict,
                 *, requested_stop: str | None = None) -> dict:
        mapping_rows = []
        try:
            mapping_rows = json.loads(artifact(run, "mapping", "mappings.json").read_text(encoding="utf-8"))
        except (ValueError, FileNotFoundError, KeyError):
            pass
        completeness = {}
        try:
            completeness = json.loads(artifact(run, "report", "completeness.json").read_text(encoding="utf-8"))
        except (ValueError, FileNotFoundError, KeyError):
            pass
        status = str(manifest.get("status") or "failed")
        generation = cfg.get("generation", {})
        summary = {
            "method_version": manifest.get("method_version", METHOD_VERSION),
            "actual_algorithm": manifest.get("actual_algorithm") or "not_clustered",
            "evidence_count": int(completeness.get("evidence_count", manifest.get("counts", {}).get("valid", 0))),
            "approved_mapping_count": sum(row.get("review_status") == "approved" for row in mapping_rows),
            "generation_mode": generation.get("mode", "test"),
            "independent_evaluation_completed": bool(completeness.get("independent_evaluation_completed")),
            "closed_loop_validated": bool(completeness.get("v1_v2_loop_completed")),
            "simulated": bool(manifest.get("simulated")) or generation.get("mode", "test") != "research",
            "run_status": status,
            "stopped_after": requested_stop if status == "paused" else next(
                (name for name in reversed(("clean", "topics", "requirements", "mapping", "graph", "generation", "evaluation", "report"))
                 if manifest.get("stages", {}).get(name, {}).get("status") == "completed"), None),
        }
        package = _archive_run(run)
        stored = self.store.put(pipeline_id, "paper-repro-v2.zip", package, "application/zip")
        self.repository.record_artifact(pipeline_id, ArtifactKind.ARCHIVE, stored)
        research_run = {**summary, "product": cfg.get("product_name", ""), "manifest": manifest,
                        "archive_sha256": stored.sha256}
        self.repository.save_generation_run(pipeline_id, "{}",
            json.dumps({"research_run": research_run}, ensure_ascii=False), 0,
            "artifact_completeness_only")
        mapped_status = RunStatus.SUCCEEDED if status == "completed" else RunStatus.PARTIAL if status == "paused" else RunStatus.FAILED
        self.repository.update_pipeline_run(pipeline_id, mapped_status, current_stage=summary["stopped_after"] or "experiment")
        self._invalidate()
        return {**research_run, "pipeline_run_id": pipeline_id, "provider": "research", "model": METHOD_VERSION}

    @staticmethod
    def _invalidate() -> None:
        try:
            from v2.application.runtime_state import VIEW_CACHE
            VIEW_CACHE.invalidate()
        except (ImportError, AttributeError):
            pass

    def load(self, run_id: str) -> dict:
        detail = HistoryService(self.repository, self.store).reopen(run_id)
        result = detail.result.get("research_run")
        if not result:
            raise ValueError("此记录不是可复现论文实验。")
        return result

    def download(self, run_id: str) -> bytes:
        rows = self.repository.list_artifacts_for_run(run_id)
        item = next((row for row in rows if row["name"] == "paper-repro-v2.zip"), None)
        if not item:
            raise ValueError("实验归档尚未生成。")
        data = self.store.read(item["storage_path"])
        if hashlib.sha256(data).hexdigest() != item["sha256"]:
            raise ValueError("实验归档哈希校验失败。")
        return data

    def rerun_with_reviews(self, parent_run_id: str, reviews: Path) -> dict:
        """Create an evaluation child only after scheme IDs exist in a verified parent."""
        with self._restored_parent(parent_run_id) as (root, config, input_path):
            return self.run(config, input_path, reviews=Path(reviews), parent_run=root)

    def rerun_with_changes(self, parent_run_id: str, changes: Path) -> dict:
        """Generate V2 from explicit change records against a verified V1 parent."""
        with self._restored_parent(parent_run_id) as (root, config, input_path):
            return self.run(config, input_path, changes=Path(changes), parent_run=root)

    @contextmanager
    def _restored_parent(self, parent_run_id: str):
        archive_bytes = self.download(parent_run_id)
        with tempfile.TemporaryDirectory(prefix="v2-paper-parent-") as temporary:
            root = Path(temporary).resolve()
            limits = ArchiveLimits.default()
            manifest = inspect_archive(archive_bytes, limits)
            normalized = [entry.path.replace("\\", "/").casefold() for entry in manifest.entries]
            if len(normalized) != len(set(normalized)):
                raise UnsafeArchive("实验归档包含重复路径。")
            extract_archive(archive_bytes, root, limits)
            verify_run(root)
            config = json.loads((root / "config.json").read_text(encoding="utf-8"))
            inputs = list((root / "private").glob("input.*"))
            if len(inputs) != 1:
                raise ValueError("父运行缺少唯一原始输入。")
            yield root, config, inputs[0]
