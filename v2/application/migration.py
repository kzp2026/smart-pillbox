from __future__ import annotations

import hashlib
import json
import mimetypes
from collections import Counter
from dataclasses import dataclass

from v2.adapters.legacy import LegacyReader, LegacySnapshot
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import ArtifactStore
from v2.domain.models import ArtifactKind, CreateRunCommand


@dataclass(frozen=True)
class MigrationReport:
    mode: str
    source_counts: dict[str, int]
    target_counts: dict[str, int]
    migrated: dict[str, int]
    skipped: dict[str, int]
    warnings: tuple[str, ...] = ()

    @property
    def migrated_total(self) -> int:
        return sum(self.migrated.values())

    @property
    def skipped_total(self) -> int:
        return sum(self.skipped.values())


@dataclass(frozen=True)
class VerificationReport:
    consistent: bool
    failed_checks: tuple[str, ...]
    checked_files: int


class MigrationService:
    def __init__(self, reader: LegacyReader, repository: KnowledgeRepository, store: ArtifactStore) -> None:
        self.reader = reader
        self.repository = repository
        self.store = store

    def dry_run(self) -> MigrationReport:
        snapshot = self.reader.scan()
        return MigrationReport(
            mode="dry-run",
            source_counts=snapshot.counts,
            target_counts=self._target_counts(),
            migrated={key: 0 for key in snapshot.counts},
            skipped={key: 0 for key in snapshot.counts},
        )

    def apply(self) -> MigrationReport:
        snapshot = self.reader.scan()
        migrated = {key: 0 for key in snapshot.counts}
        skipped = {key: 0 for key in snapshot.counts}
        product_map: dict[int, int] = {}
        batch_map: dict[int, int] = {}

        for product in snapshot.products:
            source_id = str(product["id"])
            target = self.repository.get_migration_target("product", source_id)
            if target:
                product_map[int(product["id"])] = int(target)
                skipped["products"] += 1
                continue
            target_id = self.repository.upsert_product(
                str(product.get("name") or "未命名产品"),
                str(product.get("category") or ""),
                str(product.get("description") or ""),
            )
            product_map[int(product["id"])] = target_id
            self.repository.record_migration("product", source_id, "product", str(target_id))
            migrated["products"] += 1

        comments_by_batch: dict[int, list[dict]] = {}
        for comment in snapshot.comments:
            comments_by_batch.setdefault(int(comment["batch_id"]), []).append(comment)

        for batch in snapshot.comment_batches:
            source_id = str(batch["id"])
            target = self.repository.get_migration_target("comment_batch", source_id)
            batch_comments = comments_by_batch.get(int(batch["id"]), [])
            if target:
                batch_map[int(batch["id"])] = int(target)
                skipped["comment_batches"] += 1
                skipped["comments"] += len(batch_comments)
                continue
            product_id = product_map.get(int(batch["product_id"]))
            if not product_id:
                continue
            product = next(item for item in snapshot.products if int(item["id"]) == int(batch["product_id"]))
            report = self.repository.ingest_comments(
                str(product.get("name") or "未命名产品"),
                str(product.get("category") or ""),
                str(batch.get("source_filename") or "legacy"),
                [str(item.get("comment_original") or item.get("clean_comment") or "") for item in batch_comments],
            )
            batch_map[int(batch["id"])] = report.batch_id
            self.repository.record_migration("comment_batch", source_id, "comment_batch", str(report.batch_id))
            migrated["comment_batches"] += 1
            for comment in batch_comments:
                comment_source_id = str(comment["id"])
                target_comment_id = self.repository.find_comment_id(
                    product_id, str(comment.get("comment_original") or comment.get("clean_comment") or "")
                )
                self.repository.record_migration(
                    "comment", comment_source_id, "comment", str(target_comment_id or "")
                )
                migrated["comments"] += 1

        for requirement in snapshot.requirements:
            source_id = str(requirement["id"])
            target = self.repository.get_migration_target("requirement", source_id)
            if target:
                skipped["requirements"] += 1
                continue
            product_id = product_map.get(int(requirement["product_id"]))
            if not product_id:
                continue
            target_id = self.repository.add_requirement_once(
                product_id=product_id,
                batch_id=batch_map.get(int(requirement["batch_id"])) if requirement.get("batch_id") else None,
                title=str(requirement.get("title") or "历史需求"),
                description=str(requirement.get("description") or ""),
                keywords=str(requirement.get("keywords") or ""),
                evidence_text=str(requirement.get("evidence_text") or ""),
                score=float(requirement.get("score") or 0),
                dedupe_identity=f"legacy-requirement:{source_id}",
            )
            self.repository.record_migration("requirement", source_id, "requirement", str(target_id))
            migrated["requirements"] += 1

        for generation in snapshot.generation_runs:
            source_id = str(generation["id"])
            target = self.repository.get_migration_target("generation_run", source_id)
            if target:
                skipped["generation_runs"] += 1
                continue
            run = self.repository.create_pipeline_run(
                CreateRunCommand(
                    target_product=str(generation.get("target_product") or "历史方案"),
                    demand_text=str(generation.get("demand_text") or ""),
                    provider="legacy",
                    model="legacy-snapshot",
                    image_count=self._image_count(str(generation.get("result_json") or "{}")),
                ),
                idempotency_key=f"legacy-generation:{source_id}",
            )
            target_id = self.repository.save_generation_run(
                run.id,
                str(generation.get("context_json") or "{}"),
                str(generation.get("result_json") or "{}"),
                float(generation.get("quality_score") or 0),
                str(generation.get("quality_status") or ""),
            )
            self.repository.record_migration("generation_run", source_id, "generation_run", target_id)
            migrated["generation_runs"] += 1

        snapshot_run = None
        if snapshot.files:
            snapshot_run = self.repository.create_pipeline_run(
                CreateRunCommand("原站历史快照", "迁移原站可见结果", "legacy", "legacy-files", 0),
                idempotency_key="legacy-visible-files-snapshot",
            )
        basename_counts = Counter(item.path.name for item in snapshot.files)
        for legacy_file in snapshot.files:
            target = self.repository.get_migration_target(
                "legacy_file", legacy_file.relative_path, legacy_file.sha256
            )
            if target:
                skipped["files"] += 1
                continue
            assert snapshot_run is not None
            storage_name = legacy_file.path.name
            if basename_counts[storage_name] > 1:
                identity = hashlib.sha256(
                    f"{legacy_file.relative_path}\x1f{legacy_file.sha256}".encode("utf-8")
                ).hexdigest()[:12]
                storage_name = f"{identity}-{storage_name}"
            stored = self.store.put(
                snapshot_run.id,
                storage_name,
                legacy_file.path.read_bytes(),
                mimetypes.guess_type(legacy_file.path.name)[0] or "application/octet-stream",
            )
            artifact_id = self.repository.record_artifact(snapshot_run.id, ArtifactKind.LEGACY, stored)
            self.repository.record_migration(
                "legacy_file", legacy_file.relative_path, "artifact", artifact_id, legacy_file.sha256
            )
            migrated["files"] += 1

        return MigrationReport(
            mode="apply",
            source_counts=snapshot.counts,
            target_counts=self._target_counts(),
            migrated=migrated,
            skipped=skipped,
        )

    def verify(self) -> VerificationReport:
        snapshot = self.reader.scan()
        failures: list[str] = []
        expected_minimums = {
            "products": len(snapshot.products),
            "comments": len({(item["product_id"], item.get("comment_original")) for item in snapshot.comments}),
            "requirements": len(snapshot.requirements),
            "generation_runs": len(snapshot.generation_runs),
            "artifacts": len(snapshot.files),
        }
        target = self._target_counts()
        for name, expected in expected_minimums.items():
            if target.get(name, 0) < expected:
                failures.append(f"{name}: expected>={expected}, actual={target.get(name, 0)}")

        artifacts = self.repository.list_artifacts()
        artifact_hashes = {str(item["sha256"]) for item in artifacts}
        for legacy_file in snapshot.files:
            if legacy_file.sha256 not in artifact_hashes:
                failures.append(f"file:{legacy_file.relative_path}")
                continue
            stored_row = next(item for item in artifacts if str(item["sha256"]) == legacy_file.sha256)
            stored_data = self.store.read(str(stored_row["storage_path"]))
            if hashlib.sha256(stored_data).hexdigest() != legacy_file.sha256:
                failures.append(f"hash:{legacy_file.relative_path}")

        return VerificationReport(not failures, tuple(failures), len(snapshot.files))

    def _target_counts(self) -> dict[str, int]:
        return {
            table: self.repository.count_rows(table)
            for table in (
                "products",
                "comment_batches",
                "comments",
                "requirements",
                "generation_runs",
                "pipeline_runs",
                "artifacts",
            )
        }

    @staticmethod
    def _image_count(result_json: str) -> int:
        try:
            result = json.loads(result_json)
        except (TypeError, ValueError):
            return 0
        images = result.get("image_paths") or result.get("image_prompts") or []
        return len(images) if isinstance(images, list) else 0
