from __future__ import annotations

import ast
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from streamlit.testing.v1 import AppTest

from v2.app import (
    NAV_ITEMS,
    STAGE_NAV_ITEMS,
    _cached_run_detail,
    _cached_runs,
    _invalidate_view_cache,
    _workspace_snapshot,
    masked_service_summary,
    secret_configuration_template,
)
from v2.auth import hash_password
from v2.config import AppConfig
from v2.adapters.postgres import KnowledgeRepository
from v2.domain.models import WorkspaceSnapshot


class AppStructureTests(unittest.TestCase):
    def test_navigation_rerun_reuses_repository_and_workspace_snapshot(self) -> None:
        initialize_calls: list[str] = []
        snapshot_calls: list[str] = []
        original_initialize = KnowledgeRepository.initialize
        original_snapshot = KnowledgeRepository.workspace_snapshot

        def counting_initialize(repository: KnowledgeRepository) -> None:
            initialize_calls.append(repository.database_url)
            original_initialize(repository)

        def counting_snapshot(repository: KnowledgeRepository):
            snapshot_calls.append(repository.database_url)
            return original_snapshot(repository)

        with tempfile.TemporaryDirectory() as temp_dir, mock.patch.object(
            KnowledgeRepository, "initialize", counting_initialize
        ), mock.patch.object(KnowledgeRepository, "workspace_snapshot", counting_snapshot):
            app = self._logged_in_app(Path(temp_dir) / "private.sqlite3")
            navigation = next(item for item in app.sidebar.radio if item.label == "工作台导航")
            navigation.set_value("AI 效果图").run()

        self.assertEqual(len(initialize_calls), 1)
        self.assertEqual(len(snapshot_calls), 1)

    def test_ai_image_page_defers_large_artifact_bytes_until_preview_is_requested(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        start = source.index("def _render_images(")
        end = source.index("\ndef _zip_run(", start)
        render_images_source = source[start:end]

        self.assertNotIn("_current_detail(st_module, history, include_data=False)", render_images_source)
        self.assertIn("页面切换不自动读取大图", render_images_source)
        self.assertIn("加载效果图预览", render_images_source)
        self.assertIn('data_mime_prefixes=("image/",)', render_images_source)

    def test_graph_and_design_pages_do_not_preload_archived_artifact_bytes(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        graph_start = source.index("def _render_graph(")
        design_start = source.index("def _render_design(")
        prompt_start = source.index("def _render_prompt(")

        self.assertIn("include_data=False", source[graph_start:design_start])
        self.assertIn("include_data=False", source[design_start:prompt_start])

    def test_overview_results_are_scoped_to_the_active_product(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        start = source.index("def _render_overview(")
        end = source.index("\ndef _create_import_run(", start)
        overview_source = source[start:end]

        self.assertIn("active = _active_product(st_module)", overview_source)
        self.assertIn("_cached_runs(history, 8, active)", overview_source)
        self.assertNotIn("_cached_runs(history, 8)\n", overview_source)

    def test_overview_uses_real_navigation_buttons_and_product_selector(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("设为当前产品", source)
        self.assertIn("打开导入评论", source)
        self.assertIn("打开需求生成", source)
        self.assertIn("打开数据分析", source)
        self.assertIn("打开效果图", source)

    def test_paid_image_generation_defaults_to_full_visual_delivery(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        start = source.index("def _render_demand(")
        end = source.index("\ndef _render_artifact(", start)

        self.assertIn('"效果图数量",\n            "image_count",\n            8,', source[start:end])
        self.assertIn("完整套图默认 8 张", source[start:end])
        self.assertIn("最大付费调用数量", source[start:end])

    def test_demand_draft_survives_page_switches_and_defaults_to_full_visual_delivery(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        start = source.index("def _render_demand(")
        end = source.index("\ndef _render_artifact(", start)
        demand_source = source[start:end]

        self.assertIn("v2_demand_draft", source)
        self.assertIn("_v2_demand_", source)
        self.assertIn("完整套图默认 8 张", demand_source)
        self.assertIn("_demand_selectbox", demand_source)
        self.assertIn("_set_active_product(st_module, command.target_product)", demand_source)
        self.assertIn("v2_current_run_id\"] = run.id", demand_source)

    def test_initialization_failure_has_safe_recovery_actions(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("重新连接私有服务", source)
        self.assertIn("打开 Streamlit 应用管理", source)
        self.assertIn("连接地址、数据库密码或 Supabase 连接池凭据", source)

    def test_custom_mascot_is_not_rendered(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("mascot_html", source)

    def test_history_has_decision_and_filter_controls(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        for label in ("运行状态", "生成模型", "仅看有图片", "结果决策", "对比两个版本"):
            self.assertIn(label, source)

    def test_archive_restore_requires_product_assignment(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("恢复到产品", source)
        self.assertNotIn('CreateRunCommand("恢复的历史结果"', source)

    def test_import_exposes_optional_metadata_mapping_and_admin_grouping(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        for label in ("评分列（可选）", "评论日期列（可选）", "产品版本列（可选）", "渠道列（可选）", "用户标签列（可选）"):
            self.assertIn(label, source)
        self.assertIn("管理员工具 · 原站数据复制", source)

    def test_app_bootstrap_avoids_new_domain_type_imports_during_hot_reload(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = {
            alias.name
            for node in tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "v2.domain.models"
            for alias in node.names
        }

        self.assertNotIn("WorkspaceSnapshot", imported_names)

    def test_image_job_registry_has_a_hot_reload_safe_runtime_fallback(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertNotIn("IMAGE_JOB_REGISTRY as _IMAGE_JOB_REGISTRY", source)
        self.assertIn("getattr(_runtime_state, \"IMAGE_JOB_REGISTRY\"", source)

    def _logged_in_app(self, database: Path) -> AppTest:
        app = AppTest.from_file(
            str(Path(__file__).resolve().parents[2] / "v2" / "app.py"),
            default_timeout=20,
        )
        app.secrets.update(
            {
                "V2_USERNAME": "owner",
                "V2_PASSWORD_HASH": hash_password("correct-password", salt=b"0" * 16),
                "V2_DATABASE_URL": f"sqlite:///{database}",
            }
        )
        app.run()
        app.text_input[0].input("owner")
        app.text_input[1].input("correct-password")
        next(item for item in app.button if item.label == "安全登录").click().run()
        return app

    def test_navigation_preserves_all_seven_stage_groups(self) -> None:
        self.assertEqual(
            STAGE_NAV_ITEMS,
            (
                "导入评论资产",
                "需求生成",
                "知识库概览",
                "需求-功能-结构图谱",
                "设计方案",
                "工业设计 Prompt",
                "AI 效果图",
            ),
        )
        self.assertEqual(NAV_ITEMS[-2:], ("历史记录", "设置与迁移"))

    def test_service_summary_never_returns_secret_values(self) -> None:
        config = AppConfig.from_mapping(
            {
                "V2_USERNAME": "owner",
                "V2_PASSWORD_HASH": "scrypt$hash-secret",
                "V2_DATABASE_URL": "sqlite:///private.sqlite3",
                "V2_DEEPSEEK_API_KEY": "deepseek-raw-secret",
                "V2_IMAGE_API_KEY": "image-raw-secret",
            }
        )

        summary = str(masked_service_summary(config))

        self.assertNotIn("deepseek-raw-secret", summary)
        self.assertNotIn("image-raw-secret", summary)
        self.assertIn("已配置", summary)

    def test_streamlit_smoke_login_opens_private_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            database = Path(temp_dir) / "private.sqlite3"
            app = self._logged_in_app(database)

            self.assertEqual([], list(app.exception))
            navigation = next(item for item in app.sidebar.radio if item.label == "工作台导航")
            self.assertEqual(tuple(navigation.options), NAV_ITEMS)
            mobile_navigation = next(item for item in app.selectbox if item.label == "移动端导航")
            self.assertEqual(tuple(mobile_navigation.options), NAV_ITEMS)
            self.assertTrue(any("知识库概览" in item.value for item in app.markdown))

    def test_demand_draft_and_generated_results_survive_navigation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._logged_in_app(Path(temp_dir) / "private.sqlite3")
            navigation = next(item for item in app.sidebar.radio if item.label == "工作台导航")
            navigation.set_value("需求生成").run()

            self.assertFalse(next(item for item in app.selectbox if item.label == "图片供应商").disabled)
            self.assertFalse(next(item for item in app.selectbox if item.label == "图片模型").disabled)

            next(item for item in app.text_input if item.label == "目标产品").input("持久化验证产品")
            next(item for item in app.text_area if item.label == "本次设计需求").input("验证切换页面后内容保留，并生成可查看的设计结果。").run()
            next(item for item in app.number_input if item.label == "效果图数量").set_value(0).run()

            navigation.set_value("知识库概览").run()
            navigation.set_value("需求生成").run()
            self.assertEqual(
                next(item for item in app.text_input if item.label == "目标产品").value,
                "持久化验证产品",
            )
            self.assertEqual(
                next(item for item in app.text_area if item.label == "本次设计需求").value,
                "验证切换页面后内容保留，并生成可查看的设计结果。",
            )

            next(item for item in app.button if item.label == "生成任务预览").click().run()
            next(item for item in app.button if item.label == "确认并开始生成").click().run()
            self.assertEqual([], list(app.exception))

            navigation.set_value("设计方案").run()
            self.assertTrue(any("持久化验证产品" in item.value for item in app.markdown))
            navigation.set_value("工业设计 Prompt").run()
            self.assertTrue(any("统一产品设计锁定" in item.value for item in app.code))
            navigation.set_value("需求-功能-结构图谱").run()
            self.assertTrue(any("本次已生成图谱" in item.value for item in app.markdown))

    def test_every_navigation_page_renders_without_private_data(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._logged_in_app(Path(temp_dir) / "private.sqlite3")
            for page in NAV_ITEMS:
                navigation = next(item for item in app.sidebar.radio if item.label == "工作台导航")
                navigation.set_value(page).run()
                self.assertEqual([], list(app.exception), page)

    def test_import_page_exposes_full_and_single_stage_execution(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("运行全部 10 个阶段", source)
        self.assertIn("运行选中阶段", source)
        self.assertIn("LEGACY_STAGES", source)

    def test_sidebar_exposes_a_direct_dashscope_image_key_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._logged_in_app(Path(temp_dir) / "private.sqlite3")

            key_button = next(
                item for item in app.sidebar.button if item.label == "配置百炼效果图 Key"
            )
            key_button.click().run()

            self.assertEqual([], list(app.exception))
            self.assertTrue(any("百炼效果图 Key 配置" in item.value for item in app.markdown))
            self.assertTrue(any("这里只处理阿里云百炼效果图 Key" in item.value for item in app.sidebar.caption))

    def test_header_exposes_current_product_context(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("current_product_context_html", source)
        self.assertIn("product_name=_active_product(st_module)", source)
        self.assertIn("image_key_configured=bool(config.image_api_key)", source)

    def test_history_explicitly_scopes_records_to_current_product(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "v2" / "app.py").read_text(encoding="utf-8")

        self.assertIn("当前仅显示", source)
        self.assertIn("其他产品默认隐藏", source)

    def test_secret_template_uses_placeholders_instead_of_current_keys(self) -> None:
        config = AppConfig.from_mapping(
            {
                "V2_USERNAME": "owner",
                "V2_PASSWORD_HASH": "scrypt$hash-secret",
                "V2_DATABASE_URL": "sqlite:///private.sqlite3",
                "V2_DEEPSEEK_API_KEY": "deepseek-raw-secret",
                "V2_IMAGE_API_KEY": "image-raw-secret",
            }
        )

        template = secret_configuration_template(config)

        self.assertNotIn("V2_DEEPSEEK_API_KEY", template)
        self.assertIn("V2_IMAGE_API_KEY", template)
        self.assertNotIn("deepseek-raw-secret", template)
        self.assertNotIn("image-raw-secret", template)

    def test_navigation_and_history_reads_are_reused_until_a_write_invalidates_them(self) -> None:
        class FakeRepository:
            database_url = "sqlite:///cache-integration.sqlite3"
            owner_id = "private-owner"
            schema = "agent_v2"

            def __init__(self) -> None:
                self.snapshot_calls = 0

            def workspace_snapshot(self) -> WorkspaceSnapshot:
                self.snapshot_calls += 1
                return WorkspaceSnapshot(product_count=self.snapshot_calls)

        class FakeHistory:
            def __init__(self, repository: FakeRepository) -> None:
                self.repository = repository
                self.list_calls = 0
                self.detail_calls = 0

            def list_runs(self, limit: int):
                self.list_calls += 1
                return [f"run-{limit}"]

            def reopen(self, run_id: str, include_artifact_data: bool = False):
                self.detail_calls += 1
                return (run_id, include_artifact_data)

        repository = FakeRepository()
        history = FakeHistory(repository)
        _invalidate_view_cache(repository)  # type: ignore[arg-type]

        self.assertEqual(_workspace_snapshot(repository).product_count, 1)  # type: ignore[arg-type]
        self.assertEqual(_workspace_snapshot(repository).product_count, 1)  # type: ignore[arg-type]
        self.assertEqual(_cached_runs(history, 50), ["run-50"])  # type: ignore[arg-type]
        self.assertEqual(_cached_runs(history, 50), ["run-50"])  # type: ignore[arg-type]
        self.assertEqual(_cached_run_detail(history, "run-1", True), ("run-1", True))  # type: ignore[arg-type]
        self.assertEqual(_cached_run_detail(history, "run-1", True), ("run-1", True))  # type: ignore[arg-type]

        self.assertEqual(repository.snapshot_calls, 1)
        self.assertEqual(history.list_calls, 1)
        self.assertEqual(history.detail_calls, 1)

        _invalidate_view_cache(repository)  # type: ignore[arg-type]
        self.assertEqual(_workspace_snapshot(repository).product_count, 2)  # type: ignore[arg-type]

    def test_workspace_snapshot_falls_back_for_a_repository_cached_before_deploy(self) -> None:
        class CachedLegacyRepository:
            database_url = "sqlite:///stale-module.sqlite3"
            owner_id = "private-owner"
            schema = "agent_v2"

        repository = CachedLegacyRepository()
        _invalidate_view_cache(repository)  # type: ignore[arg-type]

        snapshot = _workspace_snapshot(repository)  # type: ignore[arg-type]

        self.assertFalse(snapshot.healthy)
        self.assertEqual(snapshot.product_count, 0)


if __name__ == "__main__":
    unittest.main()
