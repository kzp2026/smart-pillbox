from __future__ import annotations

import argparse
import json
import re
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


def read_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def read_csv(path: Path) -> pd.DataFrame:
    path = resolve_latest_output_path(path)
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_csv(path)
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


def ensure_neo4j_files(output_dir: Path, product_name: str) -> None:
    nodes_path = resolve_latest_output_path(output_dir / "neo4j_nodes.csv")
    rels_path = resolve_latest_output_path(output_dir / "neo4j_relationships.csv")
    if nodes_path.exists() and rels_path.exists():
        return
    script_path = Path(__file__).resolve().parent / "06_build_neo4j_files.py"
    subprocess.run(
        [sys.executable, str(script_path), "--output-dir", str(output_dir), "--product-name", product_name],
        cwd=Path(__file__).resolve().parents[1],
        check=True,
    )


def split_keywords(value: object) -> list[str]:
    text = str(value or "")
    parts = re.split(r"[、,，;\s]+", text)
    return [part.strip() for part in parts if part.strip() and part.strip() != "主题聚类推导"]


def split_comments(value: object) -> list[str]:
    text = str(value or "")
    parts = re.split(r"\s*(?:\||\n|；|;)\s*", text)
    comments = []
    for part in parts:
        cleaned = part.strip(" 「」“”")
        if cleaned and cleaned not in comments:
            comments.append(cleaned)
    return comments


def join_unique(values: list[str], fallback: str = "") -> str:
    deduped = [value for value in dict.fromkeys(str(item).strip() for item in values) if value and value.lower() != "nan"]
    return "、".join(deduped) if deduped else fallback


def lookup_rows(df: pd.DataFrame, key_column: str, value: str) -> pd.DataFrame:
    if df.empty or key_column not in df.columns:
        return pd.DataFrame()
    return df[df[key_column].astype(str) == str(value)]


def collect_evidence_comments(
    req_id: str,
    source_keywords: str,
    topic_req_df: pd.DataFrame,
    topic_df: pd.DataFrame,
    topic_detail_df: pd.DataFrame,
    sentiment_examples_df: pd.DataFrame,
) -> list[str]:
    comments: list[str] = []
    topic_ids: list[str] = []
    if not topic_req_df.empty and {"req_id", "topic_id"}.issubset(topic_req_df.columns):
        topic_ids = topic_req_df[topic_req_df["req_id"].astype(str) == req_id]["topic_id"].astype(str).tolist()

    if topic_ids and not topic_df.empty and {"topic_id", "代表性评论"}.issubset(topic_df.columns):
        for topic_id in topic_ids:
            matched = topic_df[topic_df["topic_id"].astype(str) == topic_id]
            for _, row in matched.iterrows():
                comments.extend(split_comments(row.get("代表性评论", "")))

    if topic_ids and not topic_detail_df.empty and "topic_id" in topic_detail_df.columns:
        comment_column = "comment_original" if "comment_original" in topic_detail_df.columns else "评论" if "评论" in topic_detail_df.columns else ""
        if comment_column:
            for topic_id in topic_ids:
                matched = topic_detail_df[topic_detail_df["topic_id"].astype(str) == topic_id]
                comments.extend(str(value).strip() for value in matched[comment_column].head(3).tolist())

    keywords = split_keywords(source_keywords)
    if not sentiment_examples_df.empty and "关键词" in sentiment_examples_df.columns:
        example_columns = [col for col in sentiment_examples_df.columns if str(col).startswith("示例评论")]
        for keyword in keywords:
            matched = sentiment_examples_df[sentiment_examples_df["关键词"].astype(str).str.contains(re.escape(keyword), na=False)]
            for _, row in matched.iterrows():
                comments.extend(str(row.get(col, "")).strip() for col in example_columns)

    cleaned = []
    for comment in comments:
        if comment and comment.lower() != "nan" and comment not in cleaned:
            cleaned.append(comment)
    return cleaned[:5]


def infer_target_user(product_name: str, evidence_text: str) -> str:
    corpus = f"{product_name} {evidence_text}"
    if any(word in corpus for word in ["老人", "老年", "适老", "药", "扶手", "马桶", "起身"]):
        return "老年用户及家庭照护者"
    if any(word in corpus for word in ["儿童", "孩子", "宝宝"]):
        return "儿童及家庭看护者"
    return f"关注{product_name}体验的目标用户"


def infer_material_parameter(text: str) -> str:
    if any(word in text for word in ["安全", "稳定", "支撑", "防滑", "起身", "扶手"]):
        return "防滑软胶握持面、加厚金属或高强度工程塑料骨架、圆角抗菌易清洁表面"
    if any(word in text for word in ["便携", "小巧", "轻", "携带"]):
        return "轻量化 ABS/PP 外壳、耐磨表面处理、局部软胶缓冲"
    if any(word in text for word in ["卫生", "清洁", "污", "水", "潮湿"]):
        return "防水防污涂层、抗菌材料、可快速擦拭的无缝圆角表面"
    return "耐用工程塑料、局部软胶、易维护表面工艺"


