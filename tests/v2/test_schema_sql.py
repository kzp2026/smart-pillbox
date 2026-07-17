from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_SQL = ROOT / "v2" / "migrations" / "001_agent_v2_schema.sql"


class SchemaSqlTests(unittest.TestCase):
    def test_schema_creates_all_private_v2_tables(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8").lower()

        self.assertIn("create schema if not exists agent_v2", sql)
        for table in (
            "products",
            "comment_batches",
            "comments",
            "requirements",
            "generation_runs",
            "pipeline_runs",
            "stage_runs",
            "artifacts",
            "artifact_blobs",
            "migration_ledger",
            "login_audit",
        ):
            self.assertIn(f"create table if not exists agent_v2.{table}", sql)

    def test_schema_revokes_public_roles_and_enables_rls(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8").lower()

        self.assertIn("revoke all on schema agent_v2 from anon, authenticated", sql)
        self.assertIn("enable row level security", sql)
        self.assertGreaterEqual(sql.count("enable row level security"), 11)

    def test_schema_has_comment_requirement_and_run_idempotency_constraints(self) -> None:
        sql = SCHEMA_SQL.read_text(encoding="utf-8").lower()

        self.assertIn("unique (owner_id, product_id, fingerprint)", sql)
        self.assertIn("unique (owner_id, fingerprint)", sql)
        self.assertIn("unique (owner_id, idempotency_key)", sql)


if __name__ == "__main__":
    unittest.main()
