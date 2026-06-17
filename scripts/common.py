from __future__ import annotations

import hashlib
import html
import math
import re
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime
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
    try:
        writer = pd.ExcelWriter(p, engine="openpyxl")
    except PermissionError:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        p = p.with_name(f"{p.stem}_{timestamp}{p.suffix}")
        writer = pd.ExcelWriter(p, engine="openpyxl")
    with writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=safe_sheet_name(name), index=False)
    return p


def resolve_latest_output_path(path: str | Path) -> Path:
    """返回标准输出文件或同名时间戳备用文件中的最新一个。"""
    p = as_project_path(path)
    candidates = []
    if p.exists():
        candidates.append(p)
    candidates.extend(p.parent.glob(f"{p.stem}_*{p.suffix}"))
    if candidates:
        return max(candidates, key=lambda item: item.stat().st_mtime)
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


def build_cleaned_dataframe(input_path: str | Path | None = None) -> tuple[pd.DataFrame, Path, str]:
    """读取原始评论数据，自动识别评论列并生成标准清洗字段。"""
    source_path = resolve_input_path(input_path)
    raw_df = read_table(source_path)
    comment_col = detect_comment_column(raw_df)

    cleaned_df = raw_df.copy()
    cleaned_df["comment_original"] = cleaned_df[comment_col].astype(str)
    cleaned_df["clean_comment"] = cleaned_df["comment_original"].apply(clean_text)
    cleaned_df = cleaned_df[cleaned_df["clean_comment"].astype(str).str.len() > 0].copy()
    cleaned_df = cleaned_df.drop_duplicates(subset=["clean_comment"]).reset_index(drop=True)
    cleaned_df["words"] = cleaned_df["clean_comment"].apply(lambda text: " ".join(split_words(text)))
    cleaned_df["comment_length"] = cleaned_df["clean_comment"].str.len()
    cleaned_df["word_count"] = cleaned_df["words"].astype(str).apply(lambda text: len([w for w in text.split() if w]))

    # 兼容早期中文字段名，方便论文结果表直接阅读。
    cleaned_df["原始评论"] = cleaned_df["comment_original"]
    cleaned_df["清洗评论"] = cleaned_df["clean_comment"]
    cleaned_df["分词结果"] = cleaned_df["words"]
    cleaned_df["评论长度"] = cleaned_df["comment_length"]
    cleaned_df["词数"] = cleaned_df["word_count"]
    return cleaned_df, source_path, str(comment_col)


def normalize_cleaned_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """把旧版或不同字段名的清洗结果统一为后续阶段需要的字段。"""
    result = df.copy()
    if "clean_comment" not in result.columns:
        if "清洗评论" in result.columns:
            result["clean_comment"] = result["清洗评论"].astype(str)
        else:
            comment_col = detect_comment_column(result)
            result["clean_comment"] = result[comment_col].astype(str).apply(clean_text)
    if "comment_original" not in result.columns:
        if "原始评论" in result.columns:
            result["comment_original"] = result["原始评论"].astype(str)
        else:
            result["comment_original"] = result["clean_comment"].astype(str)
    if "words" not in result.columns:
        if "分词结果" in result.columns:
            result["words"] = result["分词结果"].astype(str)
        else:
            result["words"] = result["clean_comment"].apply(lambda text: " ".join(split_words(text)))
    if "comment_length" not in result.columns:
        result["comment_length"] = result["clean_comment"].astype(str).str.len()
    if "word_count" not in result.columns:
        result["word_count"] = result["words"].astype(str).apply(lambda text: len([w for w in text.split() if w]))
    return result


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
        "关键词类别": [classify_keyword(word) for word in feature_names],
        "TF-IDF权重": scores,
        "文档频次": df_freq,
    }).sort_values("TF-IDF权重", ascending=False)
    return result


def classify_keyword(keyword: str) -> str:
    """根据智能/适老产品评论的常见语义粗分关键词类别。"""
    word = str(keyword)
    category_rules = {
        "安装服务": ["安装", "师傅", "客服", "服务", "沟通", "下单", "物流", "快递"],
        "安全稳定": ["安全", "稳定", "防滑", "结实", "牢固", "可靠", "保护", "扶手"],
        "适老场景": ["老人", "老年", "妈妈", "父母", "家里", "厕所", "浴室", "洗澡", "起身"],
        "材料质量": ["质量", "用料", "材质", "塑料", "不锈钢", "把手", "做工"],
        "外观体验": ["外观", "颜色", "时尚", "好看", "漂亮", "颜值"],
        "价格价值": ["价格", "便宜", "划算", "值得", "性价比"],
    }
    for category, terms in category_rules.items():
        if any(term in word for term in terms):
            return category
    return "综合体验"


