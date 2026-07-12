from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageStat


STRUCTURED_LAYOUT_ASSETS = {"three_view", "board"}


def is_single_product_asset(asset_key: str) -> bool:
    """Views that must contain one coherent product, not a tiled layout."""
    return asset_key.startswith("render") or asset_key.startswith("usage") or asset_key in {"exploded", "detail"}


def _separator_centers(image: Image.Image, axis: str) -> list[float]:
    grayscale = image.convert("L").resize((180, 180), Image.Resampling.BILINEAR)
    width, height = grayscale.size
    line_length = height if axis == "vertical" else width
    line_count = width if axis == "vertical" else height
    candidates: list[int] = []

    for index in range(line_count):
        ratio = index / max(line_count - 1, 1)
        if not 0.18 <= ratio <= 0.82:
            continue
        values = [grayscale.getpixel((index, point)) for point in range(height)] if axis == "vertical" else [grayscale.getpixel((point, index)) for point in range(width)]
        mean = sum(values) / line_length
        variance = sum((value - mean) ** 2 for value in values) / line_length
        if 235 <= mean <= 252 and variance <= 64:
            candidates.append(index)

    groups: list[list[int]] = []
    for index in candidates:
        if groups and index == groups[-1][-1] + 1:
            groups[-1].append(index)
        else:
            groups.append([index])

    return [sum(group) / len(group) / line_count for group in groups if 2 <= len(group) <= 12]


def _looks_like_contact_sheet(image: Image.Image) -> bool:
    vertical = _separator_centers(image, "vertical")
    horizontal = _separator_centers(image, "horizontal")
    return len(vertical) >= 2 and len(horizontal) >= 2


def evaluate_visual_asset(image_path: Path, asset_key: str) -> dict[str, object]:
    """Reject obvious contact sheets before they are presented as product renders."""
    if not image_path.exists() or image_path.stat().st_size == 0:
        return {"accepted": False, "reason": "图片文件不存在或为空"}

    try:
        with Image.open(image_path) as opened:
            image = opened.convert("RGB")
            width, height = image.size
            variance = max(ImageStat.Stat(image).var)
    except Exception:
        return {"accepted": False, "reason": "图片无法读取"}

    if width < 128 or height < 128:
        return {"accepted": False, "reason": "图片尺寸过小"}

    if is_single_product_asset(asset_key) and variance < 12:
        return {"accepted": False, "reason": "图片内容过于空白"}

    if is_single_product_asset(asset_key) and _looks_like_contact_sheet(image):
        return {"accepted": False, "reason": "检测到疑似多宫格或拼贴图"}

    return {
        "accepted": True,
        "reason": "通过基础视觉验收",
        "width": width,
        "height": height,
    }
