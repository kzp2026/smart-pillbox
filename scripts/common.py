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
DEFAULT_INPUT_STEM = DATA_DIR / "京东智能药盒评论"


# =========================
# 2. 中文停用词与智能药盒领域词
# =========================

STOP_WORDS = {
    "的", "了", "是", "我", "也", "很", "都", "和", "在", "就", "还", "有", "给",
    "一个", "这个", "那个", "这些", "那些", "可以", "已经", "没有", "就是", "比较",
    "非常", "感觉", "觉得", "买了", "真的", "还是", "不是", "因为", "所以", "但是",
    "京东", "自营", "商城", "快递", "小哥", "东西", "商品", "产品", "这款", "起来",
}

DOMAIN_TERMS = [
    "智能药盒", "药盒", "分药", "药仓", "药格", "七天", "四格", "容量", "密封", "防潮",
    "提醒", "闹钟", "语音", "灯光", "蜂鸣", "微信", "手机", "蓝牙", "联网", "HiLink",
    "HUAWEI", "华为", "记录", "服药记录", "远程", "监护", "同步", "老人", "爸妈",
    "父母", "老年人", "操作", "简单", "方便", "便携", "小巧", "出门", "外观", "颜值",
    "无异味", "异味", "材质", "质量", "做工", "电池", "纽扣电池", "续航", "充电",
    "忘记", "吃错药", "准时", "准时吃药", "拆卸", "清洗", "安装", "扫码", "添药",
    "提醒功能", "微信同步", "远程监护", "用药管理", "日常用药", "提醒方式",
]


# =========================
# 3. 基础工具函数
# =========================

def ensure_output_dir(output_dir: str | Path | None = None) -> Path:
    """确保输出目录存在。"""
    target = Path(output_dir) if output_dir else OUTPUT_DIR
    if not target.is_absolute():
        target = ROOT_DIR / target
    target.mkdir(parents=True, exist_ok=True)
    return target


def as_project_path(path: str | Path) -> Path:
    """把相对路径转换为项目根目录下的绝对路径。"""
    p = Path(path)
    return p if p.is_absolute() else ROOT_DIR / p


def resolve_input_path(input_path: str | Path | None = None) -> Path:
    """解析输入文件，支持不带扩展名的基础路径。"""
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
    """读取 Excel 或 CSV 文件。"""
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
    """Excel sheet 名最长 31 个字符，且不能包含部分特殊字符。"""
    cleaned = re.sub(r"[\[\]\:\*\?\/\\]", "_", name)
    return cleaned[:31] if len(cleaned) > 31 else cleaned


def save_workbook(path: str | Path, sheets: dict[str, pd.DataFrame]) -> Path:
    """保存多 Sheet Excel 文件。"""
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
    """自动识别最可能的评论文本列。"""
    exact_candidates = [
        "评论内容", "评论", "评价内容", "评价", "用户评论", "内容", "正文",
        "comment", "comments", "content", "review", "text",
    ]
    columns = [str(col) for col in df.columns]
    lower_map = {str(col).lower(): str(col) for col in df.columns}

    for candidate in exact_candidates:
        if candidate in columns:
            return candidate
        if candidate.lower() in lower_map:
            return lower_map[candidate.lower()]

    best_col = None
    best_score = -1.0

    for col in df.columns:
        series = df[col].dropna().astype(str)
        if series.empty:
            continue

        sample = series.head(200)
        avg_len = sample.map(len).mean()
        max_len = sample.map(len).max()
        chinese_ratio = (
            sample.str.count(r"[\u4e00-\u9fa5]").sum()
            / max(sample.map(len).sum(), 1)
        )
        name = str(col).lower()
        name_score = 0
        if any(key in name for key in ["评论", "评价", "内容", "comment", "review", "text"]):
            name_score += 50

        score = name_score + avg_len * 0.8 + max_len * 0.05 + chinese_ratio * 20
        if avg_len < 4:
            score -= 20

        if score > best_score:
            best_score = score
            best_col = str(col)

    if best_col is None:
        raise ValueError("无法自动识别评论文本列，请检查输入数据。")
    return best_col