def infer_scene_parameter(product_name: str, text: str) -> str:
    corpus = f"{product_name} {text}"
    if any(word in corpus for word in ["马桶", "扶手", "卫生间", "如厕", "起身", "坐下"]):
        return "家庭卫生间、老人如厕起身与坐下辅助、潮湿防滑环境"
    if any(word in corpus for word in ["药", "提醒", "吃药", "服药"]):
        return "居家用药、老人日常提醒、外出携带备用场景"
    if any(word in corpus for word in ["厨房", "咖啡", "烹饪"]):
        return "家庭厨房、日常高频操作与清洁维护场景"
    return f"{product_name}目标用户的日常高频使用场景"


def build_prompt_template() -> str:
    return """你是一名工业设计研究助手。请严格调用下列 JSON 参数，不要编造评论证据。

产品类型：{product_type}
目标用户：{target_user}
使用场景：{usage_scenario}
用户需求：{need}
用户痛点：{pain_point}
功能参数：{function_parameter}
结构参数：{structure_parameter}
材料参数：{material_parameter}
场景参数：{scene_parameter}

请输出内容：
1. 产品定位
2. 目标用户
3. 核心功能
4. 结构设计
5. 材料工艺
6. 交互方式
7. 使用场景
8. 设计亮点
9. 优化方向

技术路线必须体现：用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化。
"""


