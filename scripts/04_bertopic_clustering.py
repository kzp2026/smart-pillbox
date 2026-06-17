from __future__ import annotations

import argparse
import math
from collections import Counter

import pandas as pd

from common import ensure_output_dir, load_cleaned_or_build, pure_python_kmeans, save_workbook, split_words


def try_bertopic(docs: list[str], n_topics: int) -> tuple[list[int], list[list[str]], str] | None:
    """优先尝试 BERTopic；失败时返回 None。"""
    try:
        from bertopic import BERTopic
        from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
    except Exception:
        return None

    try:
        vectorizer_model = CountVectorizer(token_pattern=r"(?u)\b\w+\b")
        embedding_vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b")
        embeddings = embedding_vectorizer.fit_transform(docs)
        model = BERTopic(
            embedding_model=None,
            vectorizer_model=vectorizer_model,
            min_topic_size=max(3, min(10, len(docs) // max(n_topics, 1))),
            calculate_probabilities=False,
            verbose=False,
        )
        labels, _ = model.fit_transform(docs, embeddings)
        topic_ids = sorted(set(labels))
        topic_keywords = []
        for topic_id in topic_ids:
            if topic_id == -1:
                topic_keywords.append(["离群评论"])
            else:
                words = model.get_topic(topic_id) or []
                topic_keywords.append([word for word, _ in words[:10]])
        id_map = {topic_id: idx for idx, topic_id in enumerate(topic_ids)}
        normalized_labels = [id_map[label] for label in labels]
        return normalized_labels, topic_keywords, "BERTopic"
    except Exception:
        return None


def try_sklearn_kmeans(docs: list[str], tokens_list: list[list[str]], n_topics: int) -> tuple[list[int], list[list[str]], str] | None:
    """尝试使用 sklearn 的 KMeans；失败时返回 None。"""
    try:
        from sklearn.cluster import KMeans
        from sklearn.feature_extraction.text import TfidfVectorizer
    except Exception:
        return None

    try:
        vectorizer = TfidfVectorizer(token_pattern=r"(?u)\b\w+\b", max_features=500)
        matrix = vectorizer.fit_transform(docs)
        model = KMeans(n_clusters=n_topics, random_state=42, n_init=10)
        labels = model.fit_predict(matrix).tolist()
        feature_names = vectorizer.get_feature_names_out()
        topic_keywords = []
        for cluster_id in range(n_topics):
            center = model.cluster_centers_[cluster_id]
            top_indexes = center.argsort()[::-1][:10]
            topic_keywords.append([feature_names[i] for i in top_indexes])
        return labels, topic_keywords, "KMeans+TF-IDF"
    except Exception:
        labels, topic_keywords = pure_python_kmeans(tokens_list, n_clusters=n_topics)
        return labels, topic_keywords, "PurePythonKMeans+TF-IDF"


def representative_comments(df: pd.DataFrame, labels: list[int], topic_id: int, limit: int = 3) -> str:
    """提取主题代表性评论。"""
    comments = []
    for label, text in zip(labels, df["clean_comment"].astype(str).tolist()):
        if label == topic_id:
            comments.append(text[:120])
        if len(comments) >= limit:
            break
    return " | ".join(comments)


def main() -> None:
    """第四阶段：BERTopic 或 KMeans 主题聚类。"""
    parser = argparse.ArgumentParser(description="第四阶段：主题聚类")
    parser.add_argument("--input", default=None, help="输入文件，默认读取 output/cleaned_comments.xlsx")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--n-topics", type=int, default=6, help="KMeans 兜底聚类主题数")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    df = load_cleaned_or_build(args.input, output_dir).copy()
    tokens_list = [split_words(value) for value in df["words"]]
    docs = [" ".join(tokens) for tokens in tokens_list]
    docs = [doc if doc.strip() else "空评论" for doc in docs]

    n_topics = max(2, min(args.n_topics, max(2, int(math.sqrt(len(df))) if len(df) > 4 else len(df))))
    result = try_bertopic(docs, n_topics)
    if result is None:
        result = try_sklearn_kmeans(docs, tokens_list, n_topics)
    if result is None:
        labels, topic_keywords = pure_python_kmeans(tokens_list, n_clusters=n_topics)
        algorithm = "PurePythonKMeans+TF-IDF"
    else:
        labels, topic_keywords, algorithm = result

    detail_df = df.copy()
    detail_df["topic_id"] = labels
    detail_df["topic_name"] = detail_df["topic_id"].apply(lambda value: f"主题{value}")
    detail_df["topic_keywords"] = detail_df["topic_id"].apply(
        lambda value: "、".join(topic_keywords[value]) if value < len(topic_keywords) else ""
    )
    detail_df["algorithm"] = algorithm

    summary_rows = []
    for topic_id in sorted(set(labels)):
        count = labels.count(topic_id)
        keywords = topic_keywords[topic_id] if topic_id < len(topic_keywords) else []
        summary_rows.append({
            "topic_id": topic_id,
            "主题名称": f"主题{topic_id}",
            "评论数": count,
            "占比": round(count / max(len(labels), 1), 4),
            "主题关键词": "、".join(keywords),
            "代表性评论": representative_comments(detail_df, labels, topic_id),
            "algorithm": algorithm,
        })
    summary_df = pd.DataFrame(summary_rows)

    note_df = pd.DataFrame([{
        "实际使用算法": algorithm,
        "说明": "优先尝试 BERTopic；若 BERTopic 未安装或运行失败，则自动使用 KMeans + TF-IDF 兜底。",
    }])

    output_path = output_dir / "BERTopic主题聚类结果.xlsx"
    save_workbook(output_path, {
        "评论主题聚类结果": detail_df,
        "主题汇总": summary_df,
        "算法说明": note_df,
    })

    print(f"实际使用算法：{algorithm}")
    print(f"主题数量：{len(summary_df)}")
    print(f"已生成：{output_path}")


if __name__ == "__main__":
    main()
