from __future__ import annotations

import tempfile
import unittest
import inspect
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.domain.models import CreateRunCommand, RunStatus


class KnowledgeRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        database_path = Path(self.temp_dir.name) / "agent_v2.sqlite3"
        self.database_url = f"sqlite:///{database_path}"
        self.repo = KnowledgeRepository(self.database_url, owner_id="private-owner")
        self.repo.initialize()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_duplicate_comments_are_idempotent_across_file_and_database(self) -> None:
        first = self.repo.ingest_comments(
            product_name="智能药盒",
            category="适老健康",
            source_filename="first.csv",
            comments=["提醒明显", "提醒明显", "  "],
        )
        second = self.repo.ingest_comments(
            product_name="智能药盒",
            category="适老健康",
            source_filename="second.csv",
            comments=["提醒明显"],
        )

        self.assertEqual(first.input_count, 3)
        self.assertEqual(first.valid_count, 2)
        self.assertEqual(first.inserted_count, 1)
        self.assertEqual(first.duplicate_count, 1)
        self.assertEqual(second.inserted_count, 0)
        self.assertEqual(self.repo.count_rows("comments"), 1)

    def test_duplicate_requirement_evidence_is_stored_once(self) -> None:
        report = self.repo.ingest_comments(
            "智能药盒", "适老健康", "comments.csv", ["提醒声音太小"]
        )

        first_id = self.repo.add_requirement_once(
            product_id=report.product_id,
            batch_id=report.batch_id,
            title="提醒反馈",
            description="提醒要清晰可感知",
            keywords=["提醒", "声音"],
            evidence_text="提醒声音太小",
            score=80,
        )
        second_id = self.repo.add_requirement_once(
            product_id=report.product_id,
            batch_id=report.batch_id,
            title="提醒反馈",
            description="提醒要清晰可感知",
            keywords=["提醒", "声音"],
            evidence_text="提醒声音太小",
            score=80,
        )

        self.assertEqual(first_id, second_id)
        self.assertEqual(self.repo.count_rows("requirements"), 1)

    def test_owner_cannot_see_another_owner_products(self) -> None:
        self.repo.ingest_comments("智能药盒", "适老健康", "a.csv", ["好用"])
        other = KnowledgeRepository(self.database_url, owner_id="other-owner")
        other.initialize()

        self.assertEqual(len(self.repo.list_products()), 1)
        self.assertEqual(other.list_products(), [])

    def test_same_idempotency_key_returns_existing_run(self) -> None:
        command = CreateRunCommand(
            target_product="智能药盒",
            demand_text="提醒老人按时吃药",
            provider="dashscope",
            model="wan2.7-image-pro",
            image_count=8,
        )

        first = self.repo.create_pipeline_run(command, idempotency_key="stable-key")
        second = self.repo.create_pipeline_run(command, idempotency_key="stable-key")

        self.assertEqual(first.id, second.id)
        self.assertEqual(first.status, RunStatus.PENDING)
        self.assertEqual(self.repo.count_rows("pipeline_runs"), 1)

    def test_deleting_product_cascades_comments_and_requirements(self) -> None:
        report = self.repo.ingest_comments("智能药盒", "适老健康", "a.csv", ["提醒声音太小"])
        self.repo.add_requirement_once(
            report.product_id,
            report.batch_id,
            "提醒反馈",
            "提醒要清晰",
            ["提醒"],
            "提醒声音太小",
            80,
        )

        self.assertTrue(self.repo.delete_product(report.product_id))

        self.assertEqual(self.repo.count_rows("products"), 0)
        self.assertEqual(self.repo.count_rows("comments"), 0)
        self.assertEqual(self.repo.count_rows("requirements"), 0)

    def test_update_product_changes_private_metadata_only(self) -> None:
        product_id = self.repo.upsert_product("智能药盒", "适老健康", "第一版")
        other = KnowledgeRepository(self.database_url, owner_id="other-owner")
        other.initialize()

        self.assertTrue(
            self.repo.update_product(product_id, "智能分药助手", "家庭健康", "第二版")
        )
        self.assertFalse(
            other.update_product(product_id, "越权修改", "未知", "不应成功")
        )

        product = self.repo.list_products()[0]
        self.assertEqual(product.name, "智能分药助手")
        self.assertEqual(product.category, "家庭健康")
        self.assertEqual(product.description, "第二版")

    def test_postgres_connection_disables_prepared_statements_for_transaction_poolers(self) -> None:
        source = inspect.getsource(KnowledgeRepository.connect)

        self.assertIn("prepare_threshold=None", source)


if __name__ == "__main__":
    unittest.main()
