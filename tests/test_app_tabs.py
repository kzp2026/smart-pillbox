from __future__ import annotations

import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


class AppTabsTests(unittest.TestCase):
    def test_requirements_pin_verified_streamlit_runtime(self) -> None:
        requirements = (ROOT_DIR / "requirements.txt").read_text(encoding="utf-8")
        self.assertIn("streamlit==1.58.0", requirements)

    def test_main_app_handles_cloud_database_startup_failures_without_generic_crash(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            "describe_database_startup_error",
            "except Exception as database_error",
            "系统不会在云数据库异常时自动切换到临时本地数据库",
            "st.stop()",
        ]:
            self.assertIn(snippet, app_source)

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
            '"prompt"',
            "效果图预览",
            "latest_image_paths",
            "get_image_prompts",
            "render_prompt_gallery",
            "visual_assets",
            "build_visual_assets_from_package",
            "统一产品设计锁定",
            "不得生成耳机盒",
            "no collage",
            "generate_visual_asset_set",
            "reference_image",
            "create_exploded_schematic",
            "create_board",
            "产品爆炸图",
            "设计展板",
            "产品使用效果图",
            "下载本次生成 prompt",
            "下载本次效果图",
            "render_main_result_preview",
            "运行版本",
            "safe_generation_payload",
            "生成记录保存失败",
        ]:
            self.assertIn(snippet, app_source)

    def test_main_app_offers_wan_27_pro_for_high_throughput_image_generation(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn('"wan2.7-image-pro"', app_source)
        self.assertLess(app_source.index('"wan2.7-image-pro"'), app_source.index("DEFAULT_IMAGE_MODEL,"))
        self.assertNotIn("生图提示词", app_source)

    def test_main_app_offers_openai_rendering_without_flattening_exploded_view(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            'key="openai_api_key_shared"',
            "OpenAI API Key",
            "OpenAI 写实渲染",
            "gpt-image-2",
            "build_openai_config",
            "render_provider",
            "单张立体写实爆炸图",
            "图像服务生成",
        ]:
            self.assertIn(snippet, app_source)
        self.assertNotIn('if key == "exploded":\n            create_visual_fallback', app_source)

    def test_openai_rendering_keeps_the_product_reference_for_follow_up_views(self) -> None:
        visual_source = (ROOT_DIR / "scripts" / "08_generate_design_visuals.py").read_text(encoding="utf-8")
        self.assertIn("reference_path: Path | None = None", visual_source)
        self.assertIn("client.images.edit", visual_source)
        self.assertIn("reference_path=reference_path", visual_source)

    def test_main_app_rejects_inconsistent_visual_outputs_before_preview(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            "evaluate_visual_asset",
            "MAX_VISUAL_RETRIES",
            "build_reference_locked_prompt",
            "未通过视觉一致性验收",
            "视觉验收未通过",
            "不展示低质量回退图",
        ]:
            self.assertIn(snippet, app_source)

    def test_main_app_exposes_industrial_design_prompt_constraints(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            "工业设计 Prompt 约束",
            "功能需求",
            "产品结构",
            "材料要求",
            "尺寸比例约束",
            "使用场景",
            "视觉风格",
            "禁止修改项",
            "industrial_constraints",
            "industrial_design_prompt",
        ]:
            self.assertIn(snippet, app_source)

    def test_main_app_can_copy_all_prompts_and_checks_view_distinctness(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        for snippet in [
            "复制全部 prompt",
            "navigator.clipboard.writeText",
            "st.html(",
            "unsafe_allow_javascript=True",
            "inspect.signature(st.html).parameters",
            "components.html(",
            "reference_image=distinct_reference",
            "第二张产品效果图必须使用与产品效果图 1 不同的镜头构图",
            "第二张使用效果图必须使用与产品使用效果图 1 不同的使用动作或场景构图",
        ]:
            self.assertIn(snippet, app_source)

    def test_main_app_keeps_scheme_generation_button_clickable(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn('st.button("从知识库生成方案", type="primary", use_container_width=True)', app_source)
        self.assertNotIn('disabled=not target_product.strip()', app_source)
        self.assertIn("请先填写要生成的产品", app_source)

    def test_generation_and_result_views_keep_their_responsibilities_separate(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
        self.assertIn("生成完成，请切换到“结果预览”查看设计方案、完整 prompt 与效果图。", app_source)
        self.assertNotIn('render_prompt_gallery(package, active_image_config, render_provider, "generate_tab_render_all")', app_source)
        self.assertIn("完整 8 条 prompt", app_source)
        self.assertIn("当前渲染服务尚未载入 API Key", app_source)

    def test_image_generation_failure_displays_provider_error_details(self) -> None:
        app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

        self.assertIn("format_image_generation_errors", app_source)
        self.assertIn("阿里云返回的真实错误", app_source)

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
