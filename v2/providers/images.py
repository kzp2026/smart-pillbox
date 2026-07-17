from __future__ import annotations

import importlib.util
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    name: str
    size: str
    reference_path: str = ""


@dataclass(frozen=True)
class ImageResult:
    succeeded: bool
    data: bytes
    mime_type: str
    provider: str
    model: str
    error: str = ""


class ExistingImageProvider:
    def __init__(self, config: dict, module_loader: Callable[[], object] | None = None) -> None:
        self._config = dict(config)
        self.provider = str(config.get("provider") or "unknown")
        self.model = str(config.get("model") or "unknown")
        self._module_loader = module_loader or self._load_existing_module

    def generate(self, request: ImageGenerationRequest) -> ImageResult:
        try:
            module = self._module_loader()
            with tempfile.TemporaryDirectory() as temp_dir:
                output_path = Path(temp_dir) / Path(request.name).name
                reference = Path(request.reference_path) if request.reference_path else None
                succeeded = bool(
                    module.generate_ai_image(
                        request.prompt,
                        output_path,
                        request.size,
                        reference_path=reference,
                        config=self._config,
                    )
                )
                if not succeeded or not output_path.exists():
                    return ImageResult(False, b"", "image/png", self.provider, self.model, "图片生成未返回有效文件。")
                return ImageResult(True, output_path.read_bytes(), "image/png", self.provider, self.model)
        except Exception as exc:
            message = str(exc)
            api_key = str(self._config.get("api_key") or "")
            if api_key:
                message = message.replace(api_key, "[REDACTED]")
            return ImageResult(False, b"", "image/png", self.provider, self.model, message[:300])

    @staticmethod
    def _load_existing_module() -> object:
        root = Path(__file__).resolve().parents[2]
        module_path = root / "scripts" / "08_generate_design_visuals.py"
        if str(root / "scripts") not in sys.path:
            sys.path.insert(0, str(root / "scripts"))
        spec = importlib.util.spec_from_file_location("v2_existing_design_visuals", module_path)
        if not spec or not spec.loader:
            raise RuntimeError("无法加载现有图片生成模块。")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
