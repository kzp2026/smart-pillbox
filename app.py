from __future__ import annotations

import subprocess
import sys
import os
import hashlib
import html
import json
import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from scripts.result_archive import build_result_archive, extract_result_archive, find_restored_input_file


# =========================
# 1. 基础配置
# =========================

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT_DIR / "output" / "runs"
SCRIPTS_DIR = ROOT_DIR / "scripts"
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# 阶段定义（去掉产品名称，改为动态）
STAGES = [
    ("01 评论清洗", "01_clean_comments.py", "cleaned_comments.xlsx"),
    ("02 关键词提取", "02_extract_keywords.py", "需求关键词提取结果.xlsx"),
    ("03 情感分析", "03_sentiment_analysis.py", "情感分析结果.xlsx"),
    ("04 主题聚类", "04_bertopic_clustering.py", "BERTopic主题聚类结果.xlsx"),
    ("05 需求映射", "05_build_mapping_database.py", "{product}_需求功能映射数据库.xlsx"),
    ("06 Neo4j图谱", "06_build_neo4j_files.py", "neo4j_nodes.csv"),
    ("07 AI生成参数", "07_generate_ai_parameters.py", "AI生成参数表.xlsx"),
    ("08 设计方案", "07_generate_design_scheme.py", "{product}产品设计方案.docx"),
    ("09 设计图片", "08_generate_design_visuals.py", "design_images/{product}产品设计展板.png"),
    ("10 方案评价", "09_evaluate_design_scheme.py", "方案评价表.xlsx"),
]

AI_PARAMETER_STAGES = [STAGES[index] for index in (0, 1, 2, 3, 4, 5, 6)]
DESIGN_IMAGE_STAGES = [STAGES[index] for index in (0, 1, 2, 3, 4, 6, 7, 8)]
EVALUATION_STAGES = [STAGES[index] for index in (0, 1, 2, 3, 4, 5, 6, 7, 9)]


def get_product_name() -> str:
    """获取当前产品名称"""
    return str(st.session_state.get("product_name", "")).strip()


def safe_path_part(value: str) -> str:
    """把产品名称转换为安全的目录名，同时保留可读性。"""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" ._")
    return cleaned[:40] or "未命名产品"


def get_output_dir() -> Path:
    """返回当前上传数据对应的独立输出目录。"""
    active = st.session_state.get("active_output_dir")
    if active:
        return Path(active)
    return OUTPUT_ROOT / "_waiting_for_upload"


def has_active_dataset() -> bool:
    """判断当前会话是否已经上传并绑定评论数据。"""
    return bool(st.session_state.get("active_dataset_key"))


def output_filename(stage_output: str) -> str:
    """把阶段输出文件名中的 {product} 替换为实际产品名"""
    return stage_output.replace("{product}", get_product_name())


def resolve_output_path(relative_path: str) -> Path:
    """返回某个输出文件的最新可用路径。

    当 Excel/WPS 占用标准结果文件时，脚本会写入“文件名_时间戳.xlsx”；
    页面展示时自动选择最新文件，避免旧文件占用导致流程中断。
    """
    resolved = get_output_dir() / output_filename(relative_path)
    candidates = []
    if resolved.exists():
        candidates.append(resolved)
    candidates.extend(resolved.parent.glob(f"{resolved.stem}_*{resolved.suffix}"))
    if candidates:
        return max(candidates, key=lambda path: path.stat().st_mtime)
    return resolved


def get_download_files() -> list[str]:
    """动态生成下载文件列表"""
    p = get_product_name()
    return [
        "cleaned_comments.xlsx",
        "需求关键词提取结果.xlsx",
        "情感分析结果.xlsx",
        "BERTopic主题聚类结果.xlsx",
        f"{p}_需求功能映射数据库.xlsx",
        "neo4j_nodes.csv",
        "neo4j_relationships.csv",
        "import_neo4j.cypher",
        "需求—功能—结构映射表.xlsx",
        "AI生成参数表.xlsx",
        "ai_generation_parameters.json",
        "prompt_template.txt",
        f"{p}产品设计方案.docx",
        f"{p}产品设计方案.txt",
        f"design_images/{p}产品效果图.png",
        f"design_images/{p}爆炸图.png",
        f"design_images/{p}细节图.png",
        f"design_images/{p}产品三视图.png",
        f"design_images/{p}产品设计展板.png",
        f"design_images/{p}产品使用效果图.png",
        "design_images/设计图像生成提示词.txt",
        "design_images/设计图像清单.xlsx",
        "方案评价表.xlsx",
        "方案评价结果.json",
        "方案优化建议.txt",
        "优化后AI生成参数.json",
        "开题报告实验结果摘要.docx",
    ]


