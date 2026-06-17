from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from common import ensure_output_dir


# =========================
# 1. 视觉输出路径与基础配置
# =========================

IMAGE_FILENAMES = {
    "render": "智能药盒设计效果图.png",
    "three_view": "智能药盒三视图.png",
    "exploded": "智能药盒爆炸图.png",
    "scenario": "智能药盒场景使用效果图.png",
    "board": "智能药盒产品设计展板.png",
}

HIGH_FIDELITY_THRESHOLD_BYTES = 500_000

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

def ensure_previous_outputs(output_dir: Path) -> None:
    """如果核心设计数据不存在，自动补跑前序阶段。"""
    mapping_path = output_dir / "智能药盒需求功能映射数据库.xlsx"
    scheme_path = output_dir / "智能药盒产品设计方案.txt"
    root = Path(__file__).resolve().parents[1]

    if not mapping_path.exists():
        subprocess.run(
            [sys.executable, str(root / "scripts" / "05_build_mapping_database.py"), "--output-dir", str(output_dir)],
            cwd=root,
            check=True,
        )

    if not scheme_path.exists():
        subprocess.run(
            [sys.executable, str(root / "scripts" / "07_generate_design_scheme.py"), "--output-dir", str(output_dir)],
            cwd=root,
            check=True,
        )


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """读取 Excel Sheet，不存在时返回空表。"""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """加载中文字体；找不到时使用默认字体。"""
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
    """按像素宽度拆分中文文本。"""
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
    """绘制自动换行文本，并返回文本块高度。"""
    x, y = xy
    line_height = draw.textbbox((0, 0), "国", font=font)[3] + line_gap
    lines = wrap_text(draw, text, font, max_width)
    for i, line in enumerate(lines):
        draw.text((x, y + i * line_height), line, font=font, fill=fill)
    return len(lines) * line_height


def rounded_rect(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], fill: str, outline: str | None = None, radius: int = 24, width: int = 2) -> None:
    """绘制圆角矩形。"""
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def pillbox_body(draw: ImageDraw.ImageDraw, x: int, y: int, w: int, h: int, scale: float = 1.0) -> None:
    """绘制智能药盒主体效果。"""
    shadow = int(18 * scale)
    rounded_rect(draw, (x + shadow, y + shadow, x + w + shadow, y + h + shadow), PALETTE["shadow"], radius=int(34 * scale))
    rounded_rect(draw, (x, y, x + w, y + h), PALETTE["white"], PALETTE["line"], radius=int(34 * scale), width=int(3 * scale))
    rounded_rect(draw, (x + int(28 * scale), y + int(28 * scale), x + w - int(28 * scale), y + int(95 * scale)), "#EAF3FF", None, radius=int(20 * scale))
    draw.text((x + int(48 * scale), y + int(42 * scale)), "Smart Pillbox", font=load_font(int(30 * scale), True), fill=PALETTE["ink"])
    draw.text((x + w - int(190 * scale), y + int(47 * scale)), "微信同步", font=load_font(int(22 * scale)), fill=PALETTE["blue"])

    cell_gap = int(14 * scale)
    cell_w = int((w - 70 * scale - 3 * cell_gap) / 4)
    cell_h = int(118 * scale)
    colors = ["#DFF5E6", "#E2F0FF", "#FFF1D6", "#FCE2DD"]
    labels = ["早", "中", "晚", "睡前"]
    for i in range(4):
        cx = x + int(35 * scale) + i * (cell_w + cell_gap)
        cy = y + int(125 * scale)
        rounded_rect(draw, (cx, cy, cx + cell_w, cy + cell_h), colors[i], "#B8C6D8", radius=int(18 * scale), width=int(2 * scale))
        draw.text((cx + int(26 * scale), cy + int(30 * scale)), labels[i], font=load_font(int(34 * scale), True), fill=PALETTE["ink"])
        draw.ellipse((cx + cell_w - int(42 * scale), cy + int(22 * scale), cx + cell_w - int(20 * scale), cy + int(44 * scale)), fill=PALETTE["green"])

    rounded_rect(draw, (x + int(42 * scale), y + h - int(78 * scale), x + w - int(42 * scale), y + h - int(28 * scale)), "#F5F8FB", "#CCD8E2", radius=int(16 * scale))
    draw.text((x + int(62 * scale), y + h - int(66 * scale)), "语音 + 灯光 + 蜂鸣 + 远程监护", font=load_font(int(22 * scale)), fill=PALETTE["muted"])


