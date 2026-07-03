from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class AppTabsTests(unittest.TestCase):
    def test_new_app_keeps_legacy_stage_tabs_visible(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for label in [
            "评论清洗",
            "关键词提取",
            "情感分析",
            "主题聚类",
            "需求映射",
            "Neo4j图谱",
            "AI生成参数",
            "设计方案",
            "设计图片",
            "方案评价",
            "下载中心",
        ]:
            self.assertIn(label, app_source)


if __name__ == "__main__":
    unittest.main()
