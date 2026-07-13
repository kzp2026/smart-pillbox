from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageChops, ImageStat


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


def _exploded_layer_signatures(image: Image.Image) -> list[Image.Image]:
    width = 160
    height = max(220, round(width * image.height / max(image.width, 1)))
    resized = image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
    corner = max(8, width // 16)
    border_samples = [
        resized.crop((0, 0, corner, corner)),
        resized.crop((width - corner, 0, width, corner)),
        resized.crop((0, height - corner, corner, height)),
        resized.crop((width - corner, height - corner, width, height)),
    ]
    medians = [ImageStat.Stat(sample).median for sample in border_samples]
    background = tuple(round(sum(sample[channel] for sample in medians) / len(medians)) for channel in range(3))
    difference = ImageChops.difference(resized, Image.new("RGB", resized.size, background)).convert("L")
    mask = difference.point(lambda value: 255 if value >= 16 else 0)

    active_rows = []
    for y in range(height):
        foreground = sum(1 for x in range(width) if mask.getpixel((x, y)) > 0)
        if foreground / width >= 0.12:
            active_rows.append(y)

    groups: list[list[int]] = []
    for y in active_rows:
        if groups and y <= groups[-1][-1] + 2:
            groups[-1].append(y)
        else:
            groups.append([y])

    signatures: list[Image.Image] = []
    for group in groups:
        top, bottom = group[0], group[-1] + 1
        if bottom - top < max(10, round(height * 0.035)):
            continue
        layer_mask = mask.crop((0, top, width, bottom))
        bbox = layer_mask.getbbox()
        if not bbox or bbox[2] - bbox[0] < width * 0.28:
            continue
        crop = resized.crop((bbox[0], top + bbox[1], bbox[2], top + bbox[3]))
        signatures.append(crop.resize((72, 36), Image.Resampling.BILINEAR))
    return signatures


def _looks_like_repeated_exploded_layers(image: Image.Image) -> bool:
    width = 160
    height = max(220, round(width * image.height / max(image.width, 1)))
    resized = image.convert("RGB").resize((width, height), Image.Resampling.BILINEAR)
    colored_density: list[float] = []
    for y in range(height):
        colored_pixels = 0
        for x in range(width):
            pixel = resized.getpixel((x, y))
            if max(pixel) - min(pixel) >= 12 and max(pixel) <= 242:
                colored_pixels += 1
        colored_density.append(colored_pixels / width)
    smoothed = [
        sum(colored_density[max(0, y - 3) : min(height, y + 4)])
        / len(colored_density[max(0, y - 3) : min(height, y + 4)])
        for y in range(height)
    ]
    minimum_peak_distance = max(14, round(height * 0.055))
    colored_peaks: list[int] = []
    for y in sorted(range(height), key=lambda row: smoothed[row], reverse=True):
        if smoothed[y] < 0.35:
            break
        if all(abs(y - peak) >= minimum_peak_distance for peak in colored_peaks):
            colored_peaks.append(y)
    if len(colored_peaks) >= 4:
        band_radius = max(9, round(height * 0.04))
        colored_bands = [
            resized.crop((0, max(0, peak - band_radius), width, min(height, peak + band_radius + 1))).resize(
                (72, 24), Image.Resampling.BILINEAR
            )
            for peak in colored_peaks
        ]
        similar_pairs = 0
        linked_peaks: set[int] = set()
        for left in range(len(colored_bands)):
            for right in range(left + 1, len(colored_bands)):
                difference = ImageStat.Stat(ImageChops.difference(colored_bands[left], colored_bands[right])).mean
                normalized = sum(difference) / (len(difference) * 255)
                if normalized <= 0.085:
                    similar_pairs += 1
                    linked_peaks.update((left, right))
        if similar_pairs >= 3 and len(linked_peaks) >= 3:
            return True

    signatures = _exploded_layer_signatures(image)
    if len(signatures) < 3:
        return False
    similar_pairs = 0
    linked_layers: set[int] = set()
    for left in range(len(signatures)):
        for right in range(left + 1, len(signatures)):
            difference = ImageStat.Stat(ImageChops.difference(signatures[left], signatures[right])).mean
            normalized = sum(difference) / (len(difference) * 255)
            if normalized <= 0.13:
                similar_pairs += 1
                linked_layers.update((left, right))
    return similar_pairs >= 2 and len(linked_layers) >= 3


def _visual_difference(image: Image.Image, reference_image: Path) -> float | None:
    try:
        with Image.open(reference_image) as opened:
            reference = opened.convert("RGB")
        current = image.convert("L").resize((48, 48), Image.Resampling.LANCZOS)
        baseline = reference.convert("L").resize((48, 48), Image.Resampling.LANCZOS)
        return ImageStat.Stat(ImageChops.difference(current, baseline)).mean[0] / 255
    except Exception:
        return None


def evaluate_visual_asset(
    image_path: Path,
    asset_key: str,
    reference_image: Path | None = None,
) -> dict[str, object]:
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

    if asset_key == "exploded" and _looks_like_repeated_exploded_layers(image):
        return {"accepted": False, "reason": "检测到重复托盘或重复外壳层，爆炸图必须展示真实且不同的内部零件"}

    if asset_key != "exploded" and is_single_product_asset(asset_key) and _looks_like_contact_sheet(image):
        return {"accepted": False, "reason": "检测到疑似多宫格或拼贴图"}

    if asset_key in {"render_2", "usage_2"} and reference_image and reference_image.exists():
        difference = _visual_difference(image, reference_image)
        if difference is not None and difference <= 0.025:
            return {"accepted": False, "reason": "与同组第一张图片过于相似，请生成不同视角或场景"}

    return {
        "accepted": True,
        "reason": "通过基础视觉验收",
        "width": width,
        "height": height,
    }
