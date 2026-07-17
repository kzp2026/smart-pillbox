from __future__ import annotations

from dataclasses import dataclass

from v2.adapters.storage import ArtifactStore


@dataclass(frozen=True)
class DeletionPlan:
    product_id: int
    product_name: str
    artifact_paths: tuple[str, ...]
    comment_count: int
    requirement_count: int
    run_count: int


@dataclass(frozen=True)
class DeletionResult:
    status: str
    deleted_paths: tuple[str, ...]
    failed_paths: tuple[str, ...]
    database_deleted: bool


class DeletionService:
    def __init__(self, repository: object, store: ArtifactStore) -> None:
        self.repository = repository
        self.store = store

    def execute(self, plan: DeletionPlan) -> DeletionResult:
        file_result = self.store.delete_many(list(plan.artifact_paths))
        if file_result.failed:
            return DeletionResult(
                status="partial",
                deleted_paths=file_result.deleted,
                failed_paths=file_result.failed,
                database_deleted=False,
            )
        database_deleted = bool(self.repository.delete_product(plan.product_id))
        return DeletionResult(
            status="succeeded" if database_deleted else "failed",
            deleted_paths=file_result.deleted,
            failed_paths=(),
            database_deleted=database_deleted,
        )