def doc_keyword_detail(df: pd.DataFrame, keyword_df: pd.DataFrame, top_k: int = 8) -> pd.DataFrame:
    """生成每条评论命中的关键词明细。"""
    keywords = keyword_df["关键词"].astype(str).tolist() if "关键词" in keyword_df.columns else []
    rows = []
    for idx, row in df.iterrows():
        text = str(row.get("clean_comment", ""))
        words = set(str(row.get("words", "")).split())
        matched = [kw for kw in keywords if kw in words or kw in text][:top_k]
        rows.append({
            "评论序号": idx + 1,
            "评论内容": text,
            "命中关键词": "、".join(matched),
            "关键词数量": len(matched),
        })
    return pd.DataFrame(rows)


def build_cooccurrence_matrix(tokens_list: list[list[str]], keywords: Iterable[str]) -> pd.DataFrame:
    """根据评论分词结果生成关键词共现矩阵。"""
    keyword_list = [str(k) for k in keywords if str(k).strip()]
    counts = pd.DataFrame(0, index=keyword_list, columns=keyword_list, dtype=int)
    keyword_set = set(keyword_list)
    for tokens in tokens_list:
        present = sorted(set(tokens) & keyword_set)
        for left in present:
            for right in present:
                counts.loc[left, right] += 1
    counts.insert(0, "关键词", counts.index)
    return counts.reset_index(drop=True)


def keyword_examples(df: pd.DataFrame, keywords: Iterable[str], max_examples: int = 3) -> pd.DataFrame:
    """为关键词匹配代表性评论，方便论文中引用用户原话。"""
    rows = []
    for keyword in [str(k) for k in keywords if str(k).strip()]:
        mask = (
            df["words"].astype(str).apply(lambda value: keyword in set(value.split()))
            | df["clean_comment"].astype(str).str.contains(keyword, regex=False, na=False)
        )
        matched = df.loc[mask, "clean_comment"].astype(str).head(max_examples).tolist()
        rows.append({
            "关键词": keyword,
            "示例评论": " | ".join(matched),
            "示例数量": len(matched),
        })
    return pd.DataFrame(rows)


def load_cleaned_or_build(input_path: str | Path | None, output_dir: Path) -> pd.DataFrame:
    cleaned_path = output_dir / "cleaned_comments.xlsx"
    if cleaned_path.exists():
        return normalize_cleaned_dataframe(pd.read_excel(cleaned_path))
    try:
        df, _, _ = build_cleaned_dataframe(input_path)
    except FileNotFoundError:
        raise FileNotFoundError("请先上传评论数据文件（支持 .xlsx/.xls/.csv）")
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
        function_desc = f"满足用户对“{topic_name}”的需求"
        structure_desc = f"支持“{topic_name}”的产品结构模块"
        if kw_list:
            top_term = kw_list[0]
            function_desc = f"增强型{top_term}功能模块"
            structure_desc = f"集成{top_term}的产品结构单元"

        rules.append({
            "category": topic_name,
            "terms": kw_list[:5],
            "function": f"{topic_name}优化功能",
            "structure": f"{topic_name}支撑结构",
            "description": f"响应“{topic_name}”相关用户需求，通过优化功能和结构提升产品体验。",
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


def pure_python_kmeans(tokens_list: list[list[str]], n_clusters: int = 8) -> tuple[list[int], list[list[str]]]:
    """兼容旧脚本命名；优先复用 sklearn KMeans，失败时给出稳定兜底结果。"""
    try:
        return kmeans_cluster_tokens(tokens_list, n_clusters=n_clusters)
    except Exception:
        if not tokens_list:
            return [], []
        labels = [idx % max(n_clusters, 1) for idx in range(len(tokens_list))]
        topic_keywords = []
        for cluster_id in range(max(labels) + 1):
            counter = Counter()
            for label, tokens in zip(labels, tokens_list):
                if label == cluster_id:
                    counter.update(tokens)
            words = [word for word, _ in counter.most_common(10)] or ["无关键词"]
            topic_keywords.append(words)
        return labels, topic_keywords


def stable_id(prefix: str, text: str, length: int = 10) -> str:
    digest = hashlib.md5(str(text).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"
