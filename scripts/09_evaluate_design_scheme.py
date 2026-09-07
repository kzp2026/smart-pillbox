from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from common import ensure_output_dir, resolve_latest_output_path, save_workbook


EVALUATION_INDICATORS = [
    "需求匹配度",
    "适老化友好性",
    "功能完整性",
    "结构合理性",
    "操作便利性",
    "材料可行性",
    "工程可行性",
    "成本合理性",
    "可优化性",
]


def read_excel(path: Path) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path)
    except Exception:
        return pd.DataFrame()


def read_text(path: Path) -> str:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def ensure_ai_parameters(output_dir: Path, product_name: str) -> None:
    parameter_path = resolve_latest_output_path(output_dir / "AI生成参数表.xlsx")
    if parameter_path.exists():
        return
    script_path = Path(__file__).resolve().parent / "07_generate_ai_parameters.py"
    subprocess.run(
        [sys.executable, str(script_path), "--output-dir", str(output_dir), "--product-name", product_name],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )


def calculate_score(indicator: str, ai_df: pd.DataFrame, scheme_text: str) -> int:
    """返回输入材料完整性自检分，不代表任何设计质量或专家意见。"""
    del indicator  # 保留既有调用签名；自检不对各设计指标作质量判断。
    nonempty_rows = 0
    if not ai_df.empty:
        nonempty_rows = int(ai_df.fillna("").astype(str).apply(lambda row: row.str.strip().ne("").any(), axis=1).sum())
    has_scheme_text = bool(scheme_text and scheme_text.strip())

    if not nonempty_rows and not has_scheme_text:
        return 0

    parameter_score = round(min(nonempty_rows, 8) / 8 * 60)
    scheme_score = 25 if has_scheme_text else 0
    need_score = 15 if "need" in ai_df.columns and ai_df["need"].fillna("").astype(str).str.strip().ne("").any() else 0
    return parameter_score + scheme_score + need_score


def build_evaluation_table(product_name: str, ai_df: pd.DataFrame, scheme_text: str) -> pd.DataFrame:
    suggestions = {
        "需求匹配度": "继续保留评论证据链，优先优化高频痛点对应功能。",
        "适老化友好性": "加强字体、握持、反馈和防误触设计，降低老年用户学习成本。",
        "功能完整性": "检查核心功能、辅助功能和异常状态提示是否形成闭环。",
        "结构合理性": "进一步验证受力路径、装配关系、维护方式和安全冗余。",
        "操作便利性": "减少操作步骤，增加清晰反馈和一眼可懂的交互提示。",
        "材料可行性": "结合使用场景补充防滑、抗菌、防水、耐磨和清洁工艺验证。",
        "工程可行性": "补充零部件标准化、制造工艺、安装方式和可靠性测试方案。",
        "成本合理性": "区分基础版与增强版配置，控制非必要传感器和复杂结构成本。",
        "可优化性": "建立用户反馈复测机制，用评分结果反向更新 AI 生成参数。",
    }
    explanations = {
        "需求匹配度": "评价设计方案是否回应评论数据提取出的核心需求与痛点。",
        "适老化友好性": "评价目标用户在认知、握持、视认、行动辅助方面的友好程度。",
        "功能完整性": "评价核心功能、辅助功能、反馈功能是否完整覆盖使用流程。",
        "结构合理性": "评价功能是否能被清晰、稳定、可维护的结构实现。",
        "操作便利性": "评价用户完成主要任务所需步骤、学习成本和错误恢复难度。",
        "材料可行性": "评价材料与工艺是否适配场景、耐用性、安全性和清洁维护要求。",
        "工程可行性": "评价方案从概念到制造、装配、测试和量产的落地可能性。",
        "成本合理性": "评价功能配置、材料选择和结构复杂度是否符合成本约束。",
        "可优化性": "评价方案是否能通过评价结果继续迭代生成参数和设计方案。",
    }
    return pd.DataFrame(
        [
            {
                "评价指标": indicator,
                "分值": calculate_score(indicator, ai_df, scheme_text),
                "评价说明": f"材料完整性自检：{explanations[indicator]} 此分值不评价设计质量、效果或可行性。",
                "优化建议": suggestions[indicator],
                "来源": "自动规则自检（非专家评分）",
            }
            for indicator in EVALUATION_INDICATORS
        ]
    )


