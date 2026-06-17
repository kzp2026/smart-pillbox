from __future__ import annotations

import argparse
import base64
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

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
    draw.text((w // 2, 80), f"{product_name} 产品设计效果图", font=font_title, fill=PALETTE["ink"], anchor="mt")

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


def create_board(path: Path, image_dir: Path, req_df: pd.DataFrame, topic_df: pd.DataFrame, product_name: str) -> None:
    """生成产品设计展板"""
    w, h = 1200, 900
    img = Image.new("RGB", (w, h), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    font_title = load_font(32, bold=True)
    font_section = load_font(20, bold=True)
    font_body = load_font(14)

    # 展板标题区
    rounded_rect(draw, (20, 20, w - 20, 100), PALETTE["blue"])
    draw.text((w // 2, 70), f"{product_name} 产品设计展板", font=font_title, fill=PALETTE["white"], anchor="mm")

    # 左栏：需求分析
    rounded_rect(draw, (20, 140, 580, 500), PALETTE["white"], PALETTE["line"])
    draw.text((300, 160), "用户需求分析", font=font_section, fill=PALETTE["ink"], anchor="mt")

    top_reqs = req_df.head(6) if not req_df.empty else []
    y = 200
    for _, row in enumerate(top_reqs.iterrows()):
        row_data = row[1]
        req_name = row_data.get("需求名称", row_data.get("设计机会点", ""))
        importance = row_data.get("重要度", "")
        draw_wrapped(draw, (40, y), f"• {req_name} (重要度: {importance})", font_body, PALETTE["ink"], 520)
        y += 40

    # 右栏：主题聚类
    rounded_rect(draw, (620, 140, w - 20, 500), PALETTE["white"], PALETTE["line"])
    draw.text((900, 160), "评论主题聚类", font=font_section, fill=PALETTE["ink"], anchor="mt")

    y = 200
    top_topics = topic_df.head(6) if not topic_df.empty else []
    for _, row in enumerate(top_topics.iterrows()):
        row_data = row[1]
        topic_name = row_data.get("主题名称", "")
        topic_kws = row_data.get("主题关键词", "")
        draw_wrapped(draw, (640, y), f"• {topic_name}: {topic_kws}", font_body, PALETTE["ink"], 540)
        y += 40

    # 底部：产品设计
    rounded_rect(draw, (20, 660, w - 20, h - 20), PALETTE["white"], PALETTE["line"])
    draw.text((w // 2, 680), "产品设计方案概要", font=font_section, fill=PALETTE["ink"], anchor="mt")

    design_text = (
        f"本展板基于{product_name}用户评论数据的自然语言处理分析结果。"
        "通过TF-IDF关键词提取、情感分析、主题聚类及需求-功能-结构映射，"
        "从用户反馈中系统性推导产品设计方向与机会点。"
    )
    draw_wrapped(draw, (60, 720), design_text, font_body, PALETTE["ink"], 1100)

    draw.text((w // 2, h - 40), "本展板由系统自动生成，为示意图", font=load_font(11), fill=PALETTE["muted"], anchor="mb")
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


# =========================
# 4. AI 真实渲染（DALL-E 兼容接口）
# =========================

def get_image_api_config() -> tuple[str | None, str | None, str]:
    """读取图像生成接口配置。

    Streamlit Cloud 中建议配置 IMAGE_API_KEY 或 OPENAI_API_KEY。
    不建议复用 DeepSeek 等纯文本 LLM 的 LLM_API_KEY，否则图片接口会失败并降级为示意图。
    """
    api_key = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("IMAGE_BASE_URL") or None
    model = os.getenv("IMAGE_MODEL", "dall-e-3")
    return api_key, base_url, model


def generate_ai_image(prompt: str, output_path: Path, size: str = "1024x1024") -> bool:
    """使用 OpenAI Images 兼容接口生成真实感渲染图。"""
    api_key, base_url, model = get_image_api_config()
    if not api_key:
        return False

    try:
        from openai import OpenAI
    except Exception:
        return False

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)

        response = client.images.generate(
            model=model,
            prompt=prompt,
            size=size,
            quality="standard",
            n=1,
        )
        image_url = response.data[0].url
        if image_url:
            import urllib.request
            urllib.request.urlretrieve(image_url, str(output_path))
            print(f"AI渲染完成：{output_path}")
            return True
    except Exception as e:
        print(f"DALL-E 生成失败，尝试备用方式：{e}")

    return False


def build_image_prompts(product_name: str, req_df: pd.DataFrame) -> str:
    """构建 AI 图像生成提示词"""
    top_keywords = ""
    if not req_df.empty and "来源关键词" in req_df.columns:
        all_kws = []
        for _, row in req_df.head(5).iterrows():
            kws = str(row.get("来源关键词", ""))
            all_kws.append(kws)
        top_keywords = "、".join(all_kws[:3]) if all_kws else ""

    return f"""# {product_name} 产品设计图像生成提示词

## 1. 设计效果图
Prompt: 专业的{product_name}产品设计渲染图，展示产品整体外观和核心功能模块，干净的白色背景，柔和的工作室灯光，高品质工业设计摄影风格，无品牌logo，无水印

## 2. 产品细节图
Prompt: {product_name}产品细节特写渲染图，展示关键功能组件和材质质感，微距摄影品质，干净背景，工业设计展示风格

## 3. 使用场景图  
Prompt: 真实生活场景中用户使用{product_name}的照片级渲染图，温馨自然光线，现代家居环境，人物自然互动，充满生活气息

## 4. 产品展板
Prompt: {product_name}产品设计研究生课题展板，包含产品渲染图、需求分析、功能结构映射图表，学术展示风格，信息图表布局清晰

---
关键词参考：{top_keywords}
"""


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
    image_api_key, _, image_model = get_image_api_config()
    use_ai = args.ai_render or bool(image_api_key)

    output_dir = ensure_output_dir(args.output_dir)
    ensure_previous_outputs(output_dir, product_name)
    image_dir = output_dir / "design_images"
    image_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = output_dir / f"{product_name}_需求功能映射数据库.xlsx"
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    req_df = read_sheet(mapping_path, "用户需求表")
    topic_df = read_sheet(topic_path, "主题汇总")

    # 定义输出图片路径
    images = {
        "render": image_dir / f"{product_name}设计效果图.png",
        "detail": image_dir / f"{product_name}细节图.png",
        "scenario": image_dir / f"{product_name}场景使用效果图.png",
        "board": image_dir / f"{product_name}产品设计展板.png",
    }

    # 生成图像提示词
    prompts_text = build_image_prompts(product_name, req_df)
    prompt_path = image_dir / "设计图像生成提示词.txt"
    prompt_path.write_text(prompts_text, encoding="utf-8")

    # 尝试 AI 渲染
    if use_ai:
        print(f"尝试 AI 真实渲染，图像模型：{image_model}")
        # 准备各图片的专用 prompt
        prompt_lines = [l for l in prompts_text.split("\n") if l.startswith("Prompt:")]
        render_ok = generate_ai_image(
            f"Professional product design render of {product_name}, showing overall appearance and core features, clean white background, soft studio lighting, high quality industrial design photography style, no brand logo, no watermark",
            images["render"], "1024x1024"
        ) if prompt_lines else False

        scenario_ok = generate_ai_image(
            f"Photorealistic lifestyle render of a person using {product_name} in a warm modern home setting, natural lighting, clean composition, no brand logo, no watermark",
            images["scenario"], "1024x1024"
        ) if len(prompt_lines) > 1 else False

        board_ok = generate_ai_image(
            f"Graduate research product design presentation board for {product_name}, including product renders, requirement analysis charts, functional-structural mapping diagrams, clean academic layout, Chinese text labels, no watermark",
            images["board"], "1792x1024"
        ) if len(prompt_lines) > 2 else False

        detail_ok = generate_ai_image(
            f"Close-up macro photography style render of {product_name} showing key functional components and material texture, clean background, industrial design showcase style, no brand logo",
            images["detail"], "1024x1024"
        ) if len(prompt_lines) > 3 else False
    else:
        print("未配置 IMAGE_API_KEY 或 OPENAI_API_KEY，设计图片将生成离线示意图；如需写实渲染，请在 Streamlit Cloud Secrets 中配置图像生成密钥。")

    # 回退到 PIL 示意图
    if not images["render"].exists():
        print("生成 PIL 示意图...")
        create_render_image(images["render"], req_df, product_name)

    if not images["detail"].exists():
        create_simple_placeholder(images["detail"], f"{product_name} 细节图")

    if not images["scenario"].exists():
        create_simple_placeholder(images["scenario"], f"{product_name} 场景使用图")

    # 展板始终用 PIL 生成（AI展板效果不稳定）
    create_board(images["board"], image_dir, req_df, topic_df, product_name)

    # 生成图片清单
    manifest = pd.DataFrame([
        {"图像类型": "设计效果图", "文件路径": str(images["render"]), "用途": f"展示{product_name}整体外观与核心功能"},
        {"图像类型": "细节图", "文件路径": str(images["detail"]), "用途": f"展示{product_name}关键组件与材质"},
        {"图像类型": "场景使用效果图", "文件路径": str(images["scenario"]), "用途": f"展示{product_name}真实使用场景"},
        {"图像类型": "产品设计展板", "文件路径": str(images["board"]), "用途": "用于论文答辩、课程展示或设计汇报"},
        {"图像类型": "图像生成提示词", "文件路径": str(prompt_path), "用途": "可复制到图像生成模型进一步渲染"},
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
    print(f"已生成：{manifest_path}")


if __name__ == "__main__":
    main()
