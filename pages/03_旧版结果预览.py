from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st


ROOT_DIR = Path(__file__).resolve().parents[1]
LEGACY_OUTPUT_DIR = ROOT_DIR / "output"


st.set_page_config(page_title="旧版结果预览", page_icon="📚", layout="wide")
st.title("旧版结果预览")
st.caption("旧版清洗、关键词、情感、主题、图谱、AI 参数、设计方案、设计图片和评价结果集中放在这里，主页面会更轻。")


@st.cache_data(show_spinner=False, max_entries=48)
def load_legacy_sheet(path_text: str, sheet_name: str = "", mtime_ns: int = 0) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name or 0)
    except Exception:
        return pd.DataFrame()


@st.cache_data(show_spinner=False, max_entries=24)
def load_legacy_csv(path_text: str, mtime_ns: int = 0) -> pd.DataFrame:
    path = Path(path_text)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
    except Exception:
        return pd.DataFrame()


def sheet(filename: str, sheet_name: str | None = None) -> pd.DataFrame:
    path = LEGACY_OUTPUT_DIR / filename
    return load_legacy_sheet(str(path), sheet_name or "", path.stat().st_mtime_ns if path.exists() else 0)


def csv(filename: str) -> pd.DataFrame:
    path = LEGACY_OUTPUT_DIR / filename
    return load_legacy_csv(str(path), path.stat().st_mtime_ns if path.exists() else 0)


def show_table(df: pd.DataFrame, title: str, max_rows: int = 80) -> None:
    st.subheader(title)
    if df.empty:
        st.info("该结果尚未生成。可在左侧页面导航打开“01_现有流程备份”运行完整流程。")
        return
    st.dataframe(df.head(max_rows), use_container_width=True)


(
    tab_clean,
    tab_keywords,
    tab_sentiment,
    tab_topics,
    tab_mapping,
    tab_neo4j,
    tab_ai_params,
    tab_scheme,
    tab_images,
    tab_evaluation,
) = st.tabs([
    "评论清洗",
    "关键词提取",
    "情感分析",
    "主题聚类",
    "需求映射",
    "Neo4j图谱",
    "AI生成参数",
    "设计方案",
    "设计图片",
    "方案评价",
])


with tab_clean:
    show_table(sheet("cleaned_comments.xlsx"), "清洗后评论数据", 80)

with tab_keywords:
    show_table(sheet("需求关键词提取结果.xlsx", "关键词排名"), "关键词排名", 80)
    show_table(sheet("需求关键词提取结果.xlsx", "评论关键词明细"), "评论关键词明细", 80)
    show_table(sheet("需求关键词提取结果.xlsx", "关键词共现矩阵"), "关键词共现矩阵", 60)

with tab_sentiment:
    show_table(sheet("情感分析结果.xlsx", "用户痛点"), "用户痛点", 50)
    show_table(sheet("情感分析结果.xlsx", "用户满意点"), "用户满意点", 50)
    show_table(sheet("情感分析结果.xlsx", "关键词情感统计"), "关键词情感统计", 80)
    show_table(sheet("情感分析结果.xlsx", "评论情感明细"), "评论情感明细", 80)

with tab_topics:
    show_table(sheet("BERTopic主题聚类结果.xlsx", "主题汇总"), "主题汇总", 30)
    show_table(sheet("BERTopic主题聚类结果.xlsx", "评论主题聚类结果"), "评论主题聚类明细", 80)

with tab_mapping:
    mapping_files = sorted(LEGACY_OUTPUT_DIR.glob("*_需求功能映射数据库.xlsx"))
    if not mapping_files:
        st.info("需求映射数据库尚未生成。可在“01_现有流程备份”运行完整流程。")
    else:
        mapping_file = mapping_files[-1].name
        st.caption(f"当前预览：{mapping_file}")
        show_table(sheet(mapping_file, "用户需求表"), "产品需求", 50)
        show_table(sheet(mapping_file, "设计机会点"), "设计机会点", 50)
        show_table(sheet(mapping_file, "产品功能表"), "产品功能", 50)
        show_table(sheet(mapping_file, "产品结构表"), "产品结构", 50)
        show_table(sheet(mapping_file, "需求功能映射"), "需求-功能映射", 80)
        show_table(sheet(mapping_file, "功能结构映射"), "功能-结构映射", 80)

with tab_neo4j:
    show_table(csv("neo4j_nodes.csv"), "知识图谱节点表", 100)
    show_table(csv("neo4j_relationships.csv"), "知识图谱关系表", 100)
    cypher_path = LEGACY_OUTPUT_DIR / "import_neo4j.cypher"
    if cypher_path.exists():
        st.subheader("Cypher 导入脚本")
        st.code(cypher_path.read_text(encoding="utf-8"), language="cypher")

with tab_ai_params:
    show_table(sheet("需求—功能—结构映射表.xlsx"), "需求—功能—结构映射表", 80)
    show_table(sheet("AI生成参数表.xlsx"), "AI 生成参数表", 80)
    for rel_path in ["ai_generation_parameters.json", "prompt_template.txt"]:
        path = LEGACY_OUTPUT_DIR / rel_path
        if path.exists():
            with st.expander(f"查看 {rel_path}"):
                st.code(path.read_text(encoding="utf-8"), language="json" if path.suffix == ".json" else "text")

with tab_scheme:
    scheme_files = sorted(LEGACY_OUTPUT_DIR.glob("*产品设计方案.txt"))
    if not scheme_files:
        st.info("设计方案尚未生成。可在“01_现有流程备份”运行完整流程。")
    else:
        scheme_file = scheme_files[-1]
        st.caption(f"当前预览：{scheme_file.name}")
        st.markdown(scheme_file.read_text(encoding="utf-8"))

with tab_images:
    image_dir = LEGACY_OUTPUT_DIR / "design_images"
    image_files = sorted(image_dir.glob("*.png")) if image_dir.exists() else []
    if not image_files:
        st.info("设计图片尚未生成。也可以在主页面“需求生成”里用阿里云百炼生成新版写实效果图。")
    else:
        columns = st.columns(3)
        for index, image_path in enumerate(image_files):
            with columns[index % 3]:
                st.image(str(image_path), caption=image_path.name, use_container_width=True)
                st.download_button(
                    f"下载 {image_path.name}",
                    data=image_path.read_bytes(),
                    file_name=image_path.name,
                    mime="image/png",
                    use_container_width=True,
                )

with tab_evaluation:
    show_table(sheet("方案评价表.xlsx"), "方案评价表", 20)
    for rel_path in ["方案优化建议.txt", "优化后AI生成参数.json", "方案评价结果.json"]:
        path = LEGACY_OUTPUT_DIR / rel_path
        if path.exists():
            with st.expander(f"查看 {rel_path}"):
                st.code(path.read_text(encoding="utf-8"), language="json" if path.suffix == ".json" else "text")
