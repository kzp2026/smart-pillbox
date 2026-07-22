from __future__ import annotations

import json
from dataclasses import dataclass

from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import ArtifactStore
from v2.domain.models import PipelineRun


@dataclass(frozen=True)
class HistoryArtifact:
    id: str
    name: str
    kind: str
    storage_path: str
    mime_type: str
    size_bytes: int
    sha256: str
    data: bytes | None = None


@dataclass(frozen=True)
class RunDetail:
    run: PipelineRun
    context: dict
    result: dict
    quality_score: float
    quality_status: str
    artifacts: tuple[HistoryArtifact, ...]


@dataclass(frozen=True)
class RunReview:
    decision: str = "undecided"
    rating: int = 0
    notes: str = ""
    is_final: bool = False
    updated_at: str = ""


class HistoryService:
    def __init__(self, repository: KnowledgeRepository, store: ArtifactStore) -> None:
        self.repository = repository
        self.store = store

    def list_runs(
        self,
        limit: int = 50,
        target_product: str | None = None,
    ) -> list[PipelineRun]:
        try:
            return self.repository.list_pipeline_runs(limit, target_product=target_product)
        except TypeError as exc:
            if "target_product" not in str(exc):
                raise
            legacy_limit = 200 if target_product else limit
            runs = self.repository.list_pipeline_runs(legacy_limit)
            if not target_product:
                return runs[:limit]
            return [run for run in runs if run.target_product == target_product][:limit]

    def reopen(
        self,
        run_id: str,
        include_artifact_data: bool = False,
        data_mime_prefixes: tuple[str, ...] = (),
    ) -> RunDetail:
        run = self.repository.get_pipeline_run(run_id)
        generation = self.repository.get_generation_run(run_id) or {}
        rows = self.repository.list_artifacts_for_run(run_id)
        requested_paths = [
            str(row["storage_path"])
            for row in rows
            if include_artifact_data
            and (
                not data_mime_prefixes
                or any(str(row["mime_type"]).startswith(prefix) for prefix in data_mime_prefixes)
            )
        ]
        read_many = getattr(self.store, "read_many", None)
        if callable(read_many):
            artifact_data = read_many(requested_paths)
        else:
            artifact_data = {path: self.store.read(path) for path in requested_paths}
        artifacts = []
        for row in rows:
            path = str(row["storage_path"])
            artifacts.append(
                HistoryArtifact(
                    id=str(row["id"]),
                    name=str(row["name"]),
                    kind=str(row["kind"]),
                    storage_path=path,
                    mime_type=str(row["mime_type"]),
                    size_bytes=int(row["size_bytes"]),
                    sha256=str(row["sha256"]),
                    data=artifact_data.get(path),
                )
            )
        return RunDetail(
            run=run,
            context=self._as_dict(generation.get("context_json", {})),
            result=self._as_dict(generation.get("result_json", {})),
            quality_score=float(generation.get("quality_score") or 0),
            quality_status=str(generation.get("quality_status") or ""),
            artifacts=tuple(artifacts),
        )

    def get_review(self, run_id: str) -> RunReview:
        row = self.repository.get_run_review(run_id)
        if not row:
            return RunReview()
        return RunReview(
            decision=str(row.get("decision") or "undecided"),
            rating=int(row.get("rating") or 0),
            notes=str(row.get("notes") or ""),
            is_final=bool(row.get("is_final")),
            updated_at=str(row.get("updated_at") or ""),
        )

    def save_review(
        self,
        run_id: str,
        decision: str,
        rating: int,
        notes: str,
        is_final: bool,
    ) -> RunReview:
        self.repository.save_run_review(run_id, decision, rating, notes, is_final)
        return self.get_review(run_id)

    @staticmethod
    def _as_dict(value: object) -> dict:
        if isinstance(value, dict):
            return value
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
