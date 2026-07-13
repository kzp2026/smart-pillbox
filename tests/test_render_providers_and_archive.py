from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))
sys.path.insert(0, str(ROOT_DIR / "scripts"))


def load_design_visuals_module():
    spec = importlib.util.spec_from_file_location("design_visuals", ROOT_DIR / "scripts" / "08_generate_design_visuals.py")
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


class RenderProviderAndArchiveTests(unittest.TestCase):
    def test_wan_27_pro_uses_multimodal_reference_generation(self) -> None:
        module = load_design_visuals_module()
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            body = json.loads(request.data.decode("utf-8"))
            content = body["input"]["messages"][0]["content"]
            self.assertEqual(body["model"], "wan2.7-image-pro")
            self.assertEqual(body["parameters"]["size"], "1024*1024")
            self.assertNotIn("prompt_extend", body["parameters"])
            self.assertNotIn("negative_prompt", body["parameters"])
            self.assertTrue(any("image" in item for item in content))
            return FakeResponse(
                {"output": {"choices": [{"message": {"content": [{"image": "https://example.com/wan.png"}]}}]}}
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            reference_path = root / "reference.png"
            output_path = root / "output.png"
            reference_path.write_bytes(b"PNG")
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "wan2.7-image-pro",
                "multimodal_url": "https://example.com/multimodal-generation/generation",
                "strict_reference": True,
            }
            with patch.object(module, "image_to_data_url", return_value="data:image/png;base64,UE5H"):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                        ok = module.generate_ai_image(
                            "same product reference", output_path, "1024x1024", reference_path=reference_path, config=config
                        )

        self.assertTrue(ok)
        self.assertEqual(len(requests), 1)

    def test_dashscope_rate_quota_is_waited_and_retried(self) -> None:
        module = load_design_visuals_module()
        attempts = []

        def fake_urlopen(request, timeout=0):
            attempts.append(request)
            if len(attempts) == 1:
                body = io.BytesIO(b'{"code":"Throttling.RateQuota","message":"Requests rate limit exceeded"}')
                raise urllib.error.HTTPError(request.full_url, 429, "Too Many Requests", {"Retry-After": "0"}, body)
            return FakeResponse(
                {"output": {"choices": [{"message": {"content": [{"image": "https://example.com/retry.png"}]}}]}}
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "output.png"
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "qwen-image-2.0-pro-2026-06-22",
                "multimodal_url": "https://example.com/multimodal-generation/generation",
                "rate_limit_attempts": 2,
                "rate_limit_wait": 0,
            }
            with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                    with patch("time.sleep") as sleep:
                        ok = module.generate_dashscope_multimodal_image(
                            "product render", output_path, "1024x1024", config, reference_path=None
                        )

        self.assertTrue(ok)
        self.assertEqual(len(attempts), 2)
        sleep.assert_called()

    def test_dashscope_model_pacing_matches_provider_quota(self) -> None:
        module = load_design_visuals_module()

        self.assertGreaterEqual(module.dashscope_min_request_interval("qwen-image-2.0-pro-2026-06-22"), 30)
        self.assertLessEqual(module.dashscope_min_request_interval("wan2.7-image-pro"), 0.25)

    def test_dashscope_provider_uses_reference_image_model_by_default(self) -> None:
        module = load_design_visuals_module()
        requests = []

        def fake_urlopen(request, timeout=0):
            requests.append(request)
            url = request.full_url
            if url.endswith("/multimodal-generation/generation"):
                body = json.loads(request.data.decode("utf-8"))
                self.assertEqual(body["model"], "qwen-image-2.0-pro-2026-06-22")
                self.assertIn("messages", body["input"])
                self.assertEqual(body["parameters"]["size"], "1024*1024")
                self.assertNotEqual(request.headers.get("X-dashscope-async"), "enable")
                return FakeResponse({"output": {"choices": [{"message": {"content": [{"image": "https://example.com/render.png"}]}}]}})
            raise AssertionError(f"unexpected url {url}")

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "render.png"
            with patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key", "IMAGE_PROVIDER": "dashscope", "IMAGE_MODEL": "qwen-image"}, clear=False):
                with patch("urllib.request.urlopen", side_effect=fake_urlopen):
                    with patch("urllib.request.urlretrieve", side_effect=lambda url, filename: Path(filename).write_bytes(b"PNG")):
                        ok = module.generate_ai_image("产品写实渲染", output_path, "1024x1024")

            self.assertTrue(ok)
            self.assertEqual(output_path.read_bytes(), b"PNG")
            self.assertEqual(len(requests), 1)

    def test_strict_reference_mode_never_falls_back_to_text_only_generation(self) -> None:
        module = load_design_visuals_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_path = root / "output.png"
            reference_path = root / "reference.png"
            reference_path.write_bytes(b"PNG")
            config = {
                "provider": "dashscope",
                "api_key": "test-key",
                "model": "qwen-image-2.0-pro-2026-06-22",
                "strict_reference": True,
            }
            with patch.object(module, "generate_dashscope_multimodal_image", return_value=False):
                with patch.object(module, "generate_dashscope_image") as text_only:
                    ok = module.generate_ai_image(
                        "same product only",
                        output_path,
                        "1024x1024",
                        reference_path=reference_path,
                        config=config,
                    )

        self.assertFalse(ok)
        text_only.assert_not_called()

    def test_result_archive_round_trip_and_path_traversal_rejected(self) -> None:
        from scripts.result_archive import build_result_archive, extract_result_archive

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            output_dir = root / "run"
            (output_dir / "design_images").mkdir(parents=True)
            (output_dir / "uploaded_comments.csv").write_text("评论\n好用", encoding="utf-8")
            (output_dir / "ai_generation_parameters.json").write_text("{}", encoding="utf-8")
            (output_dir / "design_images" / "图.png").write_bytes(b"PNG")

            archive_bytes = build_result_archive(output_dir, "马桶扶手")
            restored_dir = extract_result_archive(archive_bytes, root / "runs", "马桶扶手")

            self.assertTrue((restored_dir / "uploaded_comments.csv").exists())
            self.assertTrue((restored_dir / "design_images" / "图.png").exists())

            bad_archive = io.BytesIO()
            with zipfile.ZipFile(bad_archive, "w") as zf:
                zf.writestr("../evil.txt", "bad")
            with self.assertRaises(ValueError):
                extract_result_archive(bad_archive.getvalue(), root / "runs", "马桶扶手")


if __name__ == "__main__":
    unittest.main()
