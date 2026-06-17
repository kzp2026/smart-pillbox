from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd

from common import ensure_output_dir, resolve_latest_output_path


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def ensure_mapping_database(output_dir: Path, product_name: str) -> Path:
    mapping_path = output_dir / f"{product_name}_需求功能映射数据库.xlsx"
    latest_mapping_path = resolve_latest_output_path(mapping_path)
    if latest_mapping_path.exists():
        return latest_mapping_path
    script_path = Path(__file__).resolve().parent / "05_build_mapping_database.py"
    subprocess.run(
        [sys.executable, str(script_path), "--output-dir", str(output_dir), "--product-name", product_name],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )
    return mapping_path


def table_to_markdown(df: pd.DataFrame, columns: list[str], max_rows: int = 8) -> str:
    if df.empty:
        return "暂无数据。"
    use_cols = [col for col in columns if col in df.columns]
    rows = []
    for _, row in df.head(max_rows).iterrows():
        parts = [f"{col}：{row.get(col, '')}" for col in use_cols]
        rows.append("- " + "；".join(parts))
    return "\n".join(rows)


def build_offline_scheme(
    product_name: str,
    req_df: pd.DataFrame,
    func_df: pd.DataFrame,
    struct_df: pd.DataFrame,
    opportunity_df: pd.DataFrame,
    topic_df: pd.DataFrame,
) -> str:
    top_requirements = req_df.sort_values("重要度", ascending=False).head(6) if "重要度" in req_df.columns else req_df.head(6)
    top_opportunities = opportunity_df.head(8)

    topic_text = table_to_markdown(topic_df, ["主题名称", "评论数", "主题关键词"], 6)
    requirement_text = table_to_markdown(top_requirements, ["需求名称", "来源关键词", "情感倾向", "重要度"], 8)
    function_text = table_to_markdown(func_df, ["功能名称", "功能类别", "功能描述"], 10)
    structure_text = table_to_markdown(struct_df, ["结构名称", "结构类型", "结构描述"], 10)
    opportunity_text = table_to_markdown(top_opportunities, ["设计机会点", "证据关键词", "建议功能", "建议结构"], 10)

    return f"""# {product_name}产品设计方案

## 一、研究数据基础
本方案基于{product_name}用户评论数据，通过评论清洗、TF-IDF 关键词提取、中文情感分析、主题聚类和需求-功能-结构映射生成。该流程将用户评论中的显性评价转化为可用于产品设计决策的需求证据。

## 二、用户评论主题概览
{topic_text}

## 三、核心用户需求
{requirement_text}

综合分析用户评论数据，{product_name}的核心设计矛盾集中在用户最关注的功能体验、使用便捷性和产品质量等方面。

## 四、产品设计定位
产品定位为"面向目标用户群体的{product_name}智能终端"。设计目标包括：
1. 降低用户使用门槛，保持操作简单、反馈明确。
2. 提升核心功能体验，解决用户痛点。
3. 兼顾美观、便携和日常使用场景中的接受度。

## 五、功能设计方案
{function_text}

功能层面建议采用"核心功能突出 + 辅助功能完善"的组合策略。

## 六、结构设计方案
{structure_text}

## 七、设计机会点
{opportunity_text}

## 八、设计总结
本方案从用户评论数据出发，通过自然语言处理和主题建模技术，系统性地将用户需求映射为产品功能和结构设计建议。输出的映射数据库和知识图谱文件可进一步用于可视化展示需求关联、功能支撑关系和结构实现逻辑。"""


def maybe_llm_enhance(base_scheme: str, product_name: str) -> tuple[str, str]:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        return base_scheme, "离线模板生成"

    try:
        from openai import OpenAI
    except Exception:
        return base_scheme + "\n\n> 注：检测到 LLM_API_KEY，但未安装 openai 包，已使用离线模板生成。", "离线模板生成"

    try:
        base_url = os.getenv("LLM_BASE_URL") or None
        model = os.getenv("LLM_MODEL", "deepseek-chat")
        client = OpenAI(api_key=api_key, base_url=base_url)
        prompt = (
            f"请在不编造数据的前提下，把下面的{product_name}产品设计方案润色为研究生论文实验输出风格，"
            "保留章节结构，突出用户评论数据、需求映射和产品设计决策之间的关系。\n\n"
            + base_scheme
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
        )
        content = response.choices[0].message.content
        if content and len(content.strip()) > 200:
            return content, f"大模型增强：{model}"
    except Exception as exc:
        return base_scheme + f"\n\n> 注：大模型增强失败，已使用离线模板生成。错误信息：{exc}", "离线模板生成"

    return base_scheme, "离线模板生成"


def save_docx(text: str, output_path: Path) -> None:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.shared import Pt
    except Exception:
        print("未安装 python-docx，跳过 DOCX 输出。")
        return

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(10.5)

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("# "):
            paragraph = doc.add_heading(stripped[2:], level=0)
        elif stripped.startswith("## "):
            paragraph = doc.add_heading(stripped[3:], level=1)
        elif stripped.startswith("- "):
            doc.add_paragraph(stripped[2:], style="List Bullet")
        elif stripped[:2].isdigit() and stripped[2:3] == ".":
            doc.add_paragraph(stripped, style="List Number")
        else:
            doc.add_paragraph(stripped)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="第七阶段：生成产品设计方案")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--product-name", default="产品", help="产品名称")
    args = parser.parse_args()

    product_name = args.product_name
    output_dir = ensure_output_dir(args.output_dir)
    mapping_path = ensure_mapping_database(output_dir, product_name)
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"

    req_df = read_sheet(mapping_path, "用户需求表")
    func_df = read_sheet(mapping_path, "产品功能表")
    struct_df = read_sheet(mapping_path, "产品结构表")
    opportunity_df = read_sheet(mapping_path, "设计机会点")
    topic_df = read_sheet(topic_path, "主题汇总")

    base_scheme = build_offline_scheme(product_name, req_df, func_df, struct_df, opportunity_df, topic_df)
    final_scheme, method = maybe_llm_enhance(base_scheme, product_name)

    txt_path = output_dir / f"{product_name}产品设计方案.txt"
    docx_path = output_dir / f"{product_name}产品设计方案.docx"
    txt_path.write_text(final_scheme, encoding="utf-8")
    save_docx(final_scheme, docx_path)

    print(f"产品名称：{product_name}")
    print(f"方案生成方式：{method}")
    print(f"已生成：{txt_path}")
    print(f"已生成：{docx_path}")


if __name__ == "__main__":
    main()
