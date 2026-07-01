from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont, ImageOps

from common import ensure_output_dir, resolve_latest_output_path


# =========================
# 1. 视觉输出路径与基础配置
# =========================

PALETTE = {
    "bg": "#F7FAFC",
    "ink": "#102033",
    "muted": "#5C6B7A",
    "line": "#C8D3DF",
    "blue": "#4D8DFF",
    "cyan": "#59C3C3",
    "green": "#64C78A",
    "orange": "#F4A261",
    "red": "#E76F51",
    "white": "#FFFFFF",
    "panel": "#EEF4FA",
    "shadow": "#DDE7F0",
}


# =========================
# 2. 数据读取与字体工具
# =========================

def ensure_previous_outputs(output_dir: Path, product_name: str) -> None:
    mapping_path = output_dir / f"{product_name}_需求功能映射数据库.xlsx"
    scheme_path = output_dir / f"{product_name}产品设计方案.txt"
    root = Path(__file__).resolve().parents[1]

    if not resolve_latest_output_path(mapping_path).exists():
        subprocess.run(
            [sys.executable, str(root / "scripts" / "05_build_mapping_database.py"), "--output-dir", str(output_dir), "--product-name", product_name],
            cwd=root,
            check=True,
        )

    if not resolve_latest_output_path(scheme_path).exists():
        subprocess.run(
            [sys.executable, str(root / "scripts" / "07_generate_design_scheme.py"), "--output-dir", str(output_dir), "--product-name", product_name],
            cwd=root,
            check=True,
        )


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Bold.otf" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in str(text):
        trial = current + char
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = char
    if current:
        lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 8,
) -> int:
    x, y = xy
    line_height = draw.textbbox((0, 0), "国", font=font)[3] + line_gap
    lines = wrap_text(draw, text, font, max_width)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=fill)
    return len(lines) * line_height


def rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 24, width: int = 2) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


# =========================
# 3. PIL 示意图生成（离线备选方案）
# =========================

