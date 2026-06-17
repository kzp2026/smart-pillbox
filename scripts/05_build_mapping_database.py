from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from common import (
    MAPPING_RULES,
    as_project_path,
    compute_tfidf,
    ensure_output_dir,
    load_cleaned_or_build,
    save_workbook,
    split_words,
    stable_id,
)


def read_excel_sheet(path: Path, sheet_name: str) -> pd.DataFrame:
    """安全读取 Excel Sheet，不存在时返回空表。"""
    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_excel(path, sheet_name=sheet_name)
    except Exception:
        return pd.DataFrame()


def keyword_matches_rule(keyword: str, rule: dict) -> bool:
    """判断关键词是否命中某条需求映射规则。"""
    lowered = str(keyword).lower()
    return any(term.lower() in lowered or lowered in term.lower() for term in rule["terms"])


def collect_keyword_data(output_dir: Path) -> pd.DataFrame:
    """读取关键词结果；不存在时基于清洗数据快速计算。"""
    keyword_path = output_dir / "需求关键词提取结果.xlsx"
    keyword_df = read_excel_sheet(keyword_path, "关键词排名")
    if not keyword_df.empty:
        return keyword_df

    cleaned_df = load_cleaned_or_build(None, output_dir)
    tokens_list = [split_words(value) for value in cleaned_df["words"]]
    return compute_tfidf(tokens_list, max_features=80, min_df=2)


def collect_sentiment_data(output_dir: Path) -> pd.DataFrame:
    """读取关键词情感统计。"""
    sentiment_path = output_dir / "情感分析结果.xlsx"
    return read_excel_sheet(sentiment_path, "关键词情感统计")


def collect_topic_data(output_dir: Path) -> pd.DataFrame:
    """读取主题聚类汇总。"""
    topic_path = output_dir / "BERTopic主题聚类结果.xlsx"
    return read_excel_sheet(topic_path, "主题汇总")


def main() -> None:
    """第五阶段：构建用户需求-产品功能-产品结构映射数据库。"""
    parser = argparse.ArgumentParser(description="第五阶段：构建需求功能结构映射数据库")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    keyword_df = collect_keyword_data(output_dir)
    sentiment_df = collect_sentiment_data(output_dir)
    topic_df = collect_topic_data(output_dir)

    sentiment_map = {}
    if not sentiment_df.empty and "关键词" in sentiment_df.columns:
        for _, row in sentiment_df.iterrows():
            sentiment_map[str(row.get("关键词", ""))] = {
                "平均情感分": row.get("平均情感分", ""),
                "主要情感倾向": row.get("主要情感倾向", ""),
                "负向评论数": row.get("负向评论数", 0),
                "正向评论数": row.get("正向评论数", 0),
            }

    requirement_rows = []
    function_rows = []
    structure_rows = []
    req_func_rows = []
    func_struct_rows = []
    topic_req_rows = []
    opportunity_rows = []

    function_seen = {}
    structure_seen = {}

    for rule in MAPPING_RULES:
        matched_keywords = []
        tfidf_score = 0.0
        doc_freq = 0
        negative_count = 0
        positive_count = 0

        if not keyword_df.empty:
            for _, row in keyword_df.iterrows():
                keyword = str(row.get("关键词", ""))
                if keyword_matches_rule(keyword, rule):
                    matched_keywords.append(keyword)
                    tfidf_score += float(row.get("TF-IDF权重", 0) or 0)
                    doc_freq += int(row.get("文档频次", 0) or 0)
                    sentiment = sentiment_map.get(keyword, {})
                    negative_count += int(sentiment.get("负向评论数", 0) or 0)
                    positive_count += int(sentiment.get("正向评论数", 0) or 0)

        # 即使某类需求没有被关键词直接命中，也保留为领域规则补充，便于论文实验完整说明。
        req_id = stable_id("REQ", rule["category"])
        func_id = function_seen.setdefault(rule["function"], stable_id("FUNC", rule["function"]))
        structure_id = structure_seen.setdefault(rule["structure"], stable_id("STRU", rule["structure"]))

        importance = round(tfidf_score * 100 + doc_freq * 0.2 + negative_count * 1.5, 4)
        if importance == 0:
            importance = 1.0

        sentiment_label = "痛点优先" if negative_count > 0 else "满意保持" if positive_count > 0 else "规则补充"
        keyword_text = "、".join(dict.fromkeys(matched_keywords)) if matched_keywords else "领域规则补充"

        requirement_rows.append({
            "req_id": req_id,
            "需求名称": rule["category"],
            "需求类别": rule["category"],
            "来源关键词": keyword_text,
            "需求描述": rule["description"],
            "情感倾向": sentiment_label,
            "重要度": importance,
            "负向评论数": negative_count,
            "正向评论数": positive_count,
        })

        if rule["function"] not in {row.get("功能名称") for row in function_rows}:
            function_rows.append({
                "func_id": func_id,
                "功能名称": rule["function"],
                "功能类别": rule["category"],
                "功能描述": rule["description"],
                "设计目标": f"响应“{rule['category']}”，提升智能药盒使用体验。",
                "优先级": 1 if negative_count > 0 else 2,
            })

        if rule["structure"] not in {row.get("结构名称") for row in structure_rows}:
            structure_rows.append({
                "structure_id": structure_id,
                "结构名称": rule["structure"],
                "结构类型": rule["category"],
                "结构描述": f"用于实现“{rule['function']}”的关键结构配置。",
            })

        req_func_rows.append({
            "req_id": req_id,
            "func_id": func_id,
            "映射理由": f"{rule['category']}可通过{rule['function']}实现。",
            "映射强度": importance,
        })

        func_struct_rows.append({
            "func_id": func_id,
            "structure_id": structure_id,
            "映射理由": f"{rule['function']}依赖{rule['structure']}。",
        })

        opportunity_rows.append({
            "设计机会点": rule["category"],
            "证据关键词": keyword_text,
            "建议功能": rule["function"],
            "建议结构": rule["structure"],
            "论文实验解释": "由用户评论关键词、情感倾向和领域规则共同推导。",
        })

        if not topic_df.empty:
            for _, topic in topic_df.iterrows():
                topic_keywords = str(topic.get("主题关键词", ""))
                if any(term in topic_keywords for term in rule["terms"]):
                    topic_req_rows.append({
                        "topic_id": topic.get("topic_id", ""),
                        "主题关键词": topic_keywords,
                        "req_id": req_id,
                        "需求名称": rule["category"],
                        "映射依据": "主题关键词命中需求规则",
                    })

    output_path = output_dir / "智能药盒需求功能映射数据库.xlsx"
    save_workbook(output_path, {
        "用户需求表": pd.DataFrame(requirement_rows).sort_values("重要度", ascending=False),
        "产品功能表": pd.DataFrame(function_rows),
        "产品结构表": pd.DataFrame(structure_rows),
        "需求功能映射": pd.DataFrame(req_func_rows),
        "功能结构映射": pd.DataFrame(func_struct_rows),
        "主题需求映射": pd.DataFrame(topic_req_rows),
        "设计机会点": pd.DataFrame(opportunity_rows),
    })

    print(f"需求数量：{len(requirement_rows)}")
    print(f"功能数量：{len(function_rows)}")
    print(f"结构数量：{len(structure_rows)}")
    print(f"已生成：{output_path}")


if __name__ == "__main__":
    main()
