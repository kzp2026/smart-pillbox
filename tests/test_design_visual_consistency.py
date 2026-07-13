from __future__ import annotations

import base64
import io
import importlib.util
import os
import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))


def load_design_visuals_module():
    spec = importlib.util.spec_from_file_location(
        "design_visuals", ROOT_DIR / "scripts" / "08_generate_design_visuals.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class DesignVisualConsistencyTests(unittest.TestCase):
    def test_dashscope_error_details_are_preserved_without_exposing_api_key(self) -> None:
        module = load_design_visuals_module()
        events = [
            {
                "image": "render.png",
                "stage": "dashscope_text",
                "status": "failed",
                "message": (
                    'DashScope HTTP 403: {"code":"Arrearage","message":'
                    '"Access denied due to outstanding payment",'
                    '"request_id":"req-123","api_key":"sk-sensitive"}'
                ),
            }
        ]

        details = module.format_image_generation_errors(events)

        self.assertIn("DashScope HTTP 403", details)
        self.assertIn("Arrearage", details)
        self.assertIn("Access denied due to outstanding payment", details)
        self.assertIn("req-123", details)
        self.assertNotIn("sk-sensitive", details)
        self.assertIn("[已隐藏]", details)

    def test_prompts_share_same_product_consistency_lock(self) -> None:
        module = load_design_visuals_module()
        req_df = pd.DataFrame(
            [
                {"需求主题": "安全稳定", "需求描述": "老人如厕起身需要稳定支撑", "来源关键词": "防滑、稳固、老人"},
                {"需求主题": "安装方便", "需求描述": "希望墙面安装牢固", "来源关键词": "安装、方便"},
            ]
        )
        struct_df = pd.DataFrame(
            [
                {"结构名称": "U型双横杆扶手", "结构描述": "提供双手支撑和起身借力"},
                {"结构名称": "墙面金属固定座", "结构描述": "通过螺丝固定在瓷砖墙面"},
            ]
        )

        consistency_lock = module.build_product_consistency_lock("马桶扶手", req_df, struct_df)
        prompts_text = module.build_image_prompts("马桶扶手", req_df, struct_df)
        prompt_lines = module.extract_prompt_lines(prompts_text)
        locked_prompts = module.attach_consistency_lock_to_prompts(prompt_lines, consistency_lock)

        self.assertEqual(len(prompt_lines), 6)
        self.assertEqual(len(locked_prompts), 6)
        self.assertIn("统一产品设计锁定", consistency_lock)
        self.assertIn("白色 U 型双横杆扶手", consistency_lock)
        self.assertIn("不得生成水龙头", consistency_lock)
        for prompt in locked_prompts:
            self.assertIn("统一产品设计锁定", prompt)
            self.assertIn("same exact product design", prompt)
            self.assertIn("马桶扶手", prompt)

    def test_smart_pillbox_lock_blocks_earbud_case_drift(self) -> None:
        module = load_design_visuals_module()
        req_df = pd.DataFrame(
            [{"需求主题": "定时提醒", "需求描述": "老人容易忘记吃药", "来源关键词": "提醒、分格、便携"}]
        )
        struct_df = pd.DataFrame(
            [
                {"结构名称": "七日分格药仓", "结构描述": "按星期和时段分类收纳药片"},
                {"结构名称": "前置提醒屏", "结构描述": "显示时间和服药状态"},
            ]
        )

        consistency_lock = module.build_product_consistency_lock("智能药盒", req_df, struct_df)
        prompts_text = module.build_image_prompts("智能药盒", req_df, struct_df)

        self.assertIn("七日分格药仓", consistency_lock)
        self.assertIn("不得生成耳机盒", consistency_lock)
        self.assertIn("不得生成充电盒", consistency_lock)
        self.assertIn("单一产品主体", prompts_text)
        self.assertIn("不要拼贴图", prompts_text)

    def test_old_qwen_text_model_is_upgraded_to_reference_model(self) -> None:
        module = load_design_visuals_module()
        with patch.dict(
            os.environ,
            {"DASHSCOPE_API_KEY": "test-key", "IMAGE_PROVIDER": "dashscope", "IMAGE_MODEL": "qwen-image"},
            clear=False,
        ):
            config = module.get_image_api_config()

        self.assertEqual(config["model"], "qwen-image-2.0-pro-2026-06-22")
        self.assertTrue(config["force_reference_model"])

    def test_exploded_prompt_requires_single_vertical_technical_stack(self) -> None:
        module = load_design_visuals_module()
        req_df = pd.DataFrame(
            [{"需求主题": "定时提醒", "需求描述": "老人容易忘记吃药", "来源关键词": "提醒、分格、便携"}]
        )
        struct_df = pd.DataFrame(
            [
                {"结构名称": "透明翻盖", "结构描述": "保护药仓"},
                {"结构名称": "七日分格药仓", "结构描述": "分类收纳药片"},
                {"结构名称": "提醒电路板", "结构描述": "控制提醒和显示"},
            ]
        )

        prompt_lines = module.extract_prompt_lines(module.build_image_prompts("智能药盒", req_df, struct_df))
        exploded_prompt = prompt_lines[1]

        self.assertIn("单张完整爆炸图", exploded_prompt)
        self.assertIn("沿中心垂直装配轴", exploded_prompt)
        self.assertIn("从上到下分层悬浮", exploded_prompt)
        self.assertIn("不得生成多宫格", exploded_prompt)
        self.assertIn("不得生成耳机", exploded_prompt)

    def test_board_notes_are_compact_design_description_not_topic_dump(self) -> None:
        module = load_design_visuals_module()
        req_df = pd.DataFrame(
            [
                {"需求主题": "安全提醒", "需求描述": "老人需要按时吃药", "来源关键词": "提醒"},
                {"需求主题": "分区清楚", "需求描述": "药品分类不容易混乱", "来源关键词": "分格"},
                {"需求主题": "携带方便", "需求描述": "出门也能携带", "来源关键词": "便携"},
            ]
        )
        topic_df = pd.DataFrame(
            [{"主题名称": "主题0", "主题关键词": "提醒,分格,老人,定时,声音,灯光,便携,安全,防误服"}]
        )

        notes = module.build_compact_board_notes("智能药盒", req_df, topic_df)

        self.assertLessEqual(len(notes), 4)
        self.assertTrue(all(len(note) <= 36 for note in notes))
        self.assertFalse(any("主题0" in note or "主题关键词" in note for note in notes))

    def test_usage_retry_prevents_hand_product_intersections(self) -> None:
        module = load_design_visuals_module()

        retry_prompt = module.build_retry_variation_prompt("base prompt", "usage_1", 2)

        self.assertIn("visible air gap", retry_prompt)
        self.assertIn("do not touch", retry_prompt)
        self.assertIn("transparent lid", retry_prompt)

    def test_board_palette_tracks_product_color(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            green_path = root / "green.png"
            blue_path = root / "blue.png"
            Image.new("RGB", (320, 240), "#78A98A").save(green_path)
            Image.new("RGB", (320, 240), "#668FC4").save(blue_path)

            green_palette = module.derive_board_palette({"render": green_path})
            blue_palette = module.derive_board_palette({"render": blue_path})

        self.assertNotEqual(green_palette["accent"], blue_palette["accent"])
        self.assertNotEqual(green_palette["background"], blue_palette["background"])
        self.assertGreater(green_palette["accent_rgb"][1], green_palette["accent_rgb"][2])
        self.assertGreater(blue_palette["accent_rgb"][2], blue_palette["accent_rgb"][1])

    def test_pm_review_records_cover_all_design_images(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = {}
            for key in ["render", "exploded", "detail", "three_view", "board", "usage"]:
                image_path = root / f"{key}.png"
                Image.new("RGB", (16, 16), "white").save(image_path)
                images[key] = image_path
            ai_results = {key: True for key in ["render", "exploded", "detail", "three_view", "usage"]}
            records = module.build_pm_image_review_records(
                "智能药盒",
                images,
                ai_results,
                reference_enabled=True,
                consistency_lock="统一产品设计锁定",
            )

        image_types = {record["图像类型"] for record in records}
        self.assertEqual(
            image_types,
            {"产品一致性", "产品效果图", "产品爆炸图", "产品细节图", "产品三视图", "设计展板", "产品使用效果图"},
        )
        self.assertTrue(all(record["PM验收状态"] == "通过" for record in records))
        self.assertTrue(any("同一产品" in record["PM检查项"] for record in records))

    def test_board_template_uses_portrait_reference_style(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            images = {}
            for key in ["render", "exploded", "detail", "three_view", "usage"]:
                image_path = root / f"{key}.png"
                Image.new("RGB", (640, 420), "white").save(image_path)
                images[key] = image_path
            images["board"] = root / "board.png"
            req_df = pd.DataFrame([{"需求主题": "安全提醒", "需求描述": "老人需要按时吃药", "来源关键词": "提醒"}])
            topic_df = pd.DataFrame([{"主题关键词": "提醒,分格,老人,便携"}])

            module.create_board(images["board"], images, req_df, topic_df, "智能药盒")
            with Image.open(images["board"]) as board:
                board_size = board.size

        self.assertEqual(board_size, (1600, 2200))

    def test_board_template_removes_color_analysis_without_blank_area(self) -> None:
        module = load_design_visuals_module()
        labels = module.board_section_labels()

        self.assertNotIn("色彩分析", "".join(labels))
        self.assertNotIn("Color analysis", "".join(labels))
        self.assertIn("结构工艺", "".join(labels))
        self.assertIn("材质分析", "".join(labels))

    def test_engineering_exploded_schematic_is_generated_locally(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "exploded.png"
            struct_df = pd.DataFrame(
                [
                    {"结构名称": "透明翻盖", "结构描述": "保护药仓"},
                    {"结构名称": "七日分格药仓", "结构描述": "分类收纳药片"},
                    {"结构名称": "提醒电路板", "结构描述": "控制提醒和显示"},
                ]
            )
            module.create_exploded_schematic(output_path, "智能药盒", struct_df)
            with Image.open(output_path) as image:
                image_size = image.size

        self.assertEqual(image_size, (1200, 1600))

    def test_product_identity_reference_blocks_unrelated_objects(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "identity.png"
            module.create_product_identity_reference_image(output_path, "智能药盒")
            with Image.open(output_path) as image:
                image_size = image.size

        self.assertEqual(image_size, (1024, 1024))

    def test_dashscope_multimodal_reference_request_uses_reference_image(self) -> None:
        module = load_design_visuals_module()
        requests = []
        timeouts = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            timeouts.append(timeout)
            body = json.loads(request.data.decode("utf-8"))
            content = body["input"]["messages"][0]["content"]
            self.assertEqual(body["model"], "qwen-image-2.0-pro")
            self.assertFalse(body["parameters"]["prompt_extend"])
            self.assertTrue(any("image" in item for item in content))
            self.assertTrue(any("text" in item and "同一款产品" in item["text"] for item in content))
            return FakeResponse({"output": {"choices": [{"message": {"content": [{"image": "https://example.com/ref.png"}]}}]}})

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            output_path = root / "output.png"
            Image.new("RGB", (8, 8), "white").save(reference_path)
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "qwen-image-2.0-pro",
                "multimodal_url": "https://example.com/multimodal-generation/generation",
                "prompt_extend": False,
                "negative_prompt": "collage",
            }
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                    ok = module.generate_dashscope_multimodal_image(
                        "生成同一款产品细节图", output_path, "1024x1024", config, reference_path=reference_path
                    )
            output_bytes = output_path.read_bytes()

        self.assertTrue(ok)
        self.assertEqual(output_bytes, b"PNG")
        self.assertEqual(len(requests), 1)
        self.assertGreaterEqual(timeouts[0], 180)

    def test_reference_image_is_downscaled_and_compressed_before_upload(self) -> None:
        module = load_design_visuals_module()

        with tempfile.TemporaryDirectory() as temp_dir:
            reference_path = Path(temp_dir) / "large-reference.png"
            Image.effect_noise((1800, 1200), 64).convert("RGB").save(reference_path)

            data_url = module.image_to_data_url(reference_path)
            encoded = data_url.split(",", 1)[1]
            with Image.open(io.BytesIO(base64.b64decode(encoded))) as uploaded_image:
                uploaded_size = uploaded_image.size
                uploaded_format = uploaded_image.format

        self.assertTrue(data_url.startswith("data:image/jpeg;base64,"))
        self.assertLessEqual(max(uploaded_size), 1024)
        self.assertEqual(uploaded_format, "JPEG")

    def test_reference_upload_timeout_is_retried(self) -> None:
        module = load_design_visuals_module()
        attempts = []

        def fake_urlopen(request, timeout=0):
            attempts.append(timeout)
            if len(attempts) == 1:
                raise urllib.error.URLError(TimeoutError("The write operation timed out"))
            return FakeResponse(
                {"output": {"choices": [{"message": {"content": [{"image": "https://example.com/ref.png"}]}}]}}
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            output_path = root / "output.png"
            Image.new("RGB", (1600, 1200), "white").save(reference_path)
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "qwen-image-2.0-pro",
                "multimodal_url": "https://example.com/multimodal-generation/generation",
                "prompt_extend": False,
                "negative_prompt": "collage",
            }
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                    with patch("time.sleep"):
                        ok = module.generate_dashscope_multimodal_image(
                            "same product detail", output_path, "1024x1024", config, reference_path=reference_path
                        )

        self.assertTrue(ok)
        self.assertEqual(len(attempts), 2)
        self.assertTrue(all(timeout >= 180 for timeout in attempts))

    def test_second_visual_attempt_forces_a_distinct_composition(self) -> None:
        module = load_design_visuals_module()

        first_attempt = module.build_retry_variation_prompt("base prompt", "render_2", 1)
        second_render_attempt = module.build_retry_variation_prompt("base prompt", "render_2", 2)
        second_usage_attempt = module.build_retry_variation_prompt("base prompt", "usage_2", 2)
        second_exploded_attempt = module.build_retry_variation_prompt("base prompt", "exploded", 2)

        self.assertEqual(first_attempt, "base prompt")
        self.assertIn("camera azimuth", second_render_attempt)
        self.assertIn("rear three-quarter", second_render_attempt)
        self.assertIn("different user action", second_usage_attempt)
        self.assertIn("exactly one medication tray", second_exploded_attempt)
        self.assertIn("PCB", second_exploded_attempt)
        self.assertNotEqual(second_render_attempt, first_attempt)

    def test_reference_failure_retries_text_generation_before_fallback(self) -> None:
        module = load_design_visuals_module()
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            body = json.loads(request.data.decode("utf-8"))
            content = body["input"]["messages"][0]["content"]
            if any("image" in item for item in content):
                return FakeResponse({"output": {"choices": [{"message": {"content": []}}]}})
            return FakeResponse({"output": {"choices": [{"message": {"content": [{"image": "https://example.com/text.png"}]}}]}})

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            output_path = root / "output.png"
            Image.new("RGB", (8, 8), "white").save(reference_path)
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "qwen-image-2.0-pro",
                "multimodal_url": "https://example.com/multimodal-generation/generation",
                "base_url": "https://example.com/image-synthesis",
                "task_url": "https://example.com/tasks/{task_id}",
                "prompt_extend": False,
                "negative_prompt": "collage",
            }
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                    ok = module.generate_ai_image(
                        "生成同一款产品细节图", output_path, "1024x1024", reference_path=reference_path, config=config
                    )

        self.assertTrue(ok)
        self.assertEqual(len(requests), 2)


if __name__ == "__main__":
    unittest.main()
