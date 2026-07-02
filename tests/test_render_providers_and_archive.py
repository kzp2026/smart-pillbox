from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
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
