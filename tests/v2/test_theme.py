from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.ui.theme import asset_data_uri, build_theme_css, default_asset_urls


class ThemeTests(unittest.TestCase):
    def test_runtime_theme_assets_are_encoded_once_per_process(self) -> None:
        self.assertTrue(hasattr(default_asset_urls, "cache_info"))

    def test_asset_data_uri_embeds_real_png_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image = Path(temp_dir) / "asset.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nreal-asset")

            uri = asset_data_uri(image)

        self.assertTrue(uri.startswith("data:image/png;base64,"))
        self.assertNotIn("real-asset", uri)

    def test_theme_matches_neon_dashboard_tokens_and_responsive_contract(self) -> None:
        css = build_theme_css(
            {
                "background": "data:image/png;base64,background",
                "logo": "data:image/png;base64,logo",
                "mascot": "data:image/png;base64,mascot",
            }
        )

        for token in ("#030817", "#168bff", "#24d7df", "#8b5cf6"):
            self.assertIn(token, css)
        self.assertIn("data:image/png;base64,background", css)
        self.assertIn("@media (max-width: 560px)", css)
        self.assertIn(":focus-visible", css)
        self.assertIn(".v2-mascot", css)
        self.assertNotIn("linear-gradient", css)

    def test_native_button_like_controls_share_the_dark_console_palette(self) -> None:
        css = build_theme_css(
            {
                "background": "data:image/png;base64,background",
                "logo": "data:image/png;base64,logo",
                "mascot": "data:image/png;base64,mascot",
            }
        )

        for selector in (
            '[data-testid="stFileUploaderDropzone"] button',
            '[data-testid="stLinkButton"] a',
            '[data-baseweb="input"] button',
            '[data-testid="stCode"] button',
            '.stDownloadButton > button',
        ):
            self.assertIn(selector, css)
        self.assertIn("color-scheme: dark", css)
        self.assertIn("touch-action: manipulation", css)
        self.assertNotIn("transition: all", css)

    def test_runtime_theme_assets_use_small_webp_payloads(self) -> None:
        assets = default_asset_urls()

        self.assertTrue(all(value.startswith("data:image/webp;base64,") for value in assets.values()))
        self.assertLess(sum(len(value) for value in assets.values()), 900_000)


if __name__ == "__main__":
    unittest.main()
