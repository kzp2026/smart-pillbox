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

    def test_rejects_duplicate_second_render_and_usage_view(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "render-1.png"
            duplicate_path = root / "render-2.png"
            image = Image.new("RGB", (900, 900), "#f7f8fa")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((180, 290, 720, 590), radius=70, fill="#aab7c7")
            image.save(reference_path)
            image.save(duplicate_path)

            render_result = evaluate_visual_asset(duplicate_path, "render_2", reference_image=reference_path)
            usage_result = evaluate_visual_asset(duplicate_path, "usage_2", reference_image=reference_path)

        self.assertFalse(render_result["accepted"])
        self.assertFalse(usage_result["accepted"])
        self.assertIn("过于相似", render_result["reason"])

    def test_rejects_exploded_view_made_from_repeated_trays(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "repeated-trays.png"
            image = Image.new("RGB", (720, 1200), "#f4f4f2")
            draw = ImageDraw.Draw(image)
            for top in (140, 370, 600, 830):
                draw.rounded_rectangle((150, top, 570, top + 145), radius=30, fill="#7f9b78", outline="#35533b", width=8)
                for offset in (105, 210, 315):
                    draw.line((150 + offset, top + 8, 150 + offset, top + 137), fill="#35533b", width=7)
            image.save(image_path)

            result = evaluate_visual_asset(image_path, "exploded")

        self.assertFalse(result["accepted"])
        self.assertIn("重复托盘", result["reason"])

    def test_accepts_exploded_view_with_distinct_internal_components(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "real-components.png"
            image = Image.new("RGB", (720, 1200), "#f4f4f2")
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle((150, 100, 570, 215), radius=28, outline="#6f8c78", width=10)
            draw.rounded_rectangle((170, 280, 550, 405), radius=24, fill="#91a88e", outline="#3e6247", width=7)
            draw.rounded_rectangle((205, 470, 515, 555), radius=10, fill="#356b45")
            draw.rectangle((245, 595, 475, 690), fill="#b9bdc5", outline="#555b66", width=6)
            draw.ellipse((290, 735, 430, 875), fill="#34373b")
            draw.rounded_rectangle((145, 930, 575, 1060), radius=30, fill="#e1e3e6", outline="#737982", width=8)
            image.save(image_path)

            result = evaluate_visual_asset(image_path, "exploded")

        self.assertTrue(result["accepted"])


if __name__ == "__main__":
    unittest.main()
