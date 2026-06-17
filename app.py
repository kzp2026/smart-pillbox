from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd
import streamlit as st


# =========================
# 1. 智能体网页基础配置
# =========================

ROOT_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT_DIR / "output"
SCRIPTS_DIR = ROOT_DIR / "scripts"
OUTPUT_DIR.mkdir(exist_ok=True)

STAGES = [
    ("01 评论数据读取与清洗", "01_clean_comments.py", "cleaned_comments.xlsx"),
    ("02 TF-IDF 用户需求关键词提取", "02_extract_keywords.py", "需求关键词提取结果.xlsx"),
    ("03 中文评论情感分析", "03_sentiment_analysis.py", "情感分析结果.xlsx"),
    ("04 BERTopic/KMeans 主题聚类", "04_bertopic_clustering.py", "BERTopic主题聚类结果.xlsx"),
    ("05 需求-功能-结构映射数据库", "05_build_mapping_database.py", "智能药盒需求功能映射数据库.xlsx"),
    ("06 Neo4j 知识图谱导入文件", "06_build_neo4j_files.py", "neo4j_nodes.csv"),
    ("07 智能药盒产品设计方案", "07_generate_design_scheme.py", "智能药盒产品设计方案.docx"),
    ("08 设计图片与展板生成", "08_generate_design_visuals.py", "design_images/智能药盒产品设计展板.png"),
]

DOWNLOAD_FILES = [
    "cleaned_comments.xlsx",
    "需求关键词提取结果.xlsx",
    "情感分析结果.xlsx",
    "BERTopic主题聚类结果.xlsx",
    "智能药盒需求功能映射数据库.xlsx",
    "neo4j_nodes.csv",
    "neo4j_relationships.csv",
    "import_neo4j.cypher",
    "智能药盒产品设计方案.docx",
    "智能药盒产品设计方案.txt",
    "design_images/智能药盒设计效果图.png",
    "design_images/智能药盒三视图.png",
    "design_images/智能药盒爆炸图.png",
    "design_images/智能药盒场景使用效果图.png",
    "design_images/智能药盒产品设计展板.png",
    "design_images/设计图像生成提示词.txt",
    "design_images/设计图像清单.xlsx",
]


# =========================
# 2. 文件读取与运行工具
# =========================

def save_uploaded_file(uploaded_file) -> Path | None:
    """保存用户上传的评论数据。"""
    if uploaded_file is None:
        return None
    suffix = Path(uploaded_file.name).suffix.lower()
    target = OUTPUT_DIR / f"uploaded_comments{suffix}"
    target.write_bytes(uploaded_file.getbuffer())
    return target


def run_stage(script_name: str, input_path: Path | None = None) -> subprocess.CompletedProcess:
    """调用阶段脚本，避免数字开头脚本名 import 问题。"""
    command = [
        sys.executable,
        str(SCRIPTS_DIR / script_name),
        "--output-dir",
        str(OUTPUT_DIR),
    ]
    if input_path and script_name in {
        "01_clean_comments.py",
        "02_extract_keywords.py",
        "03_sentiment_analysis.py",
        "04_bertopic_clustering.py",
    }:
        command.extend(["--input", str(input_path)])
    return subprocess.run(command, cwd=ROOT_DIR, capture_output=True, text=True)


@st.cache_data(show_spinner=False)
def read_excel_cached(path: str, sheet_name: str | None = None):
    """缓存读取 Excel，提升网页切换速度。"""
    if sheet_name is None:
        return pd.read_excel(path, sheet_name=None)
    return pd.read_excel(path, sheet_name=sheet_name)


@st.cache_data(show_spinner=False)
def read_csv_cached(path: str) -> pd.DataFrame:
    """缓存读取 CSV。"""
    return pd.read_csv(path)


def load_sheet(filename: str, sheet_name: str) -> pd.DataFrame:
    """读取 output 下某个 Excel 文件的指定 Sheet。"""
    path = OUTPUT_DIR / filename
    if not path.exists():
        return pd.DataFrame()
    try:
        return read_excel_cached(str(path), sheet_name)
    except Exception:
        return pd.DataFrame()


def file_ready(relative_path: str) -> bool:
    """判断输出文件是否存在。"""
    return (OUTPUT_DIR / relative_path).exists()


def metric_card(label: str, value: object, help_text: str = "") -> None:
    """显示指标卡。"""
    st.metric(label, value, help=help_text or None)


def show_table(df: pd.DataFrame, title: str, max_rows: int = 100) -> None:
    """统一表格展示。"""
    st.subheader(title)
    if df.empty:
        st.info("该结果尚未生成，请先运行对应阶段。")
        return
    st.dataframe(df.head(max_rows), use_container_width=True)