def draw_callout(draw: ImageDraw.ImageDraw, anchor: tuple[int, int], target: tuple[int, int], title: str, text: str, width: int = 330) -> None:
    """绘制功能标注气泡。"""
    x, y = anchor
    draw.line((target[0], target[1], x, y + 32), fill=PALETTE["blue"], width=3)
    rounded_rect(draw, (x, y, x + width, y + 118), PALETTE["white"], PALETTE["line"], radius=18)
    draw.text((x + 18, y + 15), title, font=load_font(24, True), fill=PALETTE["ink"])
    draw_wrapped(draw, (x + 18, y + 50), text, load_font(18), PALETTE["muted"], width - 36, 5)


# =========================
# 3. 五类设计图片绘制
# =========================

def create_render_image(path: Path, req_df: pd.DataFrame) -> None:
    """生成产品设计效果图。"""
    # 如果已经存在图像模型生成的高保真立体图，默认保留，避免一键运行时被兜底示意图覆盖。
    if path.exists() and path.stat().st_size >= HIGH_FIDELITY_THRESHOLD_BYTES:
        return

    img = Image.new("RGB", (1600, 1000), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    draw.text((80, 60), "智能药盒产品设计效果图", font=load_font(52, True), fill=PALETTE["ink"])
    draw.text((82, 128), "立体外观 / 多模态提醒 / 分仓防错 / 远程监护 / 适老化交互", font=load_font(28), fill=PALETTE["muted"])

    # 兜底版使用伪 3D 等轴测绘制，让产品有明显厚度、顶面和侧面。
    x, y, w, h = 470, 330, 660, 300
    dx, dy = 95, -72
    front = (x, y, x + w, y + h)
    top_poly = [(x, y), (x + dx, y + dy), (x + w + dx, y + dy), (x + w, y)]
    side_poly = [(x + w, y), (x + w + dx, y + dy), (x + w + dx, y + h + dy), (x + w, y + h)]
    draw.polygon([(x + 35, y + h + 45), (x + w + 150, y + h - 20), (x + w + 120, y + h + 65), (x + 10, y + h + 90)], fill="#DDE7F0")
    draw.polygon(top_poly, fill="#F8FBFF", outline=PALETTE["line"])
    draw.polygon(side_poly, fill="#D6E3EF", outline=PALETTE["line"])
    rounded_rect(draw, front, PALETTE["white"], PALETTE["line"], radius=34, width=3)

    rounded_rect(draw, (x + 36, y + 28, x + w - 36, y + 86), "#EAF3FF", None, radius=18)
    draw.text((x + 58, y + 43), "Smart Pillbox", font=load_font(30, True), fill=PALETTE["ink"])
    draw.text((x + w - 178, y + 47), "远程同步", font=load_font(22), fill=PALETTE["blue"])
    for i in range(4):
        cx = x + 45 + i * 150
        cy = y + 120
        color = ["#DFF5E6", "#E2F0FF", "#FFF1D6", "#FCE2DD"][i]
        label = ["早", "中", "晚", "睡前"][i]
        rounded_rect(draw, (cx, cy, cx + 120, cy + 118), color, "#B8C6D8", radius=18, width=2)
        draw.text((cx + 34, cy + 34), label, font=load_font(34, True), fill=PALETTE["ink"])
        draw.ellipse((cx + 91, cy + 22, cx + 111, cy + 42), fill=PALETTE["green"])
    rounded_rect(draw, (x + 52, y + h - 55, x + w - 52, y + h - 20), "#F5F8FB", "#CCD8E2", radius=14)
    draw.text((x + 70, y + h - 48), "语音提醒  LED灯光  蜂鸣器  电池状态", font=load_font(20), fill=PALETTE["muted"])

    draw_callout(draw, (80, 250), (520, 390), "分仓防错", "按早、中、晚、睡前分格，降低漏服与错服风险。")
    draw_callout(draw, (80, 585), (585, 610), "适老交互", "大字体标识、状态灯和一键确认，降低老人使用门槛。")
    draw_callout(draw, (1190, 250), (1030, 390), "远程监护", "服药记录同步到手机端，家属可查看异常提醒。")
    draw_callout(draw, (1190, 585), (985, 650), "低功耗提醒", "语音、灯光、蜂鸣组合提醒，兼顾续航与可靠性。")

    if not req_df.empty:
        top = req_df.sort_values("重要度", ascending=False).head(4)
        x = 80
        y = 820
        draw.text((x, y), "评论数据驱动的核心需求", font=load_font(28, True), fill=PALETTE["ink"])
        for i, (_, row) in enumerate(top.iterrows()):
            draw.text((x + i * 370, y + 45), f"{i + 1}. {row.get('需求名称', '')}", font=load_font(22, True), fill=PALETTE["blue"])
            draw_wrapped(draw, (x + i * 370, y + 78), str(row.get("来源关键词", "")), load_font(18), PALETTE["muted"], 320)

    img.save(path)


def create_three_view(path: Path) -> None:
    """生成产品三视图。"""
    if path.exists() and path.stat().st_size >= HIGH_FIDELITY_THRESHOLD_BYTES:
        return

    img = Image.new("RGB", (1600, 1000), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.text((70, 55), "智能药盒三视图", font=load_font(52, True), fill=PALETTE["ink"])
    draw.text((72, 120), "正视图 / 俯视图 / 侧视图，展示药仓、屏幕、提醒与电池结构关系", font=load_font(26), fill=PALETTE["muted"])

    # 正视图
    draw.text((170, 210), "正视图", font=load_font(30, True), fill=PALETTE["ink"])
    pillbox_body(draw, 90, 280, 430, 260, 0.72)
    draw.line((90, 590, 520, 590), fill=PALETTE["line"], width=2)
    draw.text((230, 605), "约 160 mm", font=load_font(20), fill=PALETTE["muted"])

    # 俯视图
    draw.text((730, 210), "俯视图", font=load_font(30, True), fill=PALETTE["ink"])
    rounded_rect(draw, (600, 300, 1040, 540), PALETTE["white"], PALETTE["line"], radius=26, width=3)
    for i, color in enumerate(["#DFF5E6", "#E2F0FF", "#FFF1D6", "#FCE2DD"]):
        x = 625 + i * 100
        rounded_rect(draw, (x, 335, x + 82, 480), color, "#B8C6D8", radius=16)
    rounded_rect(draw, (1020, 355, 1160, 485), "#F5F8FB", "#CCD8E2", radius=20)
    draw.text((1044, 405), "电池仓", font=load_font(22), fill=PALETTE["muted"])
    draw.line((600, 590, 1160, 590), fill=PALETTE["line"], width=2)
    draw.text((800, 605), "约 85 mm", font=load_font(20), fill=PALETTE["muted"])

    # 侧视图
    draw.text((1245, 210), "侧视图", font=load_font(30, True), fill=PALETTE["ink"])
    rounded_rect(draw, (1230, 365, 1510, 470), PALETTE["white"], PALETTE["line"], radius=24, width=3)
    rounded_rect(draw, (1265, 328, 1475, 365), "#EAF3FF", "#CCD8E2", radius=18)
    draw.ellipse((1450, 395, 1486, 431), fill=PALETTE["green"])
    draw.line((1535, 365, 1535, 470), fill=PALETTE["line"], width=2)
    draw.text((1490, 495), "约 32 mm", font=load_font(20), fill=PALETTE["muted"])

    # 设计说明
    rounded_rect(draw, (85, 735, 1515, 900), PALETTE["panel"], None, radius=22)
    draw.text((120, 765), "结构说明", font=load_font(28, True), fill=PALETTE["ink"])
    notes = "圆角外壳降低握持边缘压迫；四分仓对应常见服药时段；顶部显示与状态灯用于提醒反馈；侧向电池仓便于维护和续航管理。"
    draw_wrapped(draw, (120, 812), notes, load_font(24), PALETTE["muted"], 1360, 10)
    img.save(path)


def create_exploded_view(path: Path) -> None:
    """生成产品爆炸图。"""
    # 如果已经存在图像模型生成的高保真爆炸图，默认保留。
    if path.exists() and path.stat().st_size >= HIGH_FIDELITY_THRESHOLD_BYTES:
        return

    img = Image.new("RGB", (1600, 1000), PALETTE["bg"])
    draw = ImageDraw.Draw(img)
    draw.text((70, 55), "智能药盒爆炸图", font=load_font(52, True), fill=PALETTE["ink"])
    draw.text((72, 120), "每个部件分离展示：可看清上盖、密封、药仓、提醒、电路、供电和底壳结构", font=load_font(26), fill=PALETTE["muted"])

    x_center = 800
    layers = [
        ("防潮上盖", 185, 520, 72, "#DDF1FF", -120),
        ("硅胶密封圈", 300, 565, 34, "#C9F0D8", 80),
        ("可拆药仓", 405, 650, 118, "#FFF1D6", -70),
        ("LED提醒灯 + 蜂鸣器", 565, 510, 54, "#FCE2DD", 120),
        ("主控电路板", 675, 455, 74, "#E2F0FF", -105),
        ("电池仓 + 充电接口", 790, 500, 66, "#E8ECF2", 110),
        ("底壳", 885, 680, 92, "#FFFFFF", 0),
    ]
    part_centers = []
    for label, y, w, h, color, offset in layers:
        x = x_center - w // 2 + offset
        rounded_rect(draw, (x + 14, y + 14, x + w + 14, y + h + 14), PALETTE["shadow"], None, radius=22)
        rounded_rect(draw, (x, y, x + w, y + h), color, PALETTE["line"], radius=22, width=3)
        draw.text((x + 24, y + h // 2 - 14), label, font=load_font(24, True), fill=PALETTE["ink"])
        part_centers.append((x + w // 2, y + h // 2))

        if "药仓" in label:
            for i in range(4):
                cx = x + 34 + i * 145
                rounded_rect(draw, (cx, y + 25, cx + 95, y + h - 22), ["#DFF5E6", "#E2F0FF", "#FFF1D6", "#FCE2DD"][i], "#B8C6D8", radius=16)
        if "主控" in label:
            draw.rectangle((x + 315, y + 18, x + 420, y + h - 18), fill="#5BA6FF", outline="#2770C9", width=2)
            draw.ellipse((x + 50, y + 22, x + 88, y + 60), fill=PALETTE["green"])
        if "电池" in label:
            rounded_rect(draw, (x + 45, y + 18, x + 205, y + 48), "#D9DEE7", "#AAB6C4", radius=12)
            draw.text((x + 230, y + 20), "USB-C", font=load_font(18), fill=PALETTE["muted"])

    for i in range(len(part_centers) - 1):
        draw.line((*part_centers[i], *part_centers[i + 1]), fill="#A8B8C8", width=2)

    callouts = [
        ((135, 220), part_centers[0], "防潮上盖", "透明上盖保护药品，减少灰尘和受潮。"),
        ((120, 470), part_centers[2], "四格药仓", "早、中、晚、睡前分仓管理，降低错服风险。"),
        ((1190, 365), part_centers[3], "提醒模块", "LED灯和蜂鸣器用于到点提醒。"),
        ((1190, 690), part_centers[5], "供电与接口", "独立电池仓和充电接口便于维护。"),
    ]
    for anchor, target, title, text in callouts:
        draw_callout(draw, anchor, target, title, text)

    img.save(path)


def create_scenario_image(path: Path) -> None:
    """生成场景使用效果图。"""
    if path.exists() and path.stat().st_size >= HIGH_FIDELITY_THRESHOLD_BYTES:
        return

    img = Image.new("RGB", (1600, 1000), "#F5F7FA")
    draw = ImageDraw.Draw(img)
    draw.text((70, 55), "智能药盒场景使用效果图", font=load_font(52, True), fill=PALETTE["ink"])
    draw.text((72, 120), "家庭老人用药管理场景：药盒提醒、老人确认、家属远程查看", font=load_font(26), fill=PALETTE["muted"])

    # 家庭桌面和背景
    rounded_rect(draw, (60, 730, 1540, 900), "#E7D9C8", None, radius=26)
    rounded_rect(draw, (90, 190, 1510, 760), "#FFFFFF", "#E4EAF0", radius=28)
    draw.rectangle((90, 610, 1510, 760), fill="#F2F6FA")

    # 老人简化人物
    draw.ellipse((190, 260, 330, 400), fill="#F1C6A8", outline="#D7A285", width=3)
    draw.arc((215, 310, 305, 365), 0, 180, fill=PALETTE["ink"], width=3)
    rounded_rect(draw, (160, 410, 360, 690), "#BBD7FF", "#8CAEDC", radius=60)
    draw.line((260, 690, 230, 760), fill="#4B5A66", width=16)
    draw.line((260, 690, 315, 760), fill="#4B5A66", width=16)
    draw.text((150, 785), "老年用户", font=load_font(26, True), fill=PALETTE["ink"])

    # 桌面药盒
    pillbox_body(draw, 520, 560, 520, 260, 0.85)
    for i in range(3):
        draw.arc((515 - i * 35, 500 - i * 35, 1045 + i * 35, 860 + i * 35), 220, 320, fill=PALETTE["orange"], width=5)
    draw.text((590, 500), "到点提醒", font=load_font(34, True), fill=PALETTE["orange"])

    # 手机端
    rounded_rect(draw, (1180, 300, 1390, 650), "#1C2530", None, radius=36)
    rounded_rect(draw, (1200, 330, 1370, 620), "#F9FBFD", None, radius=24)
    draw.text((1225, 360), "家属端", font=load_font(26, True), fill=PALETTE["ink"])
    rounded_rect(draw, (1225, 415, 1345, 465), "#DFF5E6", None, radius=16)
    draw.text((1245, 427), "已服药", font=load_font(22, True), fill=PALETTE["green"])
    rounded_rect(draw, (1225, 490, 1345, 550), "#E2F0FF", None, radius=16)
    draw.text((1242, 508), "记录同步", font=load_font(20), fill=PALETTE["blue"])
    draw.line((1040, 610, 1180, 480), fill=PALETTE["blue"], width=4)
    draw.text((1085, 535), "微信同步", font=load_font(22), fill=PALETTE["blue"])

    img.save(path)


def create_board(path: Path, image_dir: Path, req_df: pd.DataFrame, topic_df: pd.DataFrame) -> None:
    """生成产品设计展板。"""
    if path.exists() and path.stat().st_size >= HIGH_FIDELITY_THRESHOLD_BYTES:
        return

    img = Image.new("RGB", (2000, 1400), "#FFFFFF")
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 2000, 170), fill="#102033")
    draw.text((70, 42), "基于用户评论数据的智能药盒产品设计研究", font=load_font(56, True), fill="#FFFFFF")
    draw.text((72, 112), "评论数据导入 -> 文本挖掘 -> 需求映射 -> 产品方案 -> 设计图像输出", font=load_font(28), fill="#D8E6F3")

    # 左侧研究流程
    rounded_rect(draw, (70, 230, 575, 1260), "#F4F8FC", "#DCE6EF", radius=24)
    draw.text((105, 265), "实验流程", font=load_font(36, True), fill=PALETTE["ink"])
    steps = ["评论清洗", "TF-IDF关键词", "情感分析", "主题聚类", "需求-功能-结构映射", "Neo4j知识图谱", "产品设计方案"]
    y = 330
    for i, step in enumerate(steps):
        draw.ellipse((110, y, 150, y + 40), fill=PALETTE["blue"])
        draw.text((123, y + 6), str(i + 1), font=load_font(22, True), fill="#FFFFFF")
        draw.text((175, y + 3), step, font=load_font(26, True), fill=PALETTE["ink"])
        if i < len(steps) - 1:
            draw.line((130, y + 45, 130, y + 80), fill=PALETTE["line"], width=4)
        y += 110

    # 中间产品图
    rounded_rect(draw, (640, 230, 1345, 800), "#F9FBFD", "#DCE6EF", radius=24)
    draw.text((675, 265), "核心产品概念", font=load_font(36, True), fill=PALETTE["ink"])
    pillbox_body(draw, 775, 405, 440, 230, 0.72)
    draw_wrapped(draw, (690, 690), "面向老年慢病人群与家庭照护场景，集成多模态提醒、分仓防错、远程监护和适老交互。", load_font(24), PALETTE["muted"], 590, 10)

    # 右侧需求证据
    rounded_rect(draw, (1410, 230, 1930, 800), "#F4F8FC", "#DCE6EF", radius=24)
    draw.text((1445, 265), "用户需求证据", font=load_font(36, True), fill=PALETTE["ink"])
    if not req_df.empty:
        top = req_df.sort_values("重要度", ascending=False).head(5)
        yy = 330
        for _, row in top.iterrows():
            draw.text((1450, yy), str(row.get("需求名称", "")), font=load_font(24, True), fill=PALETTE["blue"])
            yy += 35
            yy += draw_wrapped(draw, (1450, yy), str(row.get("来源关键词", "")), load_font(19), PALETTE["muted"], 420, 4) + 18

    # 底部图像组
    rounded_rect(draw, (640, 860, 1930, 1260), "#F9FBFD", "#DCE6EF", radius=24)
    draw.text((675, 895), "设计输出图像", font=load_font(36, True), fill=PALETTE["ink"])
    thumbs = [
        ("效果图", image_dir / IMAGE_FILENAMES["render"]),
        ("三视图", image_dir / IMAGE_FILENAMES["three_view"]),
        ("爆炸图", image_dir / IMAGE_FILENAMES["exploded"]),
        ("场景图", image_dir / IMAGE_FILENAMES["scenario"]),
    ]
    x = 675
    for label, thumb_path in thumbs:
        if thumb_path.exists():
            thumb = Image.open(thumb_path).convert("RGB")
            thumb.thumbnail((270, 220))
            img.paste(thumb, (x, 960))
        draw.text((x + 80, 1195), label, font=load_font(24, True), fill=PALETTE["ink"])
        x += 300

    draw.text((70, 1315), "输出文件：清洗结果、关键词结果、情感结果、主题聚类、映射数据库、Neo4j文件、设计方案、设计图像与展板", font=load_font(24), fill=PALETTE["muted"])
    img.save(path)


# =========================
# 4. 生成提示词与主流程
# =========================

def build_image_prompts(req_df: pd.DataFrame) -> str:
    """生成可复制到图像模型中的提示词。"""
    req_names = "、".join(req_df.get("需求名称", pd.Series(dtype=str)).astype(str).head(6).tolist()) if not req_df.empty else "服药提醒、分仓防错、远程监护、适老交互"
    return f"""# 智能药盒设计图像生成提示词

## 1. 设计效果图
Use case: product-mockup
Asset type: smart pillbox product concept render
Primary request: 一款面向老年慢病人群的智能药盒，体现{req_names}。
Style/medium: clean 3D product rendering, realistic plastic and silicone material
Composition/framing: three-quarter front view, centered product, readable pill compartments
Lighting/mood: soft studio lighting, clean medical-home appliance feeling
Constraints: no brand logo, no watermark, no messy background

## 2. 三视图
Use case: infographic-diagram
Asset type: orthographic three-view drawing
Primary request: 智能药盒正视图、俯视图、侧视图，展示药仓、状态灯、提醒模块、电池仓。
Style/medium: industrial design board drawing, clean lines, Chinese labels
Constraints: clear structure, simple dimensions, no decorative clutter

## 3. 爆炸图
Use case: infographic-diagram
Asset type: exploded product structure diagram
Primary request: 智能药盒爆炸图，包含防潮上盖、密封圈、可拆药仓、LED/蜂鸣提醒模块、主控板、底壳与电池仓。
Style/medium: clean technical product illustration, labeled parts
Constraints: readable hierarchy, no brand logo, no watermark

## 4. 场景使用效果图
Use case: photorealistic-natural
Asset type: usage scenario render
Primary request: 家庭场景中老人使用智能药盒，到点提醒，家属手机端收到服药记录同步。
Style/medium: warm realistic lifestyle render
Constraints: friendly, safe, no hospital fear, no brand logo

## 5. 展板
Use case: productivity-visual
Asset type: graduate research product design presentation board
Primary request: 展示评论数据分析流程、核心需求、产品设计方案、三视图、爆炸图和场景图。
Style/medium: clean academic product design board
Constraints: layout clear, text concise, no watermark
"""


def main() -> None:
    """第八阶段：生成设计图片与展板。"""
    parser = argparse.ArgumentParser(description="第八阶段：生成设计效果图、三视图、爆炸图、场景图和展板")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    ensure_previous_outputs(output_dir)
    image_dir = output_dir / "design_images"
    image_dir.mkdir(parents=True, exist_ok=True)

    mapping_path = output_dir / "智能药盒需求功能映射数据库.xlsx"
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    req_df = read_sheet(mapping_path, "用户需求表")
    topic_df = read_sheet(topic_path, "主题汇总")

    create_render_image(image_dir / IMAGE_FILENAMES["render"], req_df)
    create_three_view(image_dir / IMAGE_FILENAMES["three_view"])
    create_exploded_view(image_dir / IMAGE_FILENAMES["exploded"])
    create_scenario_image(image_dir / IMAGE_FILENAMES["scenario"])
    create_board(image_dir / IMAGE_FILENAMES["board"], image_dir, req_df, topic_df)

    prompt_path = image_dir / "设计图像生成提示词.txt"
    prompt_path.write_text(build_image_prompts(req_df), encoding="utf-8")

    manifest = pd.DataFrame([
        {"图像类型": "设计效果图", "文件路径": str(image_dir / IMAGE_FILENAMES["render"]), "用途": "展示智能药盒整体外观与核心功能"},
        {"图像类型": "三视图", "文件路径": str(image_dir / IMAGE_FILENAMES["three_view"]), "用途": "展示正视、俯视、侧视结构关系"},
        {"图像类型": "爆炸图", "文件路径": str(image_dir / IMAGE_FILENAMES["exploded"]), "用途": "展示功能模块与结构层级"},
        {"图像类型": "场景使用效果图", "文件路径": str(image_dir / IMAGE_FILENAMES["scenario"]), "用途": "展示家庭服药提醒与远程监护场景"},
        {"图像类型": "产品设计展板", "文件路径": str(image_dir / IMAGE_FILENAMES["board"]), "用途": "用于论文答辩、课程展示或设计汇报"},
        {"图像类型": "图像生成提示词", "文件路径": str(prompt_path), "用途": "可复制到图像生成模型进一步渲染"},
    ])
    manifest_path = image_dir / "设计图像清单.xlsx"
    with pd.ExcelWriter(manifest_path, engine="openpyxl") as writer:
        manifest.to_excel(writer, sheet_name="设计图像清单", index=False)

    print(f"设计图片输出目录：{image_dir}")
    for filename in IMAGE_FILENAMES.values():
        print(f"已生成：{image_dir / filename}")
    print(f"已生成：{prompt_path}")
    print(f"已生成：{manifest_path}")


if __name__ == "__main__":
    main()
