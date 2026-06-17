from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


# =========================
# 1. 基础配置
# =========================

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
SCRIPTS_DIR = ROOT_DIR / "scripts"
OUTPUT_DIR.mkdir(exist_ok=True)

# 阶段定义（去掉产品名称，改为动态）
STAGES = [
    ("01 评论清洗", "01_clean_comments.py", "cleaned_comments.xlsx"),
    ("02 关键词提取", "02_extract_keywords.py", "需求关键词提取结果.xlsx"),
    ("03 情感分析", "03_sentiment_analysis.py", "情感分析结果.xlsx"),
    ("04 主题聚类", "04_bertopic_clustering.py", "BERTopic主题聚类结果.xlsx"),
    ("05 需求映射", "05_build_mapping_database.py", "{product}_需求功能映射数据库.xlsx"),
    ("06 Neo4j图谱", "06_build_neo4j_files.py", "neo4j_nodes.csv"),
    ("07 设计方案", "07_generate_design_scheme.py", "{product}产品设计方案.docx"),
    ("08 设计图片", "08_generate_design_visuals.py", "design_images/{product}产品设计展板.png"),
]


def get_product_name() -> str:
    """获取当前产品名称"""
    return st.session_state.get("product_name", "产品")


def output_filename(stage_output: str) -> str:
    """把阶段输出文件名中的 {product} 替换为实际产品名"""
    return stage_output.replace("{product}", get_product_name())


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
        f"{p}产品设计方案.docx",
        f"{p}产品设计方案.txt",
        f"design_images/{p}设计效果图.png",
        f"design_images/{p}细节图.png",
        f"design_images/{p}场景使用效果图.png",
        f"design_images/{p}产品设计展板.png",
        "design_images/设计图像生成提示词.txt",
        "design_images/设计图像清单.xlsx",
    ]


# =========================
# 2. 文件读取与运行工具
# =========================

def save_uploaded_file(uploaded_file) -> Path | None:
    if uploaded_file is None:
        return None
    suffix = Path(uploaded_file.name).suffix.lower()
    target = OUTPUT_DIR / f"uploaded_comments{suffix}"
    target.write_bytes(uploaded_file.getbuffer())
    return target


def run_stage(script_name: str, input_path: Path | None = None) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        str(SCRIPTS_DIR / script_name),
        "--output-dir", str(OUTPUT_DIR),
        "--product-name", get_product_name(),
    ]
    if input_path and script_name in {
        "01_clean_comments.py", "02_extract_keywords.py",
        "03_sentiment_analysis.py", "04_bertopic_clustering.py",
    }:
        command.extend(["--input", str(input_path)])
    return subprocess.run(command, cwd=ROOT_DIR, capture_output=True, text=True)


@st.cache_data(show_spinner=False)
def read_excel_cached(path: str, sheet_name: str | None = None):
    if sheet_name is None:
        return pd.read_excel(path, sheet_name=None)
    return pd.read_excel(path, sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def read_csv_cached(path: str) -> pd.DataFrame:
    return pd.read_csv(path)


def load_sheet(filename: str, sheet_name: str) -> pd.DataFrame:
    path = OUTPUT_DIR / output_filename(filename)
    if not path.exists():
        return pd.DataFrame()
    try:
        return read_excel_cached(str(path), sheet_name)
    except Exception:
        return pd.DataFrame()


def file_ready(relative_path: str) -> bool:
    return (OUTPUT_DIR / output_filename(relative_path)).exists()


def show_table(df: pd.DataFrame, title: str, max_rows: int = 100) -> None:
    st.subheader(title)
    if df.empty:
        st.info("该结果尚未生成，请先运行对应阶段。")
        return
    st.dataframe(df.head(max_rows), use_container_width=True)


def show_downloads() -> None:
    st.header("📥 下载中心")
    found = False
    for rel_path in get_download_files():
        full = OUTPUT_DIR / rel_path
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


def render_image(rel_path: str, caption: str) -> None:
    full = OUTPUT_DIR / rel_path
    if full.exists():
        st.image(str(full), caption=caption, use_container_width=True)
    else:
        st.caption(f"⏳ {caption} 尚未生成")


# =========================
# 3. 页面 UI
# =========================

st.set_page_config(page_title="用户评论驱动的产品设计系统", page_icon="📊", layout="wide")

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

    st.divider()

    # 一键生成
    if st.button("🚀 一键生成全部研究结果", type="primary", use_container_width=True):
        input_path = save_uploaded_file(uploaded)
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
        st.rerun()

    st.divider()

    # 分阶段运行
    st.subheader("🔧 分阶段运行")
    input_path = save_uploaded_file(uploaded)
    for stage_name, script_name, _ in STAGES:
        if st.button(f"▶ {stage_name}", use_container_width=True):
            with st.spinner(f"运行 {stage_name}..."):
                result = run_stage(script_name, input_path)
                if result.returncode == 0:
                    st.success(f"✅ {stage_name} 完成")
                else:
                    st.error(f"❌ {stage_name}：{result.stderr[:300]}")
            st.rerun()


# --- 主区域 ---
p = get_product_name()
st.title(f"📊 {p} — 用户评论驱动的产品设计系统")
st.caption("上传任意产品评论数据 → 自动完成 NLP 分析 → 生成产品设计方案与设计图")

# 标签页
tabs = st.tabs([
    "📋 评论清洗", "🔑 关键词提取", "💬 情感分析", "🧩 主题聚类",
    "🗺 需求映射", "🕸 Neo4j图谱", "📝 设计方案", "🎨 设计图片", "📥 下载中心",
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
    nodes_path = OUTPUT_DIR / "neo4j_nodes.csv"
    rels_path = OUTPUT_DIR / "neo4j_relationships.csv"
    cypher_path = OUTPUT_DIR / "import_neo4j.cypher"
    if nodes_path.exists():
        show_table(read_csv_cached(str(nodes_path)), "知识图谱节点表", 100)
    else:
        st.info("节点表尚未生成。")
    if rels_path.exists():
        show_table(read_csv_cached(str(rels_path)), "知识图谱关系表", 100)
    else:
        st.info("关系表尚未生成。")
    if cypher_path.exists():
        st.subheader("Cypher 导入脚本")
        st.code(cypher_path.read_text(encoding="utf-8"), language="cypher")

with tabs[6]:
    st.header(f"{p} 产品设计方案")
    txt_path = OUTPUT_DIR / f"{p}产品设计方案.txt"
    if txt_path.exists():
        st.markdown(txt_path.read_text(encoding="utf-8"))
    else:
        st.info("设计方案尚未生成。")

with tabs[7]:
    st.header("设计图片与展板")
    col_a, col_b = st.columns(2)
    with col_a:
        render_image(f"design_images/{p}设计效果图.png", "产品设计效果图")
        render_image(f"design_images/{p}场景使用效果图.png", "场景使用效果图")
    with col_b:
        render_image(f"design_images/{p}细节图.png", "产品细节图")
    render_image(f"design_images/{p}产品设计展板.png", "产品设计展板")

    prompt_path = OUTPUT_DIR / "design_images" / "设计图像生成提示词.txt"
    if prompt_path.exists():
        with st.expander("查看可复制到图像模型的提示词"):
            st.code(prompt_path.read_text(encoding="utf-8"))

with tabs[8]:
    show_downloads()
