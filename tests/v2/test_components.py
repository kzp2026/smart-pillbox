from __future__ import annotations

import unittest

from v2.ui.components import (
    metric_grid_html,
    process_bar_html,
    product_rows_html,
    status_bar_html,
)


class ComponentHtmlTests(unittest.TestCase):
    def test_status_bar_escapes_dynamic_values(self) -> None:
        result = status_bar_html(
            database='<script>alert("db")</script>',
            text_model="deepseek-chat",
            image_model="wan2.1-imageedit",
            healthy=True,
        )

        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)
        self.assertIn("deepseek-chat", result)

    def test_process_bar_has_exactly_seven_accessible_steps(self) -> None:
        result = process_bar_html(active_index=3, completed_indices={0, 1, 2})

        self.assertEqual(7, result.count('class="v2-process-step'))
        self.assertIn('aria-current="step"', result)
        self.assertIn("知识库概览", result)
        self.assertIn("AI 效果图", result)

    def test_metric_and_product_html_escape_user_content(self) -> None:
        metrics = metric_grid_html(
            [
                ("产品资产", "3", "个产品", "blue"),
                ("评论沉淀", "629", "条评论", "cyan"),
            ]
        )
        rows = product_rows_html(
            [
                {
                    "name": '<img src=x onerror="alert(1)">',
                    "comments": 12,
                    "requirements": 3,
                    "updated_at": "2026-07-17",
                }
            ]
        )

        self.assertEqual(2, metrics.count('data-kind="metric"'))
        self.assertNotIn("<img", rows)
        self.assertIn("&lt;img", rows)


if __name__ == "__main__":
    unittest.main()
