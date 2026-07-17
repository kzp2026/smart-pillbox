from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from v2.app import NAV_ITEMS, STAGE_NAV_ITEMS, masked_service_summary
from v2.auth import hash_password
from v2.config import AppConfig


class AppStructureTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