def build_parameter_rows(product_name: str, output_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    mapping_path = ensure_mapping_database(output_dir, product_name)
    ensure_neo4j_files(output_dir, product_name)

    req_df = read_sheet(mapping_path, "用户需求表")
    func_df = read_sheet(mapping_path, "产品功能表")
    struct_df = read_sheet(mapping_path, "产品结构表")
    req_func_df = read_sheet(mapping_path, "需求功能映射")
    func_struct_df = read_sheet(mapping_path, "功能结构映射")
    topic_req_df = read_sheet(mapping_path, "主题需求映射")
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    topic_df = read_sheet(topic_path, "主题汇总")
    topic_detail_df = read_sheet(topic_path, "评论主题聚类结果")
    sentiment_examples_df = read_sheet(output_dir / "情感分析结果.xlsx", "情感示例评论")

    if not req_df.empty and "重要度" in req_df.columns:
        req_df = req_df.sort_values("重要度", ascending=False)

    mapping_rows: list[dict] = []
    ai_rows: list[dict] = []
    all_evidence: list[str] = []

    for _, req in req_df.iterrows():
        req_id = str(req.get("req_id", ""))
        need = str(req.get("需求名称", req.get("需求类别", ""))).strip()
        if not req_id or not need:
            continue

        req_func_rows = lookup_rows(req_func_df, "req_id", req_id)
        func_ids = req_func_rows["func_id"].astype(str).tolist() if not req_func_rows.empty and "func_id" in req_func_rows.columns else []
        matched_funcs = func_df[func_df["func_id"].astype(str).isin(func_ids)] if not func_df.empty and "func_id" in func_df.columns else pd.DataFrame()
        function_names = matched_funcs["功能名称"].astype(str).tolist() if "功能名称" in matched_funcs.columns else []
        function_desc = matched_funcs["功能描述"].astype(str).tolist() if "功能描述" in matched_funcs.columns else []

        struct_ids: list[str] = []
        if func_ids and not func_struct_df.empty and {"func_id", "structure_id"}.issubset(func_struct_df.columns):
            struct_ids = func_struct_df[func_struct_df["func_id"].astype(str).isin(func_ids)]["structure_id"].astype(str).tolist()
        matched_structs = struct_df[struct_df["structure_id"].astype(str).isin(struct_ids)] if not struct_df.empty and "structure_id" in struct_df.columns else pd.DataFrame()
        structure_names = matched_structs["结构名称"].astype(str).tolist() if "结构名称" in matched_structs.columns else []
        structure_desc = matched_structs["结构描述"].astype(str).tolist() if "结构描述" in matched_structs.columns else []

        source_keywords = str(req.get("来源关键词", ""))
        evidence_comments = collect_evidence_comments(req_id, source_keywords, topic_req_df, topic_df, topic_detail_df, sentiment_examples_df)
        all_evidence.extend(evidence_comments)
        pain_point = "；".join(evidence_comments[:2]) if evidence_comments else str(req.get("需求描述", "由用户评论主题和关键词推导。"))
        evidence_text = " ".join([need, source_keywords, pain_point, *function_names, *structure_names])

        function_parameter = join_unique(function_names + function_desc, str(req.get("需求描述", "")))
        structure_parameter = join_unique(structure_names + structure_desc, "围绕核心功能配置稳定、易用、可维护的结构")
        material_parameter = infer_material_parameter(evidence_text)
        scene_parameter = infer_scene_parameter(product_name, evidence_text)
        text_prompt_parameter = (
            f"围绕{product_name}的“{need}”，结合用户痛点“{pain_point}”，"
            "生成产品定位、目标用户、核心功能、结构设计、材料工艺、交互方式、使用场景、设计亮点和优化方向。"
        )
        image_prompt_parameter = (
            f"写实工业设计渲染图，产品为{product_name}，突出{join_unique(function_names, need)}，"
            f"结构重点为{join_unique(structure_names, structure_parameter)}，材料为{material_parameter}，"
            f"场景为{scene_parameter}，产品级灯光，干净背景，细节清晰。"
        )

        path_segments = [product_name, need]
        if function_names:
            path_segments.append(function_names[0])
        if structure_names:
            path_segments.append(structure_names[0])
        graph_path = " → ".join(path_segments)

        mapping_rows.append(
            {
                "需求主题": need,
                "用户痛点": pain_point,
                "知识图谱路径": graph_path,
                "功能参数": function_parameter,
                "结构参数": structure_parameter,
                "材料参数": material_parameter,
                "场景参数": scene_parameter,
                "AI文本生成参数": text_prompt_parameter,
                "AI图像生成参数": image_prompt_parameter,
                "评价指标": "、".join(EVALUATION_INDICATORS),
            }
        )
        ai_rows.append(
            {
                "product_type": product_name,
                "target_user": infer_target_user(product_name, evidence_text),
                "usage_scenario": scene_parameter,
                "core_needs": need,
                "need": need,
                "pain_point": pain_point,
                "function_parameter": function_parameter,
                "structure_parameter": structure_parameter,
                "material_parameter": material_parameter,
                "scene_parameter": scene_parameter,
                "text_prompt_parameter": text_prompt_parameter,
                "image_prompt_parameter": image_prompt_parameter,
                "knowledge_graph_path": graph_path,
                "evaluation_indicators": "、".join(EVALUATION_INDICATORS),
                "原始评论证据": " | ".join(evidence_comments),
            }
        )

    mapping_df = pd.DataFrame(mapping_rows, columns=[
        "需求主题",
        "用户痛点",
        "知识图谱路径",
        "功能参数",
        "结构参数",
        "材料参数",
        "场景参数",
        "AI文本生成参数",
        "AI图像生成参数",
        "评价指标",
    ])
    ai_df = pd.DataFrame(ai_rows)

    core_needs = mapping_df["需求主题"].head(8).tolist() if not mapping_df.empty else []
    target_user = infer_target_user(product_name, " ".join(all_evidence + core_needs))
    usage_scenario = mapping_df["场景参数"].iloc[0] if not mapping_df.empty else f"{product_name}目标用户的日常高频使用场景"
    primary_row = ai_rows[0] if ai_rows else {}
    payload = {
        "product_type": product_name,
        "target_user": target_user,
        "usage_scenario": usage_scenario,
        "core_needs": core_needs,
        "need": primary_row.get("need", ""),
        "pain_point": primary_row.get("pain_point", ""),
        "function_parameter": primary_row.get("function_parameter", ""),
        "structure_parameter": primary_row.get("structure_parameter", ""),
        "material_parameter": primary_row.get("material_parameter", ""),
        "scene_parameter": primary_row.get("scene_parameter", ""),
        "text_prompt_parameter": primary_row.get("text_prompt_parameter", ""),
        "image_prompt_parameter": primary_row.get("image_prompt_parameter", ""),
        "generation_parameters": [
            {
                "need": row["need"],
                "pain_point": row["pain_point"],
                "function_parameter": row["function_parameter"],
                "structure_parameter": row["structure_parameter"],
                "material_parameter": row["material_parameter"],
                "scene_parameter": row["scene_parameter"],
                "text_prompt_parameter": row["text_prompt_parameter"],
                "image_prompt_parameter": row["image_prompt_parameter"],
            }
            for row in ai_rows
        ],
        "logic_chain": "用户评论数据 → 需求提取 → 知识图谱关系路径 → AI 生成参数 → Prompt 模板 → 设计方案生成 → 方案评价与优化",
    }
    return mapping_df, ai_df, payload


def main() -> None:
    parser = argparse.ArgumentParser(description="第七阶段：生成 AI 可识别参数")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--product-name", default="产品", help="产品名称")
    args = parser.parse_args()

    product_name = args.product_name
    output_dir = ensure_output_dir(args.output_dir)
    mapping_df, ai_df, payload = build_parameter_rows(product_name, output_dir)

    save_workbook(output_dir / "需求—功能—结构映射表.xlsx", {"需求功能结构映射": mapping_df})
    save_workbook(output_dir / "AI生成参数表.xlsx", {"AI生成参数": ai_df})
    (output_dir / "ai_generation_parameters.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "prompt_template.txt").write_text(build_prompt_template(), encoding="utf-8")

    print(f"产品名称：{product_name}")
    print(f"AI生成参数数量：{len(ai_df)}")
    print(f"已生成：{output_dir / '需求—功能—结构映射表.xlsx'}")
    print(f"已生成：{output_dir / 'AI生成参数表.xlsx'}")
    print(f"已生成：{output_dir / 'ai_generation_parameters.json'}")
    print(f"已生成：{output_dir / 'prompt_template.txt'}")


if __name__ == "__main__":
    main()