def save_summary_docx(product_name: str, evaluation_df: pd.DataFrame, output_path: Path) -> None:
    try:
        from docx import Document
        from docx.oxml.ns import qn
        from docx.shared import Pt
    except Exception:
        print("未安装 python-docx，跳过 DOCX 输出。")
        return

    average_score = round(float(evaluation_df["分值"].mean()), 1) if not evaluation_df.empty else 0
    weak_items = evaluation_df.sort_values("分值", ascending=True).head(3)["评价指标"].tolist() if not evaluation_df.empty else []

    doc = Document()
    normal = doc.styles["Normal"]
    normal.font.name = "宋体"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "宋体")
    normal.font.size = Pt(10.5)

    doc.add_heading(f"{product_name}材料完整性自检摘要（非专家评分）", level=0)
    doc.add_paragraph(
        "本文件为自动规则自检（非专家评分），仅检查当前是否具备评论、参数和方案等材料，"
        "不构成设计效果、工程可行性或用户体验的实证结论。"
    )
    doc.add_heading("一、技术路线", level=1)
    doc.add_paragraph("用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化。")
    doc.add_heading("二、流程预期材料（实际产物以归档为准）", level=1)
    for item in [
        "需求—功能—结构映射表",
        "AI 生成参数表与 JSON 参数",
        "Prompt 模板",
        "产品设计方案与设计图片",
        "方案评价表",
    ]:
        doc.add_paragraph(item, style="List Bullet")
    doc.add_heading("三、材料完整性自检结果", level=1)
    doc.add_paragraph(f"材料完整性自检平均值为 {average_score} 分；该值不是专家评分，不表示优势或设计质量。")
    doc.add_paragraph(f"待补充材料重点包括：{ '、'.join(weak_items) if weak_items else '暂无' }。")
    doc.add_heading("四、后续验证边界", level=1)
    doc.add_paragraph(
        "当前材料可用于说明系统流程与待验证假设。独立标注、真实专家/用户实验、原型测试与工程验证"
        "仍需另行设计、实施和报告；本自检不能替代上述工作。"
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(output_path)


def build_optimization_prompt(product_name: str, evaluation_df: pd.DataFrame, ai_df: pd.DataFrame) -> str:
    weak_items = evaluation_df.sort_values("分值", ascending=True).head(4).to_dict(orient="records") if not evaluation_df.empty else []
    needs = ai_df["need"].dropna().astype(str).head(8).tolist() if not ai_df.empty and "need" in ai_df.columns else []
    suggestions = [str(item.get("优化建议", "")) for item in weak_items if str(item.get("优化建议", "")).strip()]
    return f"""# {product_name}方案优化建议

本文件用于形成“生成—材料完整性自检—待验证优化”流程。表内分值来自自动规则自检（非专家评分），
仅反映当前材料是否齐备，不代表设计效果、工程可行性或已证实的用户价值。

## 重点需求
{chr(10).join(f"- {need}" for need in needs) if needs else "- 暂无需求参数"}

## 待补充材料项目
{chr(10).join(f"- {item.get('评价指标')}：{item.get('分值')}分；{item.get('优化建议')}" for item in weak_items) if weak_items else "- 暂无评价结果"}

## 可复制优化 Prompt
请基于当前{product_name}设计方案和 AI 生成参数，优先解决以下问题：
{chr(10).join(f"{index + 1}. {suggestion}" for index, suggestion in enumerate(suggestions)) if suggestions else "1. 保持需求证据链，继续优化功能、结构、材料和场景参数。"}

输出要求：
1. 保留用户评论证据与需求来源。
2. 明确更新功能参数、结构参数、材料参数和场景参数。
3. 对材料完整性自检分较低的项目逐项补充待验证方案，不将该分值表述为实证评价。
4. 继续体现：用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化。
5. 明确列出需要独立标注、真实专家/用户实验和原型/工程验证的假设与验证计划。
"""


def build_optimized_parameters(product_name: str, evaluation_df: pd.DataFrame, ai_df: pd.DataFrame) -> dict:
    weak_items = evaluation_df.sort_values("分值", ascending=True).head(4).to_dict(orient="records") if not evaluation_df.empty else []
    optimization_focus = [str(item.get("评价指标", "")) for item in weak_items if str(item.get("评价指标", "")).strip()]
    updated_rows = []
    for _, row in ai_df.iterrows():
        item = row.to_dict()
        constraints = "；".join(str(entry.get("优化建议", "")) for entry in weak_items if str(entry.get("优化建议", "")).strip())
        if constraints:
            item["optimization_constraints"] = constraints
            item["text_prompt_parameter"] = f"{item.get('text_prompt_parameter', '')} 优化约束：{constraints}"
            item["image_prompt_parameter"] = f"{item.get('image_prompt_parameter', '')} 视觉优化重点：{constraints}"
        updated_rows.append(item)
    return {
        "product_type": product_name,
        "optimization_focus": optimization_focus,
        "updated_generation_parameters": updated_rows,
        "logic_chain": "用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="第九阶段：生成方案评价表与开题报告摘要")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--product-name", default="产品", help="产品名称")
    args = parser.parse_args()

    product_name = args.product_name
    output_dir = ensure_output_dir(args.output_dir)
    ensure_ai_parameters(output_dir, product_name)

    ai_df = read_excel(output_dir / "AI生成参数表.xlsx")
    scheme_text = read_text(output_dir / f"{product_name}产品设计方案.txt")
    evaluation_df = build_evaluation_table(product_name, ai_df, scheme_text)
    save_workbook(output_dir / "方案评价表.xlsx", {"方案评价": evaluation_df})
    save_summary_docx(product_name, evaluation_df, output_dir / "开题报告实验结果摘要.docx")
    (output_dir / "方案优化建议.txt").write_text(build_optimization_prompt(product_name, evaluation_df, ai_df), encoding="utf-8")
    (output_dir / "优化后AI生成参数.json").write_text(
        json.dumps(build_optimized_parameters(product_name, evaluation_df, ai_df), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "方案评价结果.json").write_text(
        json.dumps(
            {
                "product_type": product_name,
                "average_score": round(float(evaluation_df["分值"].mean()), 1),
                "items": evaluation_df.to_dict(orient="records"),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(f"产品名称：{product_name}")
    print(f"评价指标数量：{len(evaluation_df)}")
    print(f"已生成：{output_dir / '方案评价表.xlsx'}")
    print(f"已生成：{output_dir / '开题报告实验结果摘要.docx'}")
    print(f"已生成：{output_dir / '方案优化建议.txt'}")
    print(f"已生成：{output_dir / '优化后AI生成参数.json'}")


if __name__ == "__main__":
    main()
