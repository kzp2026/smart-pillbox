from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import pandas as pd


# =========================
# 1. 项目路径与默认文件名
# =========================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
OUTPUT_DIR = ROOT_DIR / "output"
DEFAULT_INPUT_STEM = DATA_DIR / "comments"


# =========================
# 2. 中文停用词（通用）
# =========================

STOP_WORDS = {
    "的", "了", "是", "我", "也", "很", "都", "和", "在", "就", "还", "有", "给",
    "一个", "这个", "那个", "这些", "那些", "可以", "已经", "没有", "就是", "比较",
    "非常", "感觉", "觉得", "买了", "真的", "还是", "不是", "因为", "所以", "但是",
    "京东", "自营", "商城", "快递", "小哥", "东西", "商品", "产品", "这款", "起来",
}


# =========================
# 3. 基础工具函数
# =========================

def ensure_output_dir(output_dir: str | Path | None = None) -> Path:
    target = Path(output_dir) if output_dir else OUTPUT_DIR
    if not target.is_absolute():
        target = ROOT_DIR / target
    target.mkdir(parents=True, exist_ok=True)
    return target


def as_project_path(path: str | Path) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT_DIR / p


def resolve_input_path(input_path: str | Path | None = None) -> Path:
    candidates: list[Path] = []

    if input_path:
        user_path = as_project_path(input_path)
        if user_path.suffix:
            candidates.append(user_path)
        else:
            candidates.extend(
                user_path.with_suffix(suffix)
                for suffix in [".xlsx", ".xls", ".csv"]
            )

    candidates.extend(
        DEFAULT_INPUT_STEM.with_suffix(suffix)
        for suffix in [".xlsx", ".xls", ".csv"]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    searched = "\n".join(str(p) for p in candidates)
    raise FileNotFoundError(f"未找到评论数据文件，已尝试：\n{searched}")


def read_table(path: str | Path) -> pd.DataFrame:
    p = as_project_path(path)
    suffix = p.suffix.lower()
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(p)

    if suffix == ".csv":
        for encoding in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
            try:
                return pd.read_csv(p, encoding=encoding)
            except UnicodeDecodeError:
                continue
        return pd.read_csv(p)

    raise ValueError(f"不支持的文件格式：{p}")


def safe_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", "_", name)
    return cleaned[:31] if len(cleaned) > 31 else cleaned


def save_workbook(path: str | Path, sheets: dict[str, pd.DataFrame]) -> Path:
    p = as_project_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(p, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=safe_sheet_name(name), index=False)
    return p


# =========================
# 4. 评论列识别与文本清洗
# =========================

def detect_comment_column(df: pd.DataFrame) -> str:
    target_names = {"评论内容", "评论", "content", "comment", "评价", "评价内容", "review"}
    for col in df.columns:
        if str(col).strip() in target_names:
            return col
    for col in df.columns:
        lower = str(col).lower().strip()
        for keyword in ["评论", "内容", "评价", "comment", "review", "content"]:
            if keyword in lower:
                return col
    longest_col = max(df.select_dtypes(include=["object"]).columns,
                      key=lambda c: df[c].dropna().astype(str).str.len().mean(),
                      default=df.columns[0])
    return longest_col


def clean_text(text: str) -> str:
    text = html.unescape(str(text))
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[a-zA-Z0-9]+://\S+", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# =========================
# 5. 分词与关键词提取
# =========================

def split_words(text: str) -> list[str]:
    try:
        import jieba
    except ImportError:
        return [w for w in str(text).split() if len(w) >= 2]
    words = jieba.lcut(str(text))
    return [w.strip() for w in words if len(w.strip()) >= 2 and w.strip() not in STOP_WORDS]


def compute_tfidf(tokens_list: list[list[str]], max_features: int = 80, min_df: int = 2) -> pd.DataFrame:
    from sklearn.feature_extraction.text import TfidfVectorizer
    documents = [" ".join(tokens) for tokens in tokens_list]
    if not documents or all(not doc.strip() for doc in documents):
        return pd.DataFrame()
    vectorizer = TfidfVectorizer(max_features=max_features, min_df=min_df, token_pattern=r"(?u)\b\w+\b")
    try:
        tfidf_matrix = vectorizer.fit_transform(documents)
    except ValueError:
        return pd.DataFrame()
    feature_names = vectorizer.get_feature_names_out()
    scores = tfidf_matrix.sum(axis=0).A1
    df_freq = (tfidf_matrix > 0).sum(axis=0).A1
    result = pd.DataFrame({
        "关键词": feature_names,
        "TF-IDF权重": scores,
        "文档频次": df_freq,
    }).sort_values("TF-IDF权重", ascending=False)
    return result


def load_cleaned_or_build(input_path: str | Path | None, output_dir: Path) -> pd.DataFrame:
    cleaned_path = output_dir / "cleaned_comments.xlsx"
    if cleaned_path.exists():
        return pd.read_excel(cleaned_path)
    try:
        data_path = resolve_input_path(input_path)
    except FileNotFoundError:
        raise FileNotFoundError("请先上传评论数据文件（支持 .xlsx/.xls/.csv）")
    df = read_table(data_path)
    comment_col = detect_comment_column(df)
    df["原始评论"] = df[comment_col].astype(str)
    df["清洗评论"] = df["原始评论"].apply(clean_text)
    df["分词结果"] = df["清洗评论"].apply(lambda t: " ".join(split_words(t)))
    df["评论长度"] = df["清洗评论"].str.len()
    df["词数"] = df["清洗评论"].apply(lambda t: len(split_words(t)))
    cleaned_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(cleaned_path, index=False)
    return df


# =========================
# 6. 通用需求映射（基于主题聚类自动推导）
# =========================

def auto_generate_mapping_rules(topic_df: pd.DataFrame) -> list[dict]:
    """根据主题聚类结果自动生成需求-功能-结构映射规则。
    每个主题聚类对应一条规则，功能和结构从关键词推导。"""
    rules = []
    if topic_df.empty:
        return rules

    for _, row in topic_df.head(12).iterrows():
        topic_name = str(row.get("主题名称", ""))
        topic_keywords = str(row.get("主题关键词", ""))
        if not topic_name or topic_name == "nan":
            continue

        # 提取关键词列表
        kw_list = [k.strip() for k in re.split(r"[，,、\s]+", topic_keywords) if k.strip()]

        # 生成简短的功能和结构描述
        function_desc = f"满足用户对"{topic_name}"的需求"
        structure_desc = f"支持"{topic_name}"的产品结构模块"
        if kw_list:
            top_term = kw_list[0]
            function_desc = f"增强型{top_term}功能模块"
            structure_desc = f"集成{top_term}的产品结构单元"

        rules.append({
            "category": topic_name,
            "terms": kw_list[:5],
            "function": f"{topic_name}优化功能",
            "structure": f"{topic_name}支撑结构",
            "description": f"响应"{topic_name}"相关用户需求，通过优化功能和结构提升产品体验。",
        })

    return rules


# =========================
# 7. KMeans 聚类（BERTopic 备选方案）
# =========================

def kmeans_cluster_tokens(
    tokens_list: list[list[str]],
    n_clusters: int = 8,
    random_state: int = 42,
) -> tuple[list[int], list[list[str]]]:
    from sklearn.cluster import KMeans
    from sklearn.feature_extraction.text import TfidfVectorizer

    documents = [" ".join(tokens) for tokens in tokens_list]
    if not documents or all(not doc.strip() for doc in documents):
        return [0] * len(documents), [["无数据"]]

    vectorizer = TfidfVectorizer(max_features=300, min_df=2, token_pattern=r"(?u)\b\w+\b")
    try:
        X = vectorizer.fit_transform(documents)
    except ValueError:
        return [0] * len(documents), [["无数据"]]

    n = min(n_clusters, len(documents), X.shape[1])
    if n < 2:
        return [0] * len(documents), [["单一聚类"]]

    kmeans = KMeans(n_clusters=n, random_state=random_state, n_init=10)
    labels = kmeans.fit_predict(X)

    topic_keywords = []
    feature_names = vectorizer.get_feature_names_out()
    for cluster_id in range(n):
        indices = [i for i, lbl in enumerate(labels) if lbl == cluster_id]
        if not indices:
            topic_keywords.append(["无关键词"])
            continue
        cluster_vectors = X[indices]
        centroid = cluster_vectors.mean(axis=0).A1
        top_indices = centroid.argsort()[::-1][:10]
        topic_keywords.append([feature_names[i] for i in top_indices])

    return labels, topic_keywords


def stable_id(prefix: str, text: str, length: int = 10) -> str:
    digest = hashlib.md5(str(text).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"