# =========================
# 2. 文件读取与运行工具
# =========================

def save_uploaded_file(uploaded_file) -> Path | None:
    if uploaded_file is None:
        existing_input = st.session_state.get("active_input_path")
        if existing_input and Path(existing_input).exists():
            return Path(existing_input)
        if st.session_state.get("active_dataset_key") and st.session_state.get("active_output_dir"):
            return None
        st.session_state.pop("active_dataset_key", None)
        st.session_state.pop("active_output_dir", None)
        st.session_state.pop("active_input_path", None)
        return None

    file_bytes = uploaded_file.getvalue()
    digest = hashlib.sha256(file_bytes).hexdigest()
    dataset_key = f"{safe_path_part(get_product_name())}_{digest[:16]}"
    run_dir = OUTPUT_ROOT / dataset_key
    run_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(uploaded_file.name).suffix.lower()
    target = run_dir / f"uploaded_comments{suffix}"
    if not target.exists() or target.read_bytes() != file_bytes:
        target.write_bytes(file_bytes)

    previous_key = st.session_state.get("active_dataset_key")
    st.session_state["active_dataset_key"] = dataset_key
    st.session_state["active_output_dir"] = str(run_dir)
    st.session_state["active_input_path"] = str(target)
    if previous_key != dataset_key:
        st.cache_data.clear()
    return target


def run_stage(script_name: str, input_path: Path | None = None) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        str(SCRIPTS_DIR / script_name),
        "--output-dir", str(get_output_dir()),
    ]
    if script_name in {
        "05_build_mapping_database.py",
        "06_build_neo4j_files.py",
        "07_generate_ai_parameters.py",
        "07_generate_design_scheme.py",
        "08_generate_design_visuals.py",
        "09_evaluate_design_scheme.py",
    }:
        command.extend(["--product-name", get_product_name()])
    if input_path and script_name in {
        "01_clean_comments.py", "02_extract_keywords.py",
        "03_sentiment_analysis.py", "04_bertopic_clustering.py",
    }:
        command.extend(["--input", str(input_path)])
    env = os.environ.copy()
    runtime_dashscope_key = str(st.session_state.get("runtime_dashscope_api_key", "")).strip()
    if runtime_dashscope_key:
        env["DASHSCOPE_API_KEY"] = runtime_dashscope_key
        env["IMAGE_PROVIDER"] = "dashscope"
        env["IMAGE_MODEL"] = str(st.session_state.get("runtime_image_model", "qwen-image")).strip() or "qwen-image"
    return subprocess.run(command, cwd=ROOT_DIR, capture_output=True, text=True, env=env)


