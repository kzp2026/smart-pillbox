from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class AppTabsTests(unittest.TestCase):
    def test_main_app_keeps_primary_flow_tabs_visible(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for label in [
            "导入评论资产",
            "需求生成",
            "知识库概览",
            "结果预览",
            "下载中心",
            "旧版结果",
        ]:
            self.assertIn(label, app_source)

    def test_main_app_keeps_runtime_feedback_and_dashscope_key_session_state(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            'key="dashscope_api_key_shared"',
            "正在读取并解析上传文件",
            "正在导入评论资产",
            "正在检索知识库并生成方案",
            "设计方案预览",
            "生图提示词",
            "效果图预览",
            "latest_image_path",
            "render_main_result_preview",
        ]:
            self.assertIn(snippet, app_source)

    def test_legacy_result_page_keeps_legacy_stage_tabs_visible(self) -> None:
        page_source = (ROOT_DIR / "pages" / "03_旧版结果预览.py").read_text(encoding="utf-8")
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
        ]:
            self.assertIn(label, page_source)


if __name__ == "__main__":
    unittest.main()