def clean_comment(text: object) -> str:
    """清洗单条评论文本，尽量保留中文语义信息。"""
    if pd.isna(text):
        return ""

    value = html.unescape(str(text))
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"http\S+|www\.\S+", " ", value)
    value = re.sub(r"@\w+|#\w+", " ", value)
    value = re.sub(r"[\r\n\t]+", " ", value)
    value = re.sub(r"[^\u4e00-\u9fa5A-Za-z0-9 ]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


_JIEBA_READY = False


def _try_jieba_cut(text: str) -> list[str] | None:
    """优先使用 jieba 分词，未安装时返回 None。"""
    global _JIEBA_READY
    try:
        import jieba
    except Exception:
        return None

    if not _JIEBA_READY:
        for term in DOMAIN_TERMS:
            jieba.add_word(term)
        _JIEBA_READY = True
    return list(jieba.cut(text))


def tokenize_text(text: object) -> list[str]:
    """中文分词；没有 jieba 时使用领域词典和简单 n-gram 兜底。"""
    cleaned = clean_comment(text)
    if not cleaned:
        return []

    jieba_tokens = _try_jieba_cut(cleaned)
    if jieba_tokens is not None:
        raw_tokens = jieba_tokens
    else:
        raw_tokens = []
        # 先抓取智能药盒领域词，保证需求词不会被过度切碎。
        for term in sorted(DOMAIN_TERMS, key=len, reverse=True):
            if term.lower() in cleaned.lower():
                raw_tokens.append(term)

        # 再对剩余中文长句做二元/三元片段兜底。
        for part in re.findall(r"[\u4e00-\u9fa5]{2,}|[A-Za-z0-9]+", cleaned):
            if len(part) <= 6:
                raw_tokens.append(part)
            else:
                raw_tokens.extend(part[i:i + 2] for i in range(0, len(part) - 1, 2))
                raw_tokens.extend(part[i:i + 3] for i in range(0, len(part) - 2, 3))

    tokens = []
    for token in raw_tokens:
        word = str(token).strip()
        if len(word) < 2:
            continue
        if word in STOP_WORDS:
            continue
        if word.isdigit():
            continue
        tokens.append(word)
    return tokens


def build_cleaned_dataframe(input_path: str | Path | None = None) -> tuple[pd.DataFrame, Path, str]:
    """读取原始数据并生成清洗后的 DataFrame。"""
    source_path = resolve_input_path(input_path)
    df = read_table(source_path)
    comment_col = detect_comment_column(df)

    result = df.copy()
    result["comment_original"] = result[comment_col].astype(str)
    result["clean_comment"] = result["comment_original"].apply(clean_comment)
    result = result[result["clean_comment"] != ""].copy()
    result = result.drop_duplicates(subset=["clean_comment"]).reset_index(drop=True)

    result["words"] = result["clean_comment"].apply(lambda x: " ".join(tokenize_text(x)))
    result = result[result["words"].astype(str).str.strip() != ""].reset_index(drop=True)
    result["comment_length"] = result["clean_comment"].str.len()
    result["word_count"] = result["words"].apply(lambda x: len(str(x).split()))

    if "日期" in result.columns:
        result["日期"] = pd.to_datetime(result["日期"], errors="coerce")
    if "评分" in result.columns:
        result["评分"] = pd.to_numeric(result["评分"], errors="coerce")

    return result, source_path, comment_col


def load_cleaned_or_build(
    input_path: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> pd.DataFrame:
    """读取清洗结果；不存在时自动从原始数据生成。"""
    out_dir = ensure_output_dir(output_dir)
    default_cleaned = out_dir / "cleaned_comments.xlsx"

    if input_path:
        candidate = as_project_path(input_path)
        if candidate.exists():
            df = read_table(candidate)
            if {"clean_comment", "words"}.issubset(df.columns):
                return df
            cleaned, _, _ = build_cleaned_dataframe(candidate)
            return cleaned

    if default_cleaned.exists():
        return pd.read_excel(default_cleaned)

    cleaned, _, _ = build_cleaned_dataframe(None)
    save_workbook(default_cleaned, {"清洗后评论": cleaned})
    return cleaned


# =========================
# 5. TF-IDF、共现与主题聚类兜底
# =========================

def split_words(value: object) -> list[str]:
    """把 words 字段拆成词列表。"""
    if pd.isna(value):
        return []
    return [word for word in str(value).split() if word and word not in STOP_WORDS]


def compute_tfidf(tokens_list: list[list[str]], max_features: int = 80, min_df: int = 2) -> pd.DataFrame:
    """不依赖 sklearn 的语料级 TF-IDF 计算。"""
    doc_count = len(tokens_list)
    term_frequency = Counter()
    document_frequency = Counter()
    score_sum = defaultdict(float)

    for tokens in tokens_list:
        counts = Counter(tokens)
        term_frequency.update(counts)
        document_frequency.update(counts.keys())

    idf = {
        term: math.log((1 + doc_count) / (1 + df_count)) + 1
        for term, df_count in document_frequency.items()
        if df_count >= min_df
    }

    for tokens in tokens_list:
        counts = Counter(tokens)
        total = sum(counts.values()) or 1
        for term, count in counts.items():
            if term in idf:
                score_sum[term] += (count / total) * idf[term]

    rows = []
    for term, score in score_sum.items():
        rows.append({
            "关键词": term,
            "TF-IDF权重": round(score / max(doc_count, 1), 6),
            "文档频次": int(document_frequency[term]),
            "词频": int(term_frequency[term]),
            "关键词类别": classify_keyword_category(term),
        })

    rows.sort(key=lambda item: (item["TF-IDF权重"], item["文档频次"]), reverse=True)
    return pd.DataFrame(rows[:max_features])


def build_cooccurrence_matrix(tokens_list: list[list[str]], keywords: Iterable[str]) -> pd.DataFrame:
    """构建关键词共现矩阵。"""
    keyword_list = list(dict.fromkeys(keywords))
    keyword_set = set(keyword_list)
    matrix = pd.DataFrame(0, index=keyword_list, columns=keyword_list)

    for tokens in tokens_list:
        present = sorted(set(tokens) & keyword_set)
        for i, left in enumerate(present):
            for right in present[i + 1:]:
                matrix.loc[left, right] += 1
                matrix.loc[right, left] += 1

    matrix.insert(0, "关键词", matrix.index)
    return matrix.reset_index(drop=True)


def doc_keyword_detail(df: pd.DataFrame, keyword_df: pd.DataFrame, top_n: int = 8) -> pd.DataFrame:
    """为每条评论提取命中的高权重关键词。"""
    keyword_weight = dict(zip(keyword_df["关键词"], keyword_df["TF-IDF权重"]))
    keyword_set = set(keyword_weight)
    rows = []

    for idx, row in df.reset_index(drop=True).iterrows():
        tokens = split_words(row.get("words", ""))
        hits = sorted(
            set(tokens) & keyword_set,
            key=lambda word: keyword_weight.get(word, 0),
            reverse=True,
        )[:top_n]
        rows.append({
            "评论编号": idx + 1,
            "评论内容": row.get("clean_comment", ""),
            "分词结果": row.get("words", ""),
            "命中关键词": "、".join(hits),
            "关键词数量": len(hits),
        })

    return pd.DataFrame(rows)


def keyword_examples(df: pd.DataFrame, keywords: Iterable[str], max_examples: int = 3) -> pd.DataFrame:
    """为关键词提取代表性评论。"""
    rows = []
    for keyword in keywords:
        examples = []
        for _, row in df.iterrows():
            words = set(split_words(row.get("words", "")))
            text = str(row.get("clean_comment", ""))
            if keyword in words or keyword in text:
                examples.append(text[:120])
            if len(examples) >= max_examples:
                break
        item = {"关键词": keyword}
        for i in range(max_examples):
            item[f"示例评论{i + 1}"] = examples[i] if i < len(examples) else ""
        rows.append(item)
    return pd.DataFrame(rows)


def normalize_vector(vector: dict[str, float]) -> dict[str, float]:
    """把稀疏向量做 L2 归一化。"""
    norm = math.sqrt(sum(value * value for value in vector.values()))
    if norm == 0:
        return vector
    return {key: value / norm for key, value in vector.items()}


def cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    """计算两个稀疏向量的余弦相似度。"""
    if len(left) > len(right):
        left, right = right, left
    return sum(value * right.get(key, 0.0) for key, value in left.items())


def pure_python_kmeans(tokens_list: list[list[str]], n_clusters: int = 6, max_iter: int = 25) -> tuple[list[int], list[list[str]]]:
    """没有 sklearn 时使用的简单 KMeans 兜底实现。"""
    if not tokens_list:
        return [], []

    doc_count = len(tokens_list)
    n_clusters = max(1, min(n_clusters, doc_count))
    tfidf_df = compute_tfidf(tokens_list, max_features=300, min_df=1)
    vocab = tfidf_df["关键词"].tolist()
    idf = {
        row["关键词"]: math.log((1 + doc_count) / (1 + row["文档频次"])) + 1
        for _, row in tfidf_df.iterrows()
    }

    vectors = []
    for tokens in tokens_list:
        counts = Counter(token for token in tokens if token in vocab)
        total = sum(counts.values()) or 1
        vector = {
            term: (count / total) * idf.get(term, 1.0)
            for term, count in counts.items()
        }
        vectors.append(normalize_vector(vector))

    centroids = [vectors[int(i * doc_count / n_clusters)] for i in range(n_clusters)]
    labels = [0] * doc_count

    for _ in range(max_iter):
        changed = False
        for i, vector in enumerate(vectors):
            similarities = [cosine_similarity(vector, center) for center in centroids]
            label = max(range(n_clusters), key=lambda c: similarities[c])
            if labels[i] != label:
                labels[i] = label
                changed = True

        grouped = [[] for _ in range(n_clusters)]
        for label, vector in zip(labels, vectors):
            grouped[label].append(vector)

        new_centroids = []
        for group in grouped:
            if not group:
                new_centroids.append({})
                continue
            merged = defaultdict(float)
            for vector in group:
                for term, value in vector.items():
                    merged[term] += value
            new_centroids.append(normalize_vector({term: value / len(group) for term, value in merged.items()}))
        centroids = new_centroids

        if not changed:
            break

    topic_keywords = []
    for cluster_id in range(n_clusters):
        merged = Counter()
        for label, tokens in zip(labels, tokens_list):
            if label == cluster_id:
                merged.update(tokens)
        topic_keywords.append([word for word, _ in merged.most_common(10)])

    return labels, topic_keywords


# =========================
# 6. 需求映射规则
# =========================

MAPPING_RULES = [
    {
        "category": "服药提醒需求",
        "terms": ["提醒", "闹钟", "语音", "灯光", "蜂鸣", "准时", "忘记", "提醒功能"],
        "function": "多模态服药提醒功能",
        "structure": "蜂鸣器、LED 指示灯、语音提示模块、提醒控制芯片",
        "description": "通过声音、灯光、语音等方式提醒用户按时服药。",
    },
    {
        "category": "药品分装与防错需求",
        "terms": ["分药", "药仓", "药格", "七天", "四格", "容量", "吃错药", "添药"],
        "function": "分仓分时段药品管理功能",
        "structure": "多格药仓、日期标识盖板、防错位分隔结构",
        "description": "通过分仓结构降低漏服、错服和重复服药风险。",
    },
    {
        "category": "远程监护需求",
        "terms": ["微信", "手机", "远程", "监护", "同步", "服药记录", "记录", "爸妈", "父母"],
        "function": "远程服药记录与家属监护功能",
        "structure": "无线通信模块、云端同步接口、服药检测传感器",
        "description": "让家属能够远程查看老人服药状态并及时干预。",
    },
    {
        "category": "老人易用性需求",
        "terms": ["老人", "老年人", "操作", "简单", "上手", "方便", "扫码"],
        "function": "适老化交互与低学习成本操作功能",
        "structure": "大字体标识、大按键、扫码配置区、简化交互面板",
        "description": "降低老年用户配置和日常使用门槛。",
    },
    {
        "category": "便携与场景适应需求",
        "terms": ["便携", "小巧", "出门", "大小", "携带", "拆卸"],
        "function": "便携式药盒携带与模块拆分功能",
        "structure": "轻量化外壳、可拆卸药仓、圆角便携外形",
        "description": "满足家庭、外出、旅行等多场景用药管理。",
    },
    {
        "category": "安全卫生与防潮需求",
        "terms": ["密封", "防潮", "无异味", "异味", "材质", "清洗", "卫生"],
        "function": "药品防潮密封与易清洁功能",
        "structure": "密封圈、食品级材料、可拆洗内胆、防潮盖体",
        "description": "保障药品存放卫生与稳定性。",
    },
    {
        "category": "续航与可靠性需求",
        "terms": ["电池", "纽扣电池", "续航", "充电", "很久", "质量", "做工"],
        "function": "低功耗供电与可靠运行功能",
        "structure": "低功耗主控、电池仓、充电接口、电量提示模块",
        "description": "提升提醒系统长期运行稳定性。",
    },
    {
        "category": "外观与情感体验需求",
        "terms": ["外观", "颜值", "颜色", "小巧", "好看"],
        "function": "友好外观与家庭场景融合功能",
        "structure": "圆角外壳、柔和配色、清晰状态灯、亲和化表面处理",
        "description": "提高产品接受度和日常使用愉悦感。",
    },
]


def classify_keyword_category(keyword: str) -> str:
    """根据领域规则给关键词归类。"""
    for rule in MAPPING_RULES:
        if any(term.lower() in keyword.lower() or keyword.lower() in term.lower() for term in rule["terms"]):
            return rule["category"]
    return "综合体验需求"


def stable_id(prefix: str, text: str, length: int = 10) -> str:
    """根据文本生成稳定 ID。"""
    digest = hashlib.md5(str(text).encode("utf-8")).hexdigest()[:length]
    return f"{prefix}_{digest}"
