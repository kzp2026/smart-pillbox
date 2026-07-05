from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
import json
import tempfile
import unittest
from pathlib import Path

from scripts.product_knowledge_base import ProductKnowledgeBase, clean_text, generate_design_package, to_json_safe


class ProductKnowledgeBaseTests(unittest.TestCase):
    def test_json_safe_conversion_handles_unknown_database_values(self) -> None:
        class CustomDatabaseValue:
            def __str__(self) -> str:
                return "custom-value"

        payload = {
            "decimal": Decimal("92.5"),
            "date": date(2026, 7, 5),
            "time": time(10, 30),
            "bytes": b"hello",
            "set": {"提醒", "吃药"},
            "custom": CustomDatabaseValue(),
        }

        encoded = json.dumps(to_json_safe(payload), ensure_ascii=False)

        self.assertIn("92.5", encoded)
        self.assertIn("2026-07-05", encoded)
        self.assertIn("hello", encoded)
        self.assertIn("custom-value", encoded)

    def test_clean_text_does_not_boolean_check_database_values(self) -> None:
        class BoolErrorValue:
            def __bool__(self) -> bool:
                raise TypeError("boolean value is ambiguous")

            def __str__(self) -> str:
                return " 可 清洗 文本 "

        self.assertEqual(clean_text(BoolErrorValue()), "可 清洗 文本")

    def test_ingest_report_counts_inserted_and_duplicate_comments(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = ProductKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()

            first = kb.ingest_comment_batch_with_report(
                product_name="智能药盒",
                category="适老健康",
                source_filename="first.csv",
                comments=["提醒要明显", "提醒要明显", "药仓分格清楚", ""],
            )
            second = kb.ingest_comment_batch_with_report(
                product_name="智能药盒",
                category="适老健康",
                source_filename="second.csv",
                comments=["提醒要明显", "字体要大"],
            )

            self.assertEqual(first["input_count"], 4)
            self.assertEqual(first["valid_count"], 3)
            self.assertEqual(first["inserted_count"], 2)
            self.assertEqual(first["duplicate_in_file_count"], 1)
            self.assertEqual(first["duplicate_existing_count"], 0)
            self.assertEqual(second["valid_count"], 2)
            self.assertEqual(second["inserted_count"], 1)
            self.assertEqual(second["duplicate_existing_count"], 1)

    def test_ingest_uses_bulk_comment_insert_path(self) -> None:
        class BulkOnlyKnowledgeBase(ProductKnowledgeBase):
            def _execute_ignore(self, conn, statement: str, params: tuple) -> None:  # type: ignore[override]
                raise AssertionError("comment import should not execute one SQL statement per comment")

        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = BulkOnlyKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()

            product_id, batch_id = kb.ingest_comment_batch(
                product_name="智能药盒",
                category="适老健康",
                source_filename="bulk.csv",
                comments=["提醒要明显", "提醒要明显", "药仓分格清楚", ""],
            )

            self.assertGreater(product_id, 0)
            self.assertGreater(batch_id, 0)
            context = kb.search_context("提醒 分格", limit=5)
            self.assertEqual(context["evidence_count"], 2)

    def test_ingests_comments_and_retrieves_relevant_context(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = ProductKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()

            product_id, batch_id = kb.ingest_comment_batch(
                product_name="智能药盒",
                category="适老健康",
                source_filename="pillbox.csv",
                comments=[
                    "老人经常忘记吃药，希望药盒可以按时提醒。",
                    "药仓分格要清楚，最好一周七天都能区分。",
                    "屏幕字体要大，父母看起来更轻松。",
                ],
            )
            kb.add_requirement(
                product_id=product_id,
                batch_id=batch_id,
                title="定时提醒",
                description="老人容易忘记服药，需要声音、灯光或屏幕提醒。",
                keywords=["提醒", "老人", "吃药"],
                evidence_text="老人经常忘记吃药，希望药盒可以按时提醒。",
                score=92,
            )

            context = kb.search_context("我要做一个提醒老人按时喝水吃药的智能水杯", limit=5)

            self.assertGreaterEqual(context["evidence_count"], 2)
            self.assertEqual(context["products"][0]["name"], "智能药盒")
            self.assertIn("定时提醒", context["requirements"][0]["title"])
            self.assertTrue(any("忘记吃药" in item["comment_original"] for item in context["comments"]))

    def test_generation_package_contains_evidence_and_quality_gate(self) -> None:
        context = {
            "products": [{"name": "智能药盒", "category": "适老健康", "score": 12}],
            "requirements": [
                {
                    "title": "定时提醒",
                    "description": "老人容易忘记服药，需要明确提醒。",
                    "keywords": "提醒、老人、吃药",
                    "evidence_text": "老人经常忘记吃药，希望药盒可以按时提醒。",
                    "score": 92,
                }
            ],
            "comments": [
                {"product_name": "智能药盒", "comment_original": "屏幕字体要大，父母看起来更轻松。"}
            ],
            "evidence_count": 2,
        }

        package = generate_design_package(
            target_product="智能水杯",
            demand_text="给老人用，提醒喝水吃药，操作简单。",
            context=context,
        )

        self.assertGreaterEqual(package["quality_score"], 80)
        self.assertEqual(package["quality_status"], "达标")
        self.assertIn("评论证据", package["design_text"])
        self.assertIn("定时提醒", package["design_text"])
        self.assertIn("智能水杯", package["image_prompt_text"])
        self.assertEqual(len(package["image_prompts"]), 6)
        self.assertTrue(all("智能水杯" in prompt for prompt in package["image_prompts"]))

    def test_generation_marks_low_evidence_as_needing_review(self) -> None:
        package = generate_design_package(
            target_product="露营咖啡机",
            demand_text="轻便，户外使用。",
            context={"products": [], "requirements": [], "comments": [], "evidence_count": 0},
        )

        self.assertLess(package["quality_score"], 80)
        self.assertEqual(package["quality_status"], "需补充证据")
        self.assertIn("当前知识库证据不足", package["quality_report"]["warnings"][0])

    def test_save_generation_run_accepts_postgres_native_json_values(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = ProductKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()

            context = {
                "query": "智能药盒",
                "requirements": [
                    {
                        "title": "定时提醒",
                        "score": Decimal("92.5"),
                        "created_at": datetime(2026, 7, 5, 10, 30, tzinfo=timezone.utc),
                    }
                ],
                "comments": [],
                "evidence_count": 1,
            }
            result = generate_design_package("智能药盒", "提醒老人吃药", context)

            run_id = kb.save_generation_run("智能药盒", "提醒老人吃药", context, result)

            self.assertGreater(run_id, 0)

    def test_generation_flow_accepts_database_rows_with_native_types(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = ProductKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()
            product_id, batch_id = kb.ingest_comment_batch(
                product_name="智能药盒",
                category="适老健康",
                source_filename="comments.csv",
                comments=["提醒老人吃药，能与手机交互。"],
            )
            kb.add_requirement(
                product_id=product_id,
                batch_id=batch_id,
                title="提醒交互",
                description="提醒要明显，并能把状态同步给家人。",
                keywords=["提醒", "手机", "交互"],
                evidence_text="提醒老人吃药，能与手机交互。",
                score=Decimal("88.5"),
            )

            context = kb.search_context("智能药盒 提醒 手机交互", limit=5)
            context["comments"][0]["created_at"] = datetime(2026, 7, 5, 10, 30, tzinfo=timezone.utc)
            context["comments"][0]["extra"] = {Decimal("1.5"), date(2026, 7, 5)}
            package = generate_design_package("智能药盒", "提醒老人吃药 能与手机交互", context)
            run_id = kb.save_generation_run("智能药盒", "提醒老人吃药 能与手机交互", context, package)

            self.assertGreater(run_id, 0)

    def test_can_update_and_delete_product_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "kb.sqlite3"
            kb = ProductKnowledgeBase(f"sqlite:///{db_path}")
            kb.initialize()

            product_id, batch_id = kb.ingest_comment_batch(
                product_name="Codex持久化验证",
                category="系统验证",
                source_filename="test.csv",
                comments=["这是一条用于确认云数据库持久化写入成功的验证评论。"],
            )
            kb.add_requirement(
                product_id=product_id,
                batch_id=batch_id,
                title="验证需求",
                description="用于测试产品管理。",
                keywords=["验证"],
                evidence_text="验证评论",
                score=60,
            )

            self.assertTrue(kb.update_product(product_id, "智能药盒", "适老健康", "正式产品"))
            products = kb.list_products()
            self.assertEqual(products[0]["name"], "智能药盒")
            self.assertEqual(products[0]["category"], "适老健康")

            kb.upsert_product("保温杯", "厨房电器")
            with self.assertRaises(ValueError):
                kb.update_product(product_id, "保温杯", "适老健康")

            self.assertTrue(kb.delete_product(product_id))
            context = kb.search_context("智能药盒 验证", limit=5)
            self.assertEqual(context["evidence_count"], 0)
            self.assertFalse(any(product["name"] == "智能药盒" for product in kb.list_products()))


if __name__ == "__main__":
    unittest.main()