def show_downloads() -> None:
    """显示所有结果文件下载入口。"""
    st.subheader("结果文件下载")
    cols = st.columns(2)
    for idx, filename in enumerate(DOWNLOAD_FILES):
        path = OUTPUT_DIR / filename
        with cols[idx % 2]:
            if path.exists():
                st.download_button(
                    label=f"下载 {Path(filename).name}",
                    data=path.read_bytes(),
                    file_name=Path(filename).name,
                    key=f"download_{filename}",
                )
            else:
                st.caption(f"尚未生成：{filename}")


def render_image(relative_path: str, caption: str) -> None:
    """展示生成的设计图片。"""
    path = OUTPUT_DIR / relative_path
    if path.exists():
        st.image(str(path), caption=caption, use_container_width=True)
    else:
        st.info(f"尚未生成：{relative_path}")


# =========================
# 3. 页面布局
# =========================

st.set_page_config(page_title="智能药盒产品设计智能体", layout="wide")
st.title("智能药盒产品设计智能体")
st.caption("导入用户评论数据后，自动生成评论清洗、需求关键词、痛点分析、主题聚类、需求-功能-结构映射、Neo4j 知识图谱文件、产品设计方案、设计图片与展板。")

with st.sidebar:
    st.header("1. 导入评论数据")
    uploaded = st.file_uploader("上传评论数据（xlsx/xls/csv）", type=["xlsx", "xls", "csv"])
    uploaded_path = save_uploaded_file(uploaded)
    st.caption("未上传时默认读取 data/京东智能药盒评论(.xlsx/.xls/.csv)")

    st.header("2. 运行智能体")
    if st.button("一键生成全部研究结果", type="primary", use_container_width=True):
        logs = []
        progress = st.progress(0)
        failed = False
        for idx, (stage_name, script_name, _) in enumerate(STAGES, start=1):
            with st.spinner(f"正在运行：{stage_name}"):
                result = run_stage(script_name, uploaded_path)
            logs.append(f"===== {stage_name} =====\n{result.stdout}\n{result.stderr}")
            progress.progress(idx / len(STAGES))
            if result.returncode != 0:
                failed = True
                break
        st.session_state["last_logs"] = "\n".join(logs)
        if failed:
            st.error("流程运行中断，请查看日志。")
        else:
            st.success("全部研究结果已生成。")
        st.cache_data.clear()

    stage_names = [stage[0] for stage in STAGES]
    selected_stage = st.selectbox("单独运行某一步", stage_names)
    if st.button("运行选中阶段", use_container_width=True):
        stage = STAGES[stage_names.index(selected_stage)]
        result = run_stage(stage[1], uploaded_path)
        st.session_state["last_logs"] = f"===== {stage[0]} =====\n{result.stdout}\n{result.stderr}"
        if result.returncode == 0:
            st.success(f"{stage[0]} 已完成。")
        else:
            st.error(f"{stage[0]} 运行失败。")
        st.cache_data.clear()

    st.header("3. 输出状态")
    ready_count = sum(1 for _, _, path in STAGES if file_ready(path))
    st.progress(ready_count / len(STAGES))
    st.caption(f"已完成 {ready_count}/{len(STAGES)} 个阶段")

if "last_logs" in st.session_state:
    with st.expander("查看最近运行日志", expanded=False):
        st.code(st.session_state["last_logs"])


# =========================
# 4. 智能体结果展示
# =========================

tabs = st.tabs([
    "总览",
    "数据清洗",
    "需求关键词",
    "痛点与情感",
    "主题聚类",
    "映射数据库",
    "知识图谱",
    "设计方案",
    "设计图片与展板",
    "下载中心",
])

with tabs[0]:
    st.header("研究结果总览")
    cleaned_df = load_sheet("cleaned_comments.xlsx", "清洗后评论")
    keyword_df = load_sheet("需求关键词提取结果.xlsx", "关键词排名")
    sentiment_detail_df = load_sheet("情感分析结果.xlsx", "评论情感明细")
    topic_df = load_sheet("BERTopic主题聚类结果.xlsx", "主题汇总")
    req_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "用户需求表")

    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        metric_card("有效评论", len(cleaned_df) if not cleaned_df.empty else 0)
    with col2:
        metric_card("需求关键词", len(keyword_df) if not keyword_df.empty else 0)
    with col3:
        if not sentiment_detail_df.empty and "sentiment_label" in sentiment_detail_df.columns:
            metric_card("负向评论", int((sentiment_detail_df["sentiment_label"] == "负向").sum()))
        else:
            metric_card("负向评论", 0)
    with col4:
        metric_card("主题数量", len(topic_df) if not topic_df.empty else 0)
    with col5:
        metric_card("需求类别", len(req_df) if not req_df.empty else 0)

    show_table(req_df.sort_values("重要度", ascending=False) if "重要度" in req_df.columns else req_df, "核心用户需求", 10)
    if file_ready("design_images/智能药盒产品设计展板.png"):
        st.subheader("最终展板预览")
        render_image("design_images/智能药盒产品设计展板.png", "智能药盒产品设计展板")

