from __future__ import annotations

import argparse
from collections import Counter

import pandas as pd

from common import (
    compute_tfidf,
    ensure_output_dir,
    keyword_examples,
    load_cleaned_or_build,
    save_workbook,
    split_words,
)


POSITIVE_WORDS = {
    "好用", "方便", "满意", "不错", "喜欢", "实用", "省心", "清晰", "简单", "轻松",
    "便携", "准时", "棒", "推荐", "贴心", "漂亮", "颜值", "稳定", "快捷", "可靠",
}

NEGATIVE_WORDS = {
    "不好", "难用", "麻烦", "忘记", "吃错", "异味", "不准", "失败", "坏", "差",
    "不方便", "复杂", "声音小", "连接不上", "漏", "贵", "慢", "不灵", "问题",
}


def snownlp_score(text: str) -> float | None:
    """优先使用 SnowNLP 计算中文情感分数，未安装时返回 None。"""
    try:
        from snownlp import SnowNLP
    except Exception:
        return None

    try:
        return float(SnowNLP(text).sentiments)
    except Exception:
        return None


def rule_score(text: str, words: str, rating: object = None) -> float:
    """词典规则与评分字段结合的兜底情感分数。"""
    tokens = set(split_words(words))
    pos_count = sum(1 for word in POSITIVE_WORDS if word in text or word in tokens)
    neg_count = sum(1 for word in NEGATIVE_WORDS if word in text or word in tokens)

    score = 0.5 + (pos_count - neg_count) * 0.08
    try:
        rating_value = float(rating)
        if rating_value >= 5:
            score += 0.22
        elif rating_value >= 4:
            score += 0.12
        elif rating_value <= 2:
            score -= 0.22
        elif rating_value < 4:
            score -= 0.08
    except Exception:
        pass

    return min(max(score, 0.0), 1.0)


def label_sentiment(score: float) -> str:
    """把情感分数转换为中文标签。"""
    if score >= 0.6:
        return "正向"
    if score <= 0.4:
        return "负向"
    return "中性"


def main() -> None:
    """第三阶段：中文评论情感分析。"""
    parser = argparse.ArgumentParser(description="第三阶段：中文评论情感分析")
    parser.add_argument("--input", default=None, help="输入文件，默认读取 output/cleaned_comments.xlsx")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    df = load_cleaned_or_build(args.input, output_dir).copy()

    scores = []
    methods = []
    labels = []
    for _, row in df.iterrows():
        text = str(row.get("clean_comment", ""))
        snow_score = snownlp_score(text)
        if snow_score is None:
            score = rule_score(text, str(row.get("words", "")), row.get("评分", None))
            method = "词典规则+评分字段"
        else:
            score = snow_score
            method = "SnowNLP"
        scores.append(round(score, 4))
        methods.append(method)
        labels.append(label_sentiment(score))

    detail_df = df.copy()
    detail_df["sentiment_score"] = scores
    detail_df["sentiment_label"] = labels
    detail_df["sentiment_method"] = methods

    tokens_list = [split_words(value) for value in detail_df["words"]]
    keyword_df = compute_tfidf(tokens_list, max_features=80, min_df=2)
    keyword_set = set(keyword_df["关键词"])

    keyword_rows = []
    word_sets = detail_df["words"].astype(str).apply(lambda value: set(value.split()))
    for keyword in keyword_df["关键词"]:
        # 用集合判断分词命中，避免正则特殊字符和 pandas 分组警告。
        matched_mask = word_sets.apply(lambda words: keyword in words) | detail_df["clean_comment"].astype(str).str.contains(keyword, regex=False, na=False)
        matched = detail_df[matched_mask]
        if matched.empty:
            continue
        label_counts = Counter(matched["sentiment_label"])
        keyword_rows.append({
            "关键词": keyword,
            "关键词类别": keyword_df.loc[keyword_df["关键词"] == keyword, "关键词类别"].iloc[0],
            "出现评论数": len(matched),
            "平均情感分": round(float(matched["sentiment_score"].mean()), 4),
            "负向评论数": label_counts.get("负向", 0),
            "正向评论数": label_counts.get("正向", 0),
            "主要情感倾向": matched["sentiment_label"].mode().iloc[0],
        })

    keyword_sentiment_df = pd.DataFrame(keyword_rows)
    if not keyword_sentiment_df.empty:
        keyword_sentiment_df = keyword_sentiment_df.sort_values(
            ["平均情感分", "出现评论数"], ascending=[True, False]
        ).reset_index(drop=True)

    pains_df = keyword_sentiment_df[
        (keyword_sentiment_df["平均情感分"] <= 0.55)
        | (keyword_sentiment_df["负向评论数"] > 0)
    ].head(30) if not keyword_sentiment_df.empty else pd.DataFrame()

    highlights_df = keyword_sentiment_df[
        keyword_sentiment_df["平均情感分"] >= 0.6
    ].sort_values(["平均情感分", "出现评论数"], ascending=[False, False]).head(30) if not keyword_sentiment_df.empty else pd.DataFrame()

    examples_df = keyword_examples(detail_df, keyword_set)

    output_path = output_dir / "情感分析结果.xlsx"
    save_workbook(output_path, {
        "评论情感明细": detail_df,
        "关键词情感统计": keyword_sentiment_df,
        "用户痛点": pains_df,
        "用户满意点": highlights_df,
        "情感示例评论": examples_df,
    })

    print(f"情感分析完成，评论数：{len(detail_df)}")
    print(f"已生成：{output_path}")


if __name__ == "__main__":
    main()
