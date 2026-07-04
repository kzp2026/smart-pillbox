from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from scripts.product_knowledge_base import ProductKnowledgeBase, generate_design_package


class ProductKnowledgeBaseTests(unittest.TestCase):
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

    def test_generation_marks_low_evidence_as_needing_review(self) -> None:
        package = generate_design_package(
            target_product="露营咖啡机",
            demand_text="轻便，户外使用。",
            context={"products": [], "requirements": [], "comments": [], "evidence_count": 0},
        )

        self.assertLess(package["quality_score"], 80)
        self.assertEqual(package["quality_status"], "需补充证据")
        self.assertIn("当前知识库证据不足", package["quality_report"]["warnings"][0])

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