with tabs[1]:
    st.header("评论数据读取与清洗")
    info_df = load_sheet("cleaned_comments.xlsx", "字段识别说明")
    cleaned_df = load_sheet("cleaned_comments.xlsx", "清洗后评论")
    if not info_df.empty:
        st.write("字段识别结果")
        st.dataframe(info_df, use_container_width=True)
    show_table(cleaned_df, "清洗后评论数据", 80)

with tabs[2]:
    st.header("TF-IDF 用户需求关键词")
    keyword_df = load_sheet("需求关键词提取结果.xlsx", "关键词排名")
    detail_df = load_sheet("需求关键词提取结果.xlsx", "评论关键词明细")
    co_df = load_sheet("需求关键词提取结果.xlsx", "关键词共现矩阵")
    show_table(keyword_df, "关键词排名", 80)
    show_table(detail_df, "评论关键词明细", 80)
    show_table(co_df, "关键词共现矩阵", 60)

with tabs[3]:
    st.header("用户痛点与中文情感分析")
    sentiment_detail_df = load_sheet("情感分析结果.xlsx", "评论情感明细")
    keyword_sentiment_df = load_sheet("情感分析结果.xlsx", "关键词情感统计")
    pain_df = load_sheet("情感分析结果.xlsx", "用户痛点")
    highlight_df = load_sheet("情感分析结果.xlsx", "用户满意点")
    show_table(pain_df, "用户痛点", 50)
    show_table(highlight_df, "用户满意点", 50)
    show_table(keyword_sentiment_df, "关键词情感统计", 80)
    show_table(sentiment_detail_df, "评论情感明细", 80)

with tabs[4]:
    st.header("评论主题聚类")
    topic_df = load_sheet("BERTopic主题聚类结果.xlsx", "主题汇总")
    cluster_df = load_sheet("BERTopic主题聚类结果.xlsx", "评论主题聚类结果")
    note_df = load_sheet("BERTopic主题聚类结果.xlsx", "算法说明")
    if not note_df.empty:
        st.info(str(note_df.iloc[0].to_dict()))
    show_table(topic_df, "主题汇总", 30)
    show_table(cluster_df, "评论主题聚类明细", 80)

with tabs[5]:
    st.header("用户需求-产品功能-产品结构映射数据库")
    req_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "用户需求表")
    func_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "产品功能表")
    struct_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "产品结构表")
    req_func_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "需求功能映射")
    func_struct_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "功能结构映射")
    opportunity_df = load_sheet("智能药盒需求功能映射数据库.xlsx", "设计机会点")

    show_table(req_df, "产品需求", 50)
    show_table(opportunity_df, "设计机会点", 50)
    show_table(func_df, "产品功能", 50)
    show_table(struct_df, "产品结构", 50)
    show_table(req_func_df, "需求-功能映射", 80)
    show_table(func_struct_df, "功能-结构映射", 80)

with tabs[6]:
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

with tabs[7]:
    st.header("智能药盒产品设计方案")
    txt_path = OUTPUT_DIR / "智能药盒产品设计方案.txt"
    if txt_path.exists():
        st.markdown(txt_path.read_text(encoding="utf-8"))
    else:
        st.info("设计方案尚未生成。")

with tabs[8]:
    st.header("设计图片、三视图、爆炸图、场景图与展板")
    col_a, col_b = st.columns(2)
    with col_a:
        render_image("design_images/智能药盒设计效果图.png", "设计效果图")
        render_image("design_images/智能药盒爆炸图.png", "爆炸图")
    with col_b:
        render_image("design_images/智能药盒三视图.png", "三视图")
        render_image("design_images/智能药盒场景使用效果图.png", "场景使用效果图")
    render_image("design_images/智能药盒产品设计展板.png", "产品设计展板")

    prompt_path = OUTPUT_DIR / "design_images" / "设计图像生成提示词.txt"
    if prompt_path.exists():
        with st.expander("查看可复制到图像模型的提示词"):
            st.code(prompt_path.read_text(encoding="utf-8"))

with tabs[9]:
    show_downloads()