def create_render_image(path: Path, req_df: pd.DataFrame, product_name: str) -> None:
    """生成简化的产品效果示意图"""
    w, h = 800, 600
    img = Image.new("RGB", (w, h), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    font_title = load_font(28, bold=True)
    font_body = load_font(16)

    # 面板
    rounded_rect(draw, (40, 40, w - 40, h - 40), PALETTE["white"], PALETTE["line"])

    # 标题
    draw.text((w // 2, 80), f"{product_name} 产品效果图", font=font_title, fill=PALETTE["ink"], anchor="mt")

    # 产品简图区域
    rounded_rect(draw, (60, 130, w - 60, 380), PALETTE["panel"], PALETTE["line"], radius=16)
    draw.text((w // 2, 255), f"〔{product_name} 产品主体示意〕", font=load_font(18), fill=PALETTE["muted"], anchor="mm")

    # 底部信息
    top_reqs = req_df.head(4) if not req_df.empty else []
    y_offset = 420
    for i, (_, row) in enumerate(top_reqs.iterrows()):
        tag_x = 80 + (i % 2) * 340
        tag_y = y_offset + (i // 2) * 50
        req_name = row.get("需求名称", row.get("设计机会点", ""))
        draw.text((tag_x, tag_y), f"• {req_name}", font=font_body, fill=PALETTE["ink"])

    draw.text((w // 2, h - 50), "本图由系统自动生成，为示意图（非真实渲染）", font=load_font(12), fill=PALETTE["muted"], anchor="mb")
    img.save(path)


def paste_image_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    image_path: Path,
    box: tuple[int, int, int, int],
    title: str,
) -> None:
    left, top, right, bottom = box
    rounded_rect(draw, box, PALETTE["white"], PALETTE["line"], radius=18)
    draw.text((left + 22, top + 16), title, font=load_font(18, bold=True), fill=PALETTE["ink"])
    if not image_path.exists():
        draw.text(((left + right) // 2, (top + bottom) // 2), "图片尚未生成", font=load_font(15), fill=PALETTE["muted"], anchor="mm")
        return

    try:
        source = Image.open(image_path).convert("RGB")
        target_width = max(1, right - left - 36)
        target_height = max(1, bottom - top - 72)
        fitted = ImageOps.contain(source, (target_width, target_height), Image.Resampling.LANCZOS)
        x = left + (right - left - fitted.width) // 2
        y = top + 58 + (target_height - fitted.height) // 2
        canvas.paste(fitted, (x, y))
    except Exception:
        draw.text(((left + right) // 2, (top + bottom) // 2), "图片读取失败", font=load_font(15), fill=PALETTE["muted"], anchor="mm")


def create_board(path: Path, images: dict[str, Path], req_df: pd.DataFrame, topic_df: pd.DataFrame, product_name: str) -> None:
    """生成产品设计展板"""
    w, h = 1600, 1000
    img = Image.new("RGB", (w, h), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    font_title = load_font(32, bold=True)
    font_section = load_font(20, bold=True)
    font_body = load_font(15)

    rounded_rect(draw, (20, 20, w - 20, 96), PALETTE["blue"])
    draw.text((w // 2, 58), f"{product_name} 产品设计展板", font=font_title, fill=PALETTE["white"], anchor="mm")

    paste_image_panel(img, draw, images["render"], (20, 120, 800, 660), "产品效果图")
    paste_image_panel(img, draw, images["exploded"], (820, 120, 1190, 380), "产品爆炸图")
    paste_image_panel(img, draw, images["detail"], (1210, 120, 1580, 380), "产品细节图")
    paste_image_panel(img, draw, images["three_view"], (820, 400, 1190, 660), "产品三视图")
    paste_image_panel(img, draw, images["usage"], (1210, 400, 1580, 660), "产品使用效果图")

    rounded_rect(draw, (20, 690, 780, 970), PALETTE["white"], PALETTE["line"], radius=18)
    draw.text((42, 710), "核心用户需求", font=font_section, fill=PALETTE["ink"])
    y = 752
    if req_df.empty:
        draw.text((42, y), "暂无需求数据", font=font_body, fill=PALETTE["muted"])
    else:
        for _, row in req_df.head(5).iterrows():
            req_name = row.get("需求名称", row.get("设计机会点", ""))
            importance = row.get("重要度", "")
            text = f"• {req_name}" + (f"（重要度：{importance}）" if str(importance).strip() else "")
            y += draw_wrapped(draw, (42, y), text, font_body, PALETTE["ink"], 710, line_gap=5) + 8

    rounded_rect(draw, (820, 690, 1580, 970), PALETTE["white"], PALETTE["line"], radius=18)
    draw.text((842, 710), "评论主题与设计依据", font=font_section, fill=PALETTE["ink"])
    y = 752
    if topic_df.empty:
        draw_wrapped(draw, (842, y), f"本展板基于{product_name}用户评论分析、需求映射与产品结构方案自动生成。", font_body, PALETTE["muted"], 710)
    else:
        for _, row in topic_df.head(5).iterrows():
            topic_name = row.get("主题名称", "")
            topic_kws = row.get("主题关键词", "")
            y += draw_wrapped(draw, (842, y), f"• {topic_name}：{topic_kws}", font_body, PALETTE["ink"], 710, line_gap=5) + 8

    draw.text((w - 32, h - 12), "基于用户评论数据自动生成", font=load_font(11), fill=PALETTE["muted"], anchor="rb")
    img.save(path)
    print(f"已生成展板：{path}")


def create_simple_placeholder(path: Path, label: str) -> None:
    """生成简单占位图片"""
    w, h = 800, 600
    img = Image.new("RGB", (w, h), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    rounded_rect(draw, (60, 60, w - 60, h - 60), PALETTE["white"], PALETTE["line"])
    draw.text((w // 2, h // 2), f"〔{label}〕", font=load_font(24), fill=PALETTE["muted"], anchor="mm")
    draw.text((w // 2, h - 40), "示意图 — 可替换为AI渲染图", font=load_font(12), fill=PALETTE["muted"], anchor="mb")
    img.save(path)


def create_three_view_placeholder(path: Path, product_name: str) -> None:
    """生成包含正视图、侧视图和俯视图的离线三视图示意图。"""
    w, h = 1200, 620
    img = Image.new("RGB", (w, h), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    draw.text((w // 2, 42), f"{product_name} 产品三视图", font=load_font(28, bold=True), fill=PALETTE["ink"], anchor="mt")

    panels = [
        (50, 110, 390, 540, "正视图", (135, 180, 305, 420)),
        (430, 110, 770, 540, "侧视图", (540, 180, 660, 420)),
        (810, 110, 1150, 540, "俯视图", (895, 245, 1065, 355)),
    ]
    for left, top, right, bottom, label, body_box in panels:
        rounded_rect(draw, (left, top, right, bottom), PALETTE["white"], PALETTE["line"], radius=18)
        draw.text(((left + right) // 2, top + 28), label, font=load_font(18, bold=True), fill=PALETTE["ink"], anchor="mt")
        rounded_rect(draw, body_box, PALETTE["panel"], PALETTE["blue"], radius=24, width=3)
        body_left, body_top, body_right, body_bottom = body_box
        draw.line((body_left, body_bottom + 24, body_right, body_bottom + 24), fill=PALETTE["muted"], width=2)
        draw.line((body_left, body_bottom + 16, body_left, body_bottom + 32), fill=PALETTE["muted"], width=2)
        draw.line((body_right, body_bottom + 16, body_right, body_bottom + 32), fill=PALETTE["muted"], width=2)

    draw.text((w // 2, h - 26), "离线结构示意图；配置图像生成密钥后将自动替换为写实三视图", font=load_font(13), fill=PALETTE["muted"], anchor="mb")
    img.save(path)


# =========================
# 4. AI 真实渲染（OpenAI 兼容接口 / 阿里云百炼 DashScope）
# =========================

def get_image_api_config() -> dict:
    """读取图像生成接口配置。

    Streamlit Cloud 中可配置 IMAGE_API_KEY/OPENAI_API_KEY，或配置国内模型
    DASHSCOPE_API_KEY/QWEN_IMAGE_API_KEY 接入通义万相 / Qwen-Image。
    不建议复用 DeepSeek 等纯文本 LLM 的 LLM_API_KEY，否则图片接口会失败并降级为示意图。
    """
    provider = os.getenv("IMAGE_PROVIDER", "").strip().lower()
    dashscope_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_IMAGE_API_KEY")
    use_dashscope = provider in {"dashscope", "aliyun", "alibaba", "qwen", "qwen-image", "wanx"} or (dashscope_key and provider not in {"openai", "compatible", "openai-compatible"})
    if use_dashscope:
        model = os.getenv("IMAGE_MODEL", "qwen-image")
        return {
            "provider": "dashscope",
            "api_key": dashscope_key,
            "base_url": os.getenv("DASHSCOPE_IMAGE_API_URL", "https://dashscope.aliyuncs.com/api/v1/services/aigc/text2image/image-synthesis"),
            "task_url": os.getenv("DASHSCOPE_TASK_API_URL", "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"),
            "model": model,
            "quality": os.getenv("IMAGE_QUALITY", "standard"),
            "custom_base_url": bool(os.getenv("DASHSCOPE_IMAGE_API_URL")),
        }

    api_key = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("IMAGE_BASE_URL") or None
    model = os.getenv("IMAGE_MODEL", "gpt-image-1")
    default_quality = "medium" if model.startswith("gpt-image") else "standard"
    quality = os.getenv("IMAGE_QUALITY", default_quality)
    return {
        "provider": "openai",
        "api_key": api_key,
        "base_url": base_url,
        "task_url": "",
        "model": model,
        "quality": quality,
        "custom_base_url": bool(base_url),
    }


def compatible_image_size(model: str, size: str) -> str:
    if not model.startswith("gpt-image"):
        return size
    return {
        "1024x1792": "1024x1536",
        "1792x1024": "1536x1024",
    }.get(size, size)


def dashscope_image_size(size: str) -> str:
    return size.replace("x", "*")


def dashscope_request_json(url: str, api_key: str, payload: dict | None = None, async_request: bool = False, timeout: int = 60) -> dict:
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if async_request:
        headers["X-DashScope-Async"] = "enable"
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def download_image_url(image_url: str, output_path: Path) -> bool:
    urllib.request.urlretrieve(image_url, str(output_path))
    return output_path.exists() and output_path.stat().st_size > 0


def generate_dashscope_image(prompt: str, output_path: Path, size: str, config: dict) -> bool:
    api_key = config.get("api_key")
    if not api_key:
        return False

    try:
        response = dashscope_request_json(
            config["base_url"],
            api_key,
            {
                "model": config["model"],
                "input": {"prompt": prompt},
                "parameters": {
                    "size": dashscope_image_size(size),
                    "n": 1,
                },
            },
            async_request=True,
        )
        task_id = response.get("output", {}).get("task_id")
        if not task_id:
            raise ValueError(f"DashScope 未返回 task_id：{response}")

        task_url = str(config["task_url"]).format(task_id=task_id)
        deadline = time.time() + int(os.getenv("DASHSCOPE_TIMEOUT_SECONDS", "300"))
        poll_interval = float(os.getenv("DASHSCOPE_POLL_INTERVAL", "3"))
        last_payload = {}
        while time.time() < deadline:
            last_payload = dashscope_request_json(task_url, api_key, None, async_request=False, timeout=60)
            output = last_payload.get("output", {})
            status = output.get("task_status") or output.get("status")
            if status == "SUCCEEDED":
                results = output.get("results") or []
                image_url = results[0].get("url") if results else ""
                if not image_url:
                    raise ValueError(f"DashScope 任务成功但未返回图片 URL：{last_payload}")
                if download_image_url(image_url, output_path):
                    print(f"DashScope写实渲染完成：{output_path}")
                    return True
                return False
            if status in {"FAILED", "CANCELED", "UNKNOWN"}:
                raise ValueError(f"DashScope 任务失败：{last_payload}")
            time.sleep(poll_interval)
        raise TimeoutError(f"DashScope 任务超时：{last_payload}")
    except (urllib.error.URLError, TimeoutError, ValueError, KeyError, IndexError) as e:
        print(f"DashScope图片生成失败，已回退为离线示意图：{e}")
        return False


def generate_openai_image(prompt: str, output_path: Path, size: str, config: dict) -> bool:
    """使用 OpenAI Images 兼容接口生成真实感渲染图。"""
    api_key = config.get("api_key")
    if not api_key:
        return False

    try:
        from openai import OpenAI
    except Exception:
        return False

    try:
        model = config["model"]
        client = OpenAI(api_key=api_key, base_url=config.get("base_url") or None)

        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=compatible_image_size(model, size),
            quality=config["quality"],
            n=1,
        )
        image_data = response.data[0]
        image_url = getattr(image_data, "url", None)
        if image_url:
            import urllib.request
            urllib.request.urlretrieve(image_url, str(output_path))
            print(f"AI渲染完成：{output_path}")
            return True

        image_base64 = getattr(image_data, "b64_json", None)
        if image_base64:
            output_path.write_bytes(base64.b64decode(image_base64))
            print(f"AI渲染完成：{output_path}")
            return True
    except Exception as e:
        print(f"图片模型生成失败，已回退为离线示意图：{e}")

    return False


def generate_ai_image(prompt: str, output_path: Path, size: str = "1024x1024") -> bool:
    """按配置选择 OpenAI 兼容接口或阿里云百炼 DashScope 生成真实感渲染图。"""
    config = get_image_api_config()
    if config["provider"] == "dashscope":
        return generate_dashscope_image(prompt, output_path, size, config)
    return generate_openai_image(prompt, output_path, size, config)


def structure_prompt_context(struct_df: pd.DataFrame) -> str:
    """把产品结构表压缩为适合图像提示词使用的部件清单。"""
    if struct_df.empty:
        return "根据产品功能合理拆分外壳、承力结构、连接件和功能组件"

    components = []
    for _, row in struct_df.head(12).iterrows():
        name = str(row.get("结构名称", "")).strip()
        description = str(row.get("结构描述", "")).strip()
        if name:
            components.append(f"{name}（{description}）" if description else name)
    return "、".join(components) or "根据产品功能合理拆分关键结构组件"


def collect_prompt_terms(df: pd.DataFrame, columns: list[str], limit: int = 8) -> list[str]:
    terms: list[str] = []
    if df.empty:
        return terms
    for column in columns:
        if column not in df.columns:
            continue
        for value in df[column].dropna().astype(str).tolist():
            for item in value.replace("，", "、").replace(",", "、").replace("|", "、").split("、"):
                clean = item.strip()
                if clean and clean.lower() != "nan" and clean not in terms:
                    terms.append(clean)
                if len(terms) >= limit:
                    return terms
    return terms


def product_specific_constraints(product_name: str) -> str:
    """为容易跑偏的产品类型补充负向约束，减少模型把同名部件生成成其他物品。"""
    name = product_name.strip()
    if "马桶" in name and "扶手" in name:
        return (
            "必须是安装在马桶侧边或墙面的如厕安全扶手系统；统一外观为白色 U 型双横杆扶手、"
            "灰色防滑握持垫、银色金属墙面固定座和可见螺丝。不得生成水龙头、花洒、毛巾架、门把手、"
            "床边护栏、普通栏杆或单根黑色管件。"
        )
    if "药盒" in name:
        return "必须是同一款分格药盒或智能药盒，不得生成耳机盒、收纳盒、化妆盒或厨房容器。"
    return f"必须始终表现同一款{name}，不得生成其他品类、替代产品或与{name}无关的对象。"


def build_product_consistency_lock(product_name: str, req_df: pd.DataFrame, struct_df: pd.DataFrame) -> str:
    """生成所有写实图共用的产品身份锁，保证同一产品只改变视角和场景。"""
    need_terms = collect_prompt_terms(req_df, ["需求主题", "需求描述", "来源关键词"], limit=8)
    structure_terms = collect_prompt_terms(struct_df, ["结构名称", "结构描述"], limit=10)
    need_text = "、".join(need_terms) if need_terms else "安全、易用、稳定、符合目标用户痛点"
    structure_text = "、".join(structure_terms) if structure_terms else structure_prompt_context(struct_df)
    specific_constraints = product_specific_constraints(product_name)

    return f"""【统一产品设计锁定】
所有六张图片必须表现同一款“{product_name}”，只能改变镜头视角、拆解方式、展板排版和使用场景，不得改变产品本体。
固定产品身份：{product_name}。
固定需求特征：{need_text}。
固定结构特征：{structure_text}。
固定视觉规则：同一轮廓、同一主色、同一材料质感、同一关键部件数量、同一安装方式、同一尺寸比例、同一操作区域；产品效果图、爆炸图、细节图、三视图、设计展板和使用效果图必须互相对应。
负向约束：{specific_constraints}
Consistency lock: same exact product design, same silhouette, same component count, same colors, same materials, same mounting method, same proportions across all images; only camera angle, exploded separation, close-up crop, presentation board layout and usage scene may change."""


def attach_consistency_lock_to_prompts(prompt_lines: list[str], consistency_lock: str) -> list[str]:
    """把同一份产品身份锁注入每条实际发送给图像模型的 prompt。"""
    lock = "\n".join(line.strip() for line in consistency_lock.splitlines() if line.strip())
    locked_prompts = []
    for prompt in prompt_lines:
        clean_prompt = prompt.strip()
        if not clean_prompt:
            continue
        if lock in clean_prompt:
            locked_prompts.append(clean_prompt)
        else:
            locked_prompts.append(f"{lock}\n\n镜头任务：{clean_prompt}")
    return locked_prompts


def build_image_prompts(product_name: str, req_df: pd.DataFrame, struct_df: pd.DataFrame) -> str:
    """构建 AI 图像生成提示词"""
    top_keywords = ""
    if not req_df.empty and "来源关键词" in req_df.columns:
        all_kws = []
        for _, row in req_df.head(5).iterrows():
            kws = str(row.get("来源关键词", ""))
            all_kws.append(kws)
        top_keywords = "、".join(all_kws[:3]) if all_kws else ""

    structure_context = structure_prompt_context(struct_df)
    consistency_lock = build_product_consistency_lock(product_name, req_df, struct_df)

    return f"""# {product_name} 产品设计图像生成提示词

## 统一产品一致性设计锁
{consistency_lock}

## 1. 产品效果图
Prompt: 严格遵守“统一产品设计锁定”，专业的{product_name}产品设计渲染图，展示同一款产品的整体外观、固定结构、材质、配色和核心功能模块，干净的白色背景，柔和的工作室灯光，高品质工业设计摄影风格，photorealistic，industrial design visualization，no logo，no watermark

## 2. 产品爆炸图
Prompt: 严格遵守“统一产品设计锁定”，{product_name}产品结构爆炸图，必须拆解同一款产品而不是重新设计新产品，严格依据以下部件进行拆分：{structure_context}。所有零部件沿垂直装配轴依次分离悬浮，保持正确装配顺序、统一透视、等距间隔且互不遮挡，清晰展示外壳、承力结构、连接方式和功能组件之间的装配关系；右侧设置简洁部件名称与水平引导线，白色背景，等距轴测视角，照片级工业设计产品渲染，engineering exploded view，photorealistic，industrial design visualization，no logo，no watermark

## 3. 产品细节图
Prompt: 严格遵守“统一产品设计锁定”，{product_name}产品细节特写渲染图，只放大同一款产品上的关键功能组件、连接方式、操作界面、人体工学细节和材质工艺，不能替换为不同造型或不同产品，微距摄影品质，干净背景，photorealistic，industrial design visualization，no logo，no watermark

## 4. 产品三视图
Prompt: 严格遵守“统一产品设计锁定”，{product_name}工业设计三视图，同一产品以统一比例展示正视图、侧视图和俯视图，三个正交视图水平排列并严格对齐，准确呈现同一轮廓、同一结构分区、同一操作区域与主要尺寸关系，白色背景，无透视变形，orthographic projection，photorealistic，industrial design visualization，no logo，no watermark

## 5. 设计展板
Prompt: 严格遵守“统一产品设计锁定”，{product_name}产品设计研究生课题展板，展板中的效果图、爆炸图、细节图、三视图和使用效果图必须是同一款产品，包含需求分析和功能结构映射，学术展示风格，信息层级清晰，photorealistic，industrial design visualization，no logo，no watermark

## 6. 产品使用效果图
Prompt: 严格遵守“统一产品设计锁定”，真实目标用户在自然生活场景中使用同一款{product_name}的照片级渲染图，产品本体必须与产品效果图、爆炸图、细节图和三视图保持一致，准确展示人物动作、产品尺度、空间关系和核心功能，温馨自然光线，现代真实环境，photorealistic，industrial design visualization，no logo，no watermark

---
关键词参考：{top_keywords}
"""


def get_prompt_llm_config() -> tuple[str | None, str | None, str]:
    """读取用于优化渲染提示词的 DeepSeek 配置。"""
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    api_key = deepseek_key or os.getenv("LLM_API_KEY")
    if deepseek_key:
        return (
            api_key,
            os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            os.getenv("DEEPSEEK_MODEL", "deepseek-v4-flash"),
        )
    return api_key, os.getenv("LLM_BASE_URL") or None, os.getenv("LLM_MODEL", "deepseek-v4-flash")


def maybe_enhance_image_prompts(
    base_prompts: str,
    product_name: str,
    req_df: pd.DataFrame,
    topic_df: pd.DataFrame,
    struct_df: pd.DataFrame,
) -> tuple[str, str]:
    """使用 DeepSeek 将分析结果转成更专业的工业设计渲染提示词。"""
    api_key, base_url, model = get_prompt_llm_config()
    if not api_key:
        return base_prompts, "规则模板"

    try:
        from openai import OpenAI
    except Exception:
        return base_prompts, "规则模板（缺少 openai 依赖）"

    requirements = req_df.head(8).to_dict(orient="records") if not req_df.empty else []
    topics = topic_df.head(6).to_dict(orient="records") if not topic_df.empty else []
    structures = struct_df.head(12).to_dict(orient="records") if not struct_df.empty else []
    consistency_lock = build_product_consistency_lock(product_name, req_df, struct_df)
    prompt = f"""你是工业设计师和产品可视化提示词专家。请基于以下真实分析数据，为{product_name}生成六类写实产品渲染提示词。

用户需求：{requirements}
评论主题：{topics}
产品结构：{structures}
统一产品设计锁定：{consistency_lock}

要求：
1. 不得把产品误写成智能药盒或其他产品。
2. 六条提示词必须表现同一款产品：同一轮廓、同一颜色、同一材料、同一部件数量、同一安装方式和同一尺寸比例；只能改变视角、拆解、特写、展板排版和使用场景。
3. 每条 Prompt 都必须明确写入“严格遵守统一产品设计锁定”。
4. 产品效果图要说明造型、材质、颜色、核心结构、视角、灯光和背景。
5. 爆炸图必须严格使用“产品结构”中的真实部件，沿装配轴分层拆开并保持正确装配关系。
6. 产品细节图要展示关键连接、操作界面、材料工艺和人体工学细节。
7. 产品三视图必须包含统一比例且严格对齐的正视图、侧视图和俯视图，不得使用透视视角。
8. 设计展板要整合效果图、爆炸图、细节图、三视图、使用效果图和需求要点，避免难以辨认的大段文字。
9. 产品使用效果图要描述真实目标用户、动作、空间关系和使用环境。
10. 每条提示词都必须强调 photorealistic、industrial design visualization、no logo、no watermark。
11. 严格按下列 Markdown 格式输出，只能包含六个章节，每个章节恰好一行以 Prompt: 开头的完整提示词：

## 1. 产品效果图
Prompt: ...
## 2. 产品爆炸图
Prompt: ...
## 3. 产品细节图
Prompt: ...
## 4. 产品三视图
Prompt: ...
## 5. 设计展板
Prompt: ...
## 6. 产品使用效果图
Prompt: ...
"""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "只依据给定数据生成工业设计渲染提示词，不得编造产品类型。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.4,
        )
        content = response.choices[0].message.content or ""
        prompt_lines = [line for line in content.splitlines() if line.strip().startswith("Prompt:")]
        if len(prompt_lines) == 6:
            return f"# {product_name} 产品设计图像生成提示词\n\n{content.strip()}\n", f"DeepSeek增强：{model}"
    except Exception as exc:
        print(f"DeepSeek 提示词增强失败，使用规则模板：{exc}")

    return base_prompts, "规则模板"


def extract_prompt_lines(prompts_text: str) -> list[str]:
    """按固定顺序提取六类图片提示词。"""
    prompts = []
    for line in prompts_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Prompt:"):
            prompts.append(stripped.split("Prompt:", 1)[1].strip())
    return prompts


# =========================
# 5. 主流程
# =========================

def main() -> None:
    parser = argparse.ArgumentParser(description="第八阶段：生成设计图片与展板")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--product-name", default="产品", help="产品名称")
    parser.add_argument("--ai-render", action="store_true", help="使用 AI 生成真实渲染图（需配置 IMAGE_API_KEY 或 OPENAI_API_KEY）")
    args = parser.parse_args()

    product_name = args.product_name
    image_config = get_image_api_config()
    image_api_key = image_config.get("api_key")
    image_model = image_config.get("model")
    image_quality = image_config.get("quality")
    image_provider = image_config.get("provider")
    use_ai = args.ai_render or bool(image_api_key)

    output_dir = ensure_output_dir(args.output_dir)
    ensure_previous_outputs(output_dir, product_name)
    image_dir = output_dir / "design_images"
    image_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = output_dir / f"{product_name}_需求功能映射数据库.xlsx"
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    req_df = read_sheet(mapping_path, "用户需求表")
    topic_df = read_sheet(topic_path, "主题汇总")
    struct_df = read_sheet(mapping_path, "产品结构表")

    # 定义输出图片路径
    images = {
        "render": image_dir / f"{product_name}产品效果图.png",
        "exploded": image_dir / f"{product_name}爆炸图.png",
        "detail": image_dir / f"{product_name}细节图.png",
        "three_view": image_dir / f"{product_name}产品三视图.png",
        "board": image_dir / f"{product_name}产品设计展板.png",
        "usage": image_dir / f"{product_name}产品使用效果图.png",
    }

    # 生成图像提示词
    consistency_lock = build_product_consistency_lock(product_name, req_df, struct_df)
    base_prompts = build_image_prompts(product_name, req_df, struct_df)
    prompts_text, prompt_method = maybe_enhance_image_prompts(
        base_prompts, product_name, req_df, topic_df, struct_df
    )
    prompt_path = image_dir / "设计图像生成提示词.txt"
    prompt_path.write_text(prompts_text, encoding="utf-8")
    consistency_lock_path = image_dir / "产品一致性设计锁.txt"
    consistency_lock_path.write_text(consistency_lock, encoding="utf-8")
    print(f"渲染提示词生成方式：{prompt_method}")

    # 尝试 AI 渲染
    ai_results = {
        "render": False,
        "exploded": False,
        "detail": False,
        "three_view": False,
        "usage": False,
    }
    if use_ai:
        print(f"尝试 AI 真实渲染，供应商：{image_provider}，图像模型：{image_model}")
        # 准备各图片的专用 prompt
        prompt_lines = attach_consistency_lock_to_prompts(
            extract_prompt_lines(prompts_text), consistency_lock
        )
        ai_results["render"] = generate_ai_image(
            prompt_lines[0],
            images["render"], "1024x1024"
        ) if prompt_lines else False

        ai_results["exploded"] = generate_ai_image(
            prompt_lines[1],
            images["exploded"], "1024x1792"
        ) if len(prompt_lines) > 1 else False

        ai_results["detail"] = generate_ai_image(
            prompt_lines[2],
            images["detail"], "1024x1024"
        ) if len(prompt_lines) > 2 else False

        ai_results["three_view"] = generate_ai_image(
            prompt_lines[3],
            images["three_view"], "1792x1024"
        ) if len(prompt_lines) > 3 else False

        ai_results["usage"] = generate_ai_image(
            prompt_lines[5],
            images["usage"], "1024x1024"
        ) if len(prompt_lines) > 5 else False
    else:
        print("未配置 IMAGE_API_KEY、OPENAI_API_KEY、DASHSCOPE_API_KEY 或 QWEN_IMAGE_API_KEY，设计图片将生成离线示意图；如需写实渲染，请在 Streamlit Cloud Secrets 中配置图像生成密钥。")

    # 回退到 PIL 示意图
    if not ai_results["render"]:
        print("生成 PIL 示意图...")
        create_render_image(images["render"], req_df, product_name)

    if not ai_results["detail"]:
        create_simple_placeholder(images["detail"], f"{product_name} 细节图")

    if not ai_results["exploded"]:
        create_simple_placeholder(images["exploded"], f"{product_name} 产品爆炸图")

    if not ai_results["three_view"]:
        create_three_view_placeholder(images["three_view"], product_name)

    if not ai_results["usage"]:
        create_simple_placeholder(images["usage"], f"{product_name} 产品使用效果图")

    create_board(images["board"], images, req_df, topic_df, product_name)

    ai_success_count = sum(ai_results.values())
    render_status = {
        "image_api_configured": bool(image_api_key),
        "provider": image_provider if image_api_key else None,
        "model": image_model if image_api_key else None,
        "quality": image_quality if image_api_key else None,
        "custom_base_url": bool(image_config.get("custom_base_url")),
        "ai_success_count": ai_success_count,
        "ai_target_count": len(ai_results),
        "consistency_lock_file": str(consistency_lock_path.name),
        "images": ai_results,
    }
    status_path = image_dir / "写实渲染状态.json"
    status_path.write_text(json.dumps(render_status, ensure_ascii=False, indent=2), encoding="utf-8")
    if use_ai:
        print(f"AI写实渲染成功：{ai_success_count}/{len(ai_results)}")

    # 生成图片清单
    manifest = pd.DataFrame([
        {"图像类型": "产品效果图", "文件路径": str(images["render"]), "用途": f"展示{product_name}整体外观与核心功能"},
        {"图像类型": "产品爆炸图", "文件路径": str(images["exploded"]), "用途": f"展示{product_name}零部件、装配顺序与结构关系"},
        {"图像类型": "产品细节图", "文件路径": str(images["detail"]), "用途": f"展示{product_name}关键组件与材质工艺"},
        {"图像类型": "产品三视图", "文件路径": str(images["three_view"]), "用途": f"展示{product_name}正视图、侧视图和俯视图"},
        {"图像类型": "产品设计展板", "文件路径": str(images["board"]), "用途": "用于论文答辩、课程展示或设计汇报"},
        {"图像类型": "产品使用效果图", "文件路径": str(images["usage"]), "用途": f"展示{product_name}真实使用场景"},
        {"图像类型": "图像生成提示词", "文件路径": str(prompt_path), "用途": "可复制到图像生成模型进一步渲染"},
        {"图像类型": "产品一致性设计锁", "文件路径": str(consistency_lock_path), "用途": "约束六类写实渲染图保持同一款产品"},
        {"图像类型": "写实渲染状态", "文件路径": str(status_path), "用途": "记录图片模型、成功数量和回退状态"},
    ])
    manifest_path = image_dir / "设计图像清单.xlsx"
    with pd.ExcelWriter(manifest_path, engine="openpyxl") as writer:
        manifest.to_excel(writer, sheet_name="设计图像清单", index=False)

    print(f"产品名称：{product_name}")
    print(f"设计图片输出目录：{image_dir}")
    for label, img_path in images.items():
        if img_path.exists():
            print(f"已生成：{img_path}")
    print(f"已生成：{prompt_path}")
    print(f"已生成：{consistency_lock_path}")
    print(f"已生成：{manifest_path}")


if __name__ == "__main__":
    main()