@st.cache_data(show_spinner=False)
def read_excel_cached(path: str, sheet_name: str | None, modified_ns: int, file_size: int):
    if sheet_name is None:
        # sheet_name=None 在 pandas 中表示读取全部工作表，会返回 dict；
        # 页面预览需要 DataFrame，因此默认读取第一个工作表。
        return pd.read_excel(path, sheet_name=0)
    return pd.read_excel(path, sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def read_csv_cached(path: str, modified_ns: int, file_size: int) -> pd.DataFrame:
    return pd.read_csv(path)


def load_sheet(filename: str, sheet_name: str | None) -> pd.DataFrame:
    path = resolve_output_path(filename)
    if not path.exists():
        return pd.DataFrame()
    try:
        stat = path.stat()
        data = read_excel_cached(str(path), sheet_name, stat.st_mtime_ns, stat.st_size)
        # 兜底处理：如果后续误传 sheet_name=None 或文件读取返回字典，
        # 自动取第一个工作表，避免 show_table 访问 .empty 时崩溃。
        if isinstance(data, dict):
            return next(iter(data.values()), pd.DataFrame())
        if isinstance(data, pd.DataFrame):
            return data
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame()


def file_ready(relative_path: str) -> bool:
    return has_active_dataset() and resolve_output_path(relative_path).exists()


def show_table(df: pd.DataFrame, title: str, max_rows: int = 100) -> None:
    st.subheader(title)
    if df.empty:
        st.info("该结果尚未生成，请先运行对应阶段。")
        return
    st.dataframe(df.head(max_rows), use_container_width=True)


def show_downloads() -> None:
    st.header("📥 下载中心")
    found = False
    output_dir = get_output_dir()
    if has_active_dataset() and output_dir.exists():
        archive_bytes = build_result_archive(output_dir, get_product_name())
        st.download_button(
            label="⬇ 下载完整研究结果归档.zip",
            data=archive_bytes,
            file_name=f"{safe_path_part(get_product_name())}_完整研究结果归档.zip",
            mime="application/zip",
            use_container_width=True,
        )
        st.caption("该 ZIP 可在侧边栏“恢复历史结果归档”重新导入，解决 Streamlit Cloud 重启后结果丢失的问题。")
    for rel_path in get_download_files():
        full = resolve_output_path(rel_path)
        if full.exists():
            found = True
            with open(full, "rb") as f:
                st.download_button(
                    label=f"⬇ {rel_path}",
                    data=f,
                    file_name=Path(rel_path).name,
                    mime="application/octet-stream",
                )
    if not found:
        st.info("还没有生成结果，请先上传数据并运行分析。")


def render_design_image_card(rel_path: str, title: str, description: str) -> None:
    full = resolve_output_path(rel_path)
    st.subheader(title)
    st.caption(description)
    if full.exists():
        st.image(str(full), use_container_width=True)
        st.download_button(
            label=f"下载{title}",
            data=full.read_bytes(),
            file_name=full.name,
            mime="image/png",
            key=f"download_{rel_path}",
            use_container_width=True,
        )
    else:
        st.info(f"{title}尚未生成，请先运行“09 设计图片”。")


def load_render_status() -> dict:
    status_path = resolve_output_path("design_images/写实渲染状态.json")
    if not status_path.exists():
        return {}
    try:
        return json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def get_image_api_status() -> tuple[bool, str, str]:
    runtime_dashscope_key = str(st.session_state.get("runtime_dashscope_api_key", "")).strip()
    if runtime_dashscope_key:
        return True, "阿里云百炼 DashScope（当前会话临时密钥）", str(st.session_state.get("runtime_image_model", "qwen-image")).strip() or "qwen-image"
    dashscope_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("QWEN_IMAGE_API_KEY")
    image_key = os.getenv("IMAGE_API_KEY") or os.getenv("OPENAI_API_KEY")
    provider = os.getenv("IMAGE_PROVIDER", "").strip().lower()
    if provider in {"dashscope", "aliyun", "alibaba", "qwen", "qwen-image", "wanx"} or (dashscope_key and provider not in {"openai", "compatible", "openai-compatible"}):
        return bool(dashscope_key), "阿里云百炼 DashScope（通义万相 / Qwen-Image）", os.getenv("IMAGE_MODEL", "qwen-image")
    return bool(image_key), "OpenAI Images 兼容接口", os.getenv("IMAGE_MODEL", "gpt-image-1")


def build_graph_svg(nodes_df: pd.DataFrame, rels_df: pd.DataFrame, max_nodes: int = 36) -> str:
    if nodes_df.empty or rels_df.empty or "node_id" not in nodes_df.columns:
        return ""
    selected = nodes_df.head(max_nodes).copy()
    selected_ids = set(selected["node_id"].astype(str))
    rels = rels_df[
        rels_df.get("source_id", pd.Series(dtype=str)).astype(str).isin(selected_ids)
        & rels_df.get("target_id", pd.Series(dtype=str)).astype(str).isin(selected_ids)
    ].head(max_nodes * 2)
    width, height = 980, 620
    center_x, center_y, radius = width / 2, height / 2, 250
    positions = {}
    total = max(len(selected), 1)
    for index, (_, row) in enumerate(selected.iterrows()):
        angle = 2 * math.pi * index / total
        node_id = str(row.get("node_id", ""))
        positions[node_id] = (center_x + radius * math.cos(angle), center_y + radius * math.sin(angle))

    color_map = {
        "Product": "#4D8DFF",
        "Requirement": "#64C78A",
        "Function": "#F4A261",
        "Structure": "#59C3C3",
        "Topic": "#A78BFA",
        "Keyword": "#E76F51",
    }
    edge_parts = []
    for _, rel in rels.iterrows():
        source_id = str(rel.get("source_id", ""))
        target_id = str(rel.get("target_id", ""))
        if source_id in positions and target_id in positions:
            x1, y1 = positions[source_id]
            x2, y2 = positions[target_id]
            title = html.escape(str(rel.get("type", "")))
            edge_parts.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#CBD5E1" stroke-width="1.4"><title>{title}</title></line>')

    node_parts = []
    for _, row in selected.iterrows():
        node_id = str(row.get("node_id", ""))
        x, y = positions[node_id]
        label = str(row.get("label", ""))
        name = str(row.get("name", node_id))
        color = color_map.get(label, "#94A3B8")
        safe_name = html.escape(name[:14])
        safe_title = html.escape(f"{name} | {label} | {row.get('description', '')}")
        node_parts.append(
            f'<g><circle cx="{x:.1f}" cy="{y:.1f}" r="22" fill="{color}" stroke="white" stroke-width="3"><title>{safe_title}</title></circle>'
            f'<text x="{x:.1f}" y="{y + 38:.1f}" text-anchor="middle" font-size="12" fill="#102033">{safe_name}</text></g>'
        )

    legend = "".join(
        f'<span style="display:inline-flex;align-items:center;margin-right:14px;"><span style="width:10px;height:10px;background:{color};border-radius:50%;display:inline-block;margin-right:5px;"></span>{html.escape(label)}</span>'
        for label, color in color_map.items()
    )
    return f"""
    <div style="font-family:Arial,'Microsoft YaHei',sans-serif;background:#F8FAFC;border:1px solid #D8E2EC;border-radius:16px;padding:14px;">
      <div style="font-weight:700;color:#102033;margin-bottom:8px;">知识图谱关系预览（悬停节点/连线可查看说明）</div>
      <div style="font-size:12px;color:#5C6B7A;margin-bottom:10px;">{legend}</div>
      <svg width="100%" viewBox="0 0 {width} {height}" role="img" aria-label="Neo4j 知识图谱关系预览">
        {''.join(edge_parts)}
        {''.join(node_parts)}
      </svg>
    </div>
    """


def load_json_output(relative_path: str) -> dict:
    path = resolve_output_path(relative_path)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def load_text_output(relative_path: str) -> str:
    path = resolve_output_path(relative_path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def run_stage_sequence(
    stages: list[tuple[str, str, str]],
    input_path: Path | None,
    final_stage_name: str,
    running_label: str,
    done_label: str,
) -> bool:
    with st.status(running_label, expanded=True) as status:
        for stage_name, script_name, stage_output in stages:
            if stage_name != final_stage_name and file_ready(stage_output):
                st.write(f"✅ {stage_name} 已有结果，跳过")
                continue
            st.write(f"⏳ {stage_name}...")
            result = run_stage(script_name, input_path)
            if result.returncode != 0:
                error_text = (result.stderr or result.stdout or "未知错误").strip()
                st.error(f"❌ {stage_name} 失败：{error_text[:800]}")
                status.update(label=f"{stage_name} 失败", state="error")
                return False
            st.write(f"✅ {stage_name} 完成")
        status.update(label=done_label, state="complete")
        return True


# =========================
# 3. 页面 UI
# =========================

st.set_page_config(page_title="用户评论驱动的产品创新智能体", page_icon="📊", layout="wide")

# --- 侧边栏 ---
with st.sidebar:
    st.title("⚙️ 控制面板")

    # 产品名称输入
    st.text_input(
        "📦 产品名称",
        value=st.session_state.get("product_name", ""),
        placeholder="例如：智能药盒、蓝牙耳机、咖啡机...",
        key="product_name",
        help="输入你要研究的产品名称，所有结果将围绕该产品生成。",
    )

    if not get_product_name():
        st.warning("👆 请先输入产品名称")
        st.stop()

    st.divider()

    # 数据上传
    uploaded = st.file_uploader(
        "📤 上传评论数据",
        type=["xlsx", "xls", "csv"],
        help="支持 .xlsx / .xls / .csv，自动识别评论列。",
    )
    input_path = save_uploaded_file(uploaded)
    if uploaded is not None:
        st.success(f"已绑定当前数据：{uploaded.name}")
        st.caption(f"独立结果编号：{st.session_state['active_dataset_key'][-16:]}")
    else:
        st.info("请上传评论数据。上传前不会显示仓库内的历史结果。")

    with st.expander("🎨 写实渲染配置（可选）", expanded=False):
        st.caption("如果你看不到 Streamlit 后台 Secrets，就在这里临时填写百炼 Key。仅当前会话使用，不写入 GitHub。")
        st.text_input(
            "阿里云百炼 API Key",
            type="password",
            key="runtime_dashscope_api_key",
            placeholder="sk-...",
            help="不要把密钥发给别人；这里只用于当前网页会话生成写实渲染图。",
        )
        st.selectbox(
            "图片模型",
            options=["qwen-image", "wan2.2-t2i-plus"],
            index=0,
            key="runtime_image_model",
            help="优先使用 qwen-image；如果你的百炼控制台未开通，可切换通义万相 wan2.2-t2i-plus。",
        )
        if st.session_state.get("runtime_dashscope_api_key"):
            st.success("已填写临时百炼密钥。进入“设计图片”页点击写实渲染生成按钮。")

    with st.expander("📦 恢复历史结果归档", expanded=False):
        archive_file = st.file_uploader(
            "上传此前下载的完整研究结果归档.zip",
            type=["zip"],
            key="restore_result_archive",
            help="用于恢复已生成的表格、图片、方案和评价结果，解决云端重启后结果丢失。",
        )
        if st.button("恢复归档", use_container_width=True, disabled=archive_file is None):
            try:
                archive_bytes = archive_file.getvalue()
                restored_dir = extract_result_archive(archive_bytes, OUTPUT_ROOT, get_product_name())
                restored_input = find_restored_input_file(restored_dir)
                st.session_state["active_dataset_key"] = restored_dir.name
                st.session_state["active_output_dir"] = str(restored_dir)
                if restored_input:
                    st.session_state["active_input_path"] = str(restored_input)
                else:
                    st.session_state.pop("active_input_path", None)
                st.cache_data.clear()
                st.success("历史结果已恢复。")
                st.rerun()
            except Exception as exc:
                st.error(f"归档恢复失败：{exc}")

    st.divider()

    # 一键生成
    if st.button("🚀 一键生成全部研究结果", type="primary", use_container_width=True):
        if input_path is None:
            st.error("请先上传评论数据。")
            st.stop()
        with st.status(f"正在分析 {get_product_name()} 用户评论...", expanded=True) as status:
            for stage_name, script_name, _ in STAGES:
                st.write(f"⏳ {stage_name}...")
                result = run_stage(script_name, input_path)
                if result.returncode != 0:
                    st.error(f"❌ {stage_name} 失败：{result.stderr[:500]}")
                    status.update(label=f"{stage_name} 失败", state="error")
                    break
                st.write(f"✅ {stage_name} 完成")
            else:
                status.update(label="🎉 全部完成！", state="complete")
        st.cache_data.clear()
        st.rerun()

    st.divider()

    # 分阶段运行
    st.subheader("🔧 分阶段运行")
    for stage_name, script_name, _ in STAGES:
        if st.button(f"▶ {stage_name}", use_container_width=True):
            if input_path is None:
                st.error("请先上传评论数据。")
                st.stop()
            with st.spinner(f"运行 {stage_name}..."):
                result = run_stage(script_name, input_path)
                if result.returncode == 0:
                    st.success(f"✅ {stage_name} 完成")
                else:
                    st.error(f"❌ {stage_name}：{result.stderr[:300]}")
            st.cache_data.clear()
            st.rerun()


# --- 主区域 ---
p = get_product_name()
deepseek_configured = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("LLM_API_KEY"))
image_api_configured, image_provider_label, image_model_name = get_image_api_status()
st.title(f"📊 {p} — 用户评论驱动的产品创新智能体")
st.caption("上传任意产品评论数据 → 自动完成 NLP 分析 → 生成产品设计方案与设计图")

if not has_active_dataset():
    st.info("请在左侧填写产品名称并上传评论数据。当前页面不会读取或展示任何历史产品结果。")

# 标签页
tabs = st.tabs([
    "📋 评论清洗", "🔑 关键词提取", "💬 情感分析", "🧩 主题聚类",
    "🗺 需求映射", "🕸 Neo4j图谱", "🤖 AI 生成参数", "📝 设计方案",
    "🎨 设计图片", "📊 方案评价", "📥 下载中心",
])

with tabs[0]:
    st.header("评论数据清洗")
    show_table(load_sheet("cleaned_comments.xlsx", None), "清洗后评论数据", 80)

with tabs[1]:
    st.header("TF-IDF 关键词提取")
    show_table(load_sheet("需求关键词提取结果.xlsx", "关键词排名"), "关键词排名", 80)
    show_table(load_sheet("需求关键词提取结果.xlsx", "评论关键词明细"), "评论关键词明细", 80)
    show_table(load_sheet("需求关键词提取结果.xlsx", "关键词共现矩阵"), "关键词共现矩阵", 60)

with tabs[2]:
    st.header("用户痛点与中文情感分析")
    show_table(load_sheet("情感分析结果.xlsx", "用户痛点"), "用户痛点", 50)
    show_table(load_sheet("情感分析结果.xlsx", "用户满意点"), "用户满意点", 50)
    show_table(load_sheet("情感分析结果.xlsx", "关键词情感统计"), "关键词情感统计", 80)
    show_table(load_sheet("情感分析结果.xlsx", "评论情感明细"), "评论情感明细", 80)

with tabs[3]:
    st.header("评论主题聚类")
    note_df = load_sheet("BERTopic主题聚类结果.xlsx", "算法说明")
    if not note_df.empty:
        st.info(str(note_df.iloc[0].to_dict()))
    show_table(load_sheet("BERTopic主题聚类结果.xlsx", "主题汇总"), "主题汇总", 30)
    show_table(load_sheet("BERTopic主题聚类结果.xlsx", "评论主题聚类结果"), "评论主题聚类明细", 80)

with tabs[4]:
    st.header("用户需求 → 产品功能 → 产品结构 映射数据库")
    mapping_fn = f"{p}_需求功能映射数据库.xlsx"
    show_table(load_sheet(mapping_fn, "用户需求表"), "产品需求", 50)
    show_table(load_sheet(mapping_fn, "设计机会点"), "设计机会点", 50)
    show_table(load_sheet(mapping_fn, "产品功能表"), "产品功能", 50)
    show_table(load_sheet(mapping_fn, "产品结构表"), "产品结构", 50)
    show_table(load_sheet(mapping_fn, "需求功能映射"), "需求-功能映射", 80)
    show_table(load_sheet(mapping_fn, "功能结构映射"), "功能-结构映射", 80)

with tabs[5]:
    st.header("Neo4j 知识图谱数据")
    nodes_path = resolve_output_path("neo4j_nodes.csv")
    rels_path = resolve_output_path("neo4j_relationships.csv")
    cypher_path = get_output_dir() / "import_neo4j.cypher"
    nodes_df = pd.DataFrame()
    rels_df = pd.DataFrame()
    if nodes_path.exists():
        stat = nodes_path.stat()
        nodes_df = read_csv_cached(str(nodes_path), stat.st_mtime_ns, stat.st_size)
    else:
        st.info("节点表尚未生成。")
    if rels_path.exists():
        stat = rels_path.stat()
        rels_df = read_csv_cached(str(rels_path), stat.st_mtime_ns, stat.st_size)
    else:
        st.info("关系表尚未生成。")
    graph_svg = build_graph_svg(nodes_df, rels_df)
    if graph_svg:
        components.html(graph_svg, height=660, scrolling=True)
    if not nodes_df.empty:
        show_table(nodes_df, "知识图谱节点表", 100)
    if not rels_df.empty:
        show_table(rels_df, "知识图谱关系表", 100)
    if cypher_path.exists():
        st.subheader("Cypher 导入脚本")
        st.code(cypher_path.read_text(encoding="utf-8"), language="cypher")

with tabs[6]:
    st.header("AI 生成参数")
    st.caption("用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化。")

    if st.button(
        "🤖 生成/刷新 AI 生成参数",
        type="primary",
        use_container_width=True,
        disabled=input_path is None,
        help="自动补跑缺失的分析阶段，并生成映射表、JSON 参数和 Prompt 模板。",
    ):
        if run_stage_sequence(
            AI_PARAMETER_STAGES,
            input_path,
            "07 AI生成参数",
            "正在把需求信息转化为 AI 可识别参数...",
            "AI 生成参数已生成",
        ):
            st.cache_data.clear()

    st.subheader("需求—功能—结构—AI 生成参数映射表")
    st.caption("把用户需求主题、痛点证据和 Neo4j 关系路径进一步转化为功能、结构、材料、场景和 AI Prompt 参数。")
    ai_mapping_df = load_sheet("需求—功能—结构映射表.xlsx", None)
    if ai_mapping_df.empty:
        st.info("AI 生成参数尚未生成，请点击上方按钮或运行“07 AI生成参数”。")
    else:
        st.dataframe(ai_mapping_df, use_container_width=True)

    ai_table_df = load_sheet("AI生成参数表.xlsx", None)
    if not ai_table_df.empty and "原始评论证据" in ai_table_df.columns:
        with st.expander("查看原始评论证据", expanded=False):
            for _, row in ai_table_df.iterrows():
                need = str(row.get("need", row.get("core_needs", row.get("需求主题", "需求主题"))))
                evidence = str(row.get("原始评论证据", "")).strip()
                with st.container(border=True):
                    st.markdown(f"**{need}**")
                    if evidence and evidence.lower() != "nan":
                        for comment in [item.strip() for item in evidence.split("|") if item.strip()]:
                            st.write(f"“{comment}”")
                    else:
                        st.caption("暂无代表性原始评论，请先完成主题聚类与情感分析。")

    st.subheader("JSON 参数预览")
    parameter_json = load_json_output("ai_generation_parameters.json")
    if parameter_json:
        st.json(parameter_json, expanded=False)
    else:
        st.info("JSON 参数尚未生成。")

    st.subheader("Prompt 模板预览")
    prompt_template = load_text_output("prompt_template.txt")
    if prompt_template:
        st.code(prompt_template, language="text")
    else:
        st.info("Prompt 模板尚未生成。")

with tabs[7]:
    st.header(f"{p} 产品设计方案")
    if deepseek_configured:
        st.success("DeepSeek 已连接：设计方案将根据当前评论分析结果进行增强。")
    else:
        st.info("未配置 DeepSeek API，当前使用离线规则生成设计方案。")
    txt_path = resolve_output_path(f"{p}产品设计方案.txt")
    if txt_path.exists():
        st.markdown(txt_path.read_text(encoding="utf-8"))
    else:
        st.info("设计方案尚未生成。")

with tabs[8]:
    st.header("设计图片")
    st.caption("完整输出产品效果图、爆炸图、细节图、三视图、设计展板和产品使用效果图。")
    if deepseek_configured:
        st.success("DeepSeek 已连接：将依据需求、痛点和主题聚类优化工业设计渲染提示词。")

    with st.expander("如何启用写实渲染", expanded=not image_api_configured):
        st.markdown(
            "在 Streamlit Cloud 打开 **Manage app → Settings → Secrets**，添加支持图片生成的 API 配置。"
            "DeepSeek 只负责优化提示词，不能替代图片生成模型；国内模型可直接使用阿里云百炼 DashScope。"
        )
        st.info("如果公开页面右上角没有 Manage app，请直接在左侧“写实渲染配置（可选）”里临时填写阿里云百炼 API Key。")
        st.caption("推荐国内配置：通义万相 / Qwen-Image")
        st.code(
            'DASHSCOPE_API_KEY = "你的阿里云百炼API Key"\n'
            'IMAGE_PROVIDER = "dashscope"\n'
            'IMAGE_MODEL = "qwen-image"\n'
            '# 也可改用通义万相模型，例如：\n'
            '# IMAGE_MODEL = "wan2.2-t2i-plus"',
            language="toml",
        )
        st.caption("OpenAI 或其他兼容接口配置：")
        st.code(
            'IMAGE_API_KEY = "你的图片模型密钥"\n'
            'IMAGE_MODEL = "gpt-image-1"\n'
            '# 使用兼容接口时再填写：\n'
            '# IMAGE_BASE_URL = "https://你的接口地址/v1"\n'
            '# IMAGE_QUALITY = "medium"',
            language="toml",
        )
        st.caption("保存 Secrets 后等待应用重启，再点击下方按钮重新生成。密钥不要上传到 GitHub。")

    if image_api_configured:
        st.success(f"图片模型已配置：{image_provider_label} / {image_model_name}")

    generate_label = f"🎨 使用{image_provider_label}生成/重新生成六类写实渲染图" if image_api_configured else "🧩 生成六类离线示意图"
    if st.button(
        generate_label,
        type="primary",
        use_container_width=True,
        disabled=input_path is None,
        help="自动补跑缺失的分析阶段，并重新执行 09 设计图片。",
    ):
        run_stage_sequence(
            DESIGN_IMAGE_STAGES,
            input_path,
            "09 设计图片",
            "正在准备设计数据并生成六类图片...",
            "六类设计图片已生成",
        )
        st.cache_data.clear()

    render_status = load_render_status()
    if image_api_configured:
        success_count = int(render_status.get("ai_success_count", 0))
        target_count = int(render_status.get("ai_target_count", 5))
        provider_name = render_status.get("provider") or image_provider_label
        model_name = render_status.get("model") or image_model_name
        if render_status and success_count == target_count:
            st.success(f"图片模型已连接：{provider_name} / {model_name}，本次 {success_count}/{target_count} 张写实图生成成功，展板已自动合成。")
        elif render_status:
            st.warning(f"图片模型已配置，但本次仅 {success_count}/{target_count} 张写实图生成成功；失败项目已自动回退为离线示意图。")
        else:
            st.info("图片模型密钥已配置。点击上方按钮生成六类写实渲染图。")
    else:
        st.warning("当前未配置图片生成密钥，只能生成专业提示词和离线示意图；写实渲染需要 IMAGE_API_KEY、OPENAI_API_KEY、DASHSCOPE_API_KEY 或 QWEN_IMAGE_API_KEY。")

    image_cards = [
        (f"design_images/{p}产品效果图.png", "产品效果图", "展示整体造型、材质、配色与核心功能。"),
        (f"design_images/{p}爆炸图.png", "产品爆炸图", "展示零部件、装配顺序与结构关系。"),
        (f"design_images/{p}细节图.png", "产品细节图", "展示关键组件、交互区域与材料工艺。"),
        (f"design_images/{p}产品三视图.png", "产品三视图", "展示正视图、侧视图和俯视图。"),
        (f"design_images/{p}产品设计展板.png", "设计展板", "整合设计图、用户需求与研究结论。"),
        (f"design_images/{p}产品使用效果图.png", "产品使用效果图", "展示目标用户、使用动作与真实环境。"),
    ]
    for start in range(0, len(image_cards), 3):
        columns = st.columns(3)
        for column, card in zip(columns, image_cards[start:start + 3]):
            with column:
                with st.container(border=True):
                    render_design_image_card(*card)

    prompt_path = resolve_output_path("design_images/设计图像生成提示词.txt")
    if prompt_path.exists():
        with st.expander("查看可复制到图像模型的提示词"):
            st.code(prompt_path.read_text(encoding="utf-8"))

with tabs[9]:
    st.header("方案评价")
    st.caption("说明 AI 生成方案如何进一步转化为可评价、可优化、可工程化的产品设计方案。")
    st.info("评价链路：用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化。")

    if st.button(
        "📊 生成/刷新方案评价",
        type="primary",
        use_container_width=True,
        disabled=input_path is None,
        help="自动补跑缺失的分析阶段，并生成方案评价表和开题报告实验结果摘要。",
    ):
        if run_stage_sequence(
            EVALUATION_STAGES,
            input_path,
            "10 方案评价",
            "正在生成方案评价与开题报告摘要...",
            "方案评价已生成",
        ):
            st.cache_data.clear()

    evaluation_df = load_sheet("方案评价表.xlsx", None)
    if evaluation_df.empty:
        st.info("方案评价尚未生成，请点击上方按钮或运行“10 方案评价”。")
    else:
        average_score = round(float(evaluation_df["分值"].mean()), 1) if "分值" in evaluation_df.columns else None
        if average_score is not None:
            st.metric("方案综合平均分", f"{average_score} / 100")
        show_table(evaluation_df, "方案评价表", 20)
        st.caption("评价结果可反向指导 AI 生成参数更新，形成“生成—评价—优化”的闭环。")
        optimization_prompt = load_text_output("方案优化建议.txt")
        optimized_parameters = load_json_output("优化后AI生成参数.json")
        if optimization_prompt:
            with st.expander("查看方案优化建议 Prompt"):
                st.code(optimization_prompt, language="text")
        if optimized_parameters:
            with st.expander("查看优化后 AI 生成参数"):
                st.json(optimized_parameters, expanded=False)

with tabs[10]:
    show_downloads()
