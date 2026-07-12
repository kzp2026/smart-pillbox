from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from scripts.visual_asset_quality import evaluate_visual_asset


class VisualAssetQualityTests(unittest.TestCase):
    def test_rejects_a_contact_sheet_for_single_product_assets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "contact-sheet.png"
            image = Image.new("RGB", (900, 900), "white")
            draw = ImageDraw.Draw(image)
            for x in (300, 600):
                draw.rectangle((x - 10, 0, x + 10, 900), fill="#f6f6f6")
            for y in (300, 600):
                draw.rectangle((0, y - 10, 900, y + 10), fill="#f6f6f6")
            for row in range(3):
                for column in range(3):
                    left = column * 300 + 65
                    top = row * 300 + 90
                    draw.rounded_rectangle((left, top, left + 170, top + 120), radius=22, fill="#aab7c7")
            image.save(image_path)

            result = evaluate_visual_asset(image_path, "render")

        self.assertFalse(result["accepted"])
        self.assertIn("多宫格", result["reason"])

    def test_rejects_contact_sheets_for_second_render_and_usage_images(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "contact-sheet.png"
            image = Image.new("RGB", (900, 900), "white")
            draw = ImageDraw.Draw(image)
            for x in (300, 600):
                draw.rectangle((x - 10, 0, x + 10, 900), fill="#f6f6f6")
            for y in (300, 600):
                draw.rectangle((0, y - 10, 900, y + 10), fill="#f6f6f6")
            image.save(image_path)

            render_result = evaluate_visual_asset(image_path, "render_2")
            usage_result = evaluate_visual_asset(image_path, "usage_2")

        self.assertFalse(render_result["accepted"])
        self.assertFalse(usage_result["accepted"])

    def test_accepts_a_single_product_frame(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "single-product.png"
            image = Image.new("RGB", (900, 900), "#f7f8fa")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((180, 290, 720, 590), radius=70, fill="#aab7c7")
            draw.rounded_rectangle((235, 340, 665, 530), radius=42, outline="#dfe7ef", width=8)
            image.save(image_path)

            result = evaluate_visual_asset(image_path, "render")

        self.assertTrue(result["accepted"])

    def test_allows_engineering_layouts_for_three_view_and_board(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "three-view.png"
            image = Image.new("RGB", (900, 600), "white")
            draw = ImageDraw.Draw(image)
            for x in (300, 600):
                draw.rectangle((x - 4, 0, x + 4, 600), fill="#eeeeee")
            image.save(image_path)

            result = evaluate_visual_asset(image_path, "three_view")

        self.assertTrue(result["accepted"])


if __name__ == "__main__":
    unittest.main()
