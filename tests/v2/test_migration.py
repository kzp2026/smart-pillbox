from __future__ import annotations

import json
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path

from v2.adapters.legacy import LegacyReader
from v2.adapters.postgres import KnowledgeRepository
from v2.adapters.storage import LocalArtifactStore, StoredArtifact, artifact_path
from v2.application.migration import MigrationService


def create_legacy_database(path: Path) -> None:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE products (
            id INTEGER PRIMARY KEY, owner_id TEXT, name TEXT, category TEXT, description TEXT,
            visibility TEXT, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE comment_batches (
            id INTEGER PRIMARY KEY, owner_id TEXT, product_id INTEGER, source_filename TEXT,
            comment_count INTEGER, created_at TEXT
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY, owner_id TEXT, product_id INTEGER, batch_id INTEGER,
            comment_original TEXT, clean_comment TEXT, fingerprint TEXT, created_at TEXT
        );
        CREATE TABLE requirements (
            id INTEGER PRIMARY KEY, owner_id TEXT, product_id INTEGER, batch_id INTEGER,
            title TEXT, description TEXT, keywords TEXT, evidence_text TEXT, score REAL, created_at TEXT
        );
        CREATE TABLE generation_runs (
            id INTEGER PRIMARY KEY, owner_id TEXT, target_product TEXT, demand_text TEXT,
            context_json TEXT, result_json TEXT, quality_score REAL, quality_status TEXT, created_at TEXT
        );
        """
    )
    now = "2026-07-01T00:00:00+00:00"
    connection.execute(
        "INSERT INTO products VALUES (1, 'private', '智能药盒', '适老健康', '旧产品', 'private', ?, ?)",
        (now, now),
    )
    connection.execute("INSERT INTO comment_batches VALUES (10, 'private', 1, 'comments.csv', 1, ?)", (now,))
    connection.execute(
        "INSERT INTO comments VALUES (100, 'private', 1, 10, '提醒声音太小', '提醒声音太小', 'old-fp', ?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO requirements VALUES (200, 'private', 1, 10, '提醒反馈', '提醒要清晰', '提醒、声音', '提醒声音太小', 80, ?)",
        (now,),
    )
    connection.execute(
        "INSERT INTO generation_runs VALUES (300, 'private', '智能药盒', '提醒老人吃药', ?, ?, 88, '达标', ?)",
        (
            json.dumps({"evidence_count": 1}, ensure_ascii=False),
            json.dumps({"design_text": "旧设计方案", "image_prompts": ["prompt"]}, ensure_ascii=False),
            now,
        ),
    )
    connection.commit()
    connection.close()


class StrictNameStore:
    """Mimics remote object storage where a duplicate path is rejected."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put(self, run_id, name: str, data: bytes, mime_type: str) -> StoredArtifact:
        path = artifact_path(run_id, name)
        if path in self.objects:
            raise RuntimeError("duplicate remote object path")
        self.objects[path] = data
        return StoredArtifact(
            str(run_id),
            Path(name).name,
            path,
            mime_type,
            len(data),
            hashlib.sha256(data).hexdigest(),
        )

    def read(self, path: str) -> bytes:
        return self.objects[path]

    def delete_many(self, paths):
        raise NotImplementedError


class MigrationServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        source_path = root / "legacy.sqlite3"
        create_legacy_database(source_path)
        output_dir = root / "output"
        (output_dir / "design_images").mkdir(parents=True)
        (output_dir / "方案评价表.xlsx").write_bytes(b"evaluation-xlsx")
        (output_dir / "design_images" / "产品效果图.png").write_bytes(b"product-image")

        self.reader = LegacyReader(f"sqlite:///{source_path}", owner_id="private", output_roots=[output_dir])
        self.repo = KnowledgeRepository(f"sqlite:///{root / 'v2.sqlite3'}", owner_id="private-owner")
        self.repo.initialize()
        self.store = LocalArtifactStore(root / "private-storage")
        self.service = MigrationService(self.reader, self.repo, self.store)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_dry_run_never_writes_target(self) -> None:
        before = self.repo.total_business_rows()

        report = self.service.dry_run()

        self.assertEqual(self.repo.total_business_rows(), before)
        self.assertEqual(report.source_counts["products"], 1)
        self.assertEqual(report.source_counts["files"], 2)
        self.assertEqual(report.mode, "dry-run")

    def test_apply_twice_is_idempotent(self) -> None:
        first = self.service.apply()
        second = self.service.apply()

        self.assertEqual(first.target_counts, second.target_counts)
        self.assertEqual(second.migrated_total, 0)
        self.assertGreater(second.skipped_total, 0)
        self.assertEqual(self.repo.count_rows("products"), 1)
        self.assertEqual(self.repo.count_rows("comments"), 1)
        self.assertEqual(self.repo.count_rows("requirements"), 1)
        self.assertEqual(self.repo.count_rows("generation_runs"), 1)
        self.assertEqual(self.repo.count_rows("artifacts"), 2)

    def test_unowned_visible_files_become_legacy_snapshot_artifacts(self) -> None:
        self.service.apply()

        artifact = self.repo.find_artifact_by_name("产品效果图.png")

        self.assertIsNotNone(artifact)
        self.assertEqual(artifact["kind"], "legacy")
        self.assertEqual(self.store.read(artifact["storage_path"]), b"product-image")

    def test_verify_confirms_counts_and_file_hashes(self) -> None:
        self.service.apply()

        verification = self.service.verify()

        self.assertTrue(verification.consistent)
        self.assertEqual(verification.failed_checks, ())
        self.assertEqual(verification.checked_files, 2)

    def test_duplicate_legacy_requirements_are_preserved_as_history(self) -> None:
        source_path = Path(self.reader.database_url.removeprefix("sqlite:///"))
        connection = sqlite3.connect(source_path)
        try:
            original = connection.execute(
                "SELECT owner_id, product_id, batch_id, title, description, keywords, "
                "evidence_text, score, created_at FROM requirements WHERE id = 200"
            ).fetchone()
            connection.execute(
                "INSERT INTO requirements VALUES (201, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                original,
            )
            connection.commit()
        finally:
            connection.close()

        self.service.apply()

        self.assertEqual(self.repo.count_rows("requirements"), 2)

    def test_duplicate_legacy_basenames_are_preserved_as_distinct_artifacts(self) -> None:
        root = Path(self.temp_dir.name)
        second_root = root / "second-output"
        (second_root / "design_images").mkdir(parents=True)
        (second_root / "design_images" / "产品效果图.png").write_bytes(b"second-image")
        service = MigrationService(
            LegacyReader(
                self.reader.database_url,
                owner_id="private",
                output_roots=[root / "output", second_root],
            ),
            self.repo,
            self.store,
        )

        service.apply()

        artifacts = self.repo.list_artifacts()
        image_hashes = {
            item["sha256"]
            for item in artifacts
            if str(item["name"]).endswith("产品效果图.png")
        }
        self.assertEqual(len(image_hashes), 2)

    def test_duplicate_basenames_do_not_collide_in_remote_storage(self) -> None:
        root = Path(self.temp_dir.name)
        second_root = root / "remote-second-output"
        (second_root / "design_images").mkdir(parents=True)
        (second_root / "design_images" / "产品效果图.png").write_bytes(b"remote-second-image")
        strict_store = StrictNameStore()
        service = MigrationService(
            LegacyReader(
                self.reader.database_url,
                owner_id="private",
                output_roots=[root / "output", second_root],
            ),
            self.repo,
            strict_store,
        )

        service.apply()

        self.assertEqual(len(strict_store.objects), 3)


if __name__ == "__main__":
    unittest.main()
