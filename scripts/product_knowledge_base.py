from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator
from urllib.parse import urlparse

from scripts.industrial_design_prompt import build_industrial_design_prompt


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = ROOT_DIR / "data" / "product_knowledge_base.sqlite3"
DEFAULT_OWNER_ID = "private"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def clean_text(value: object) -> str:
    text = "" if value is None else str(value)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def text_fingerprint(value: str) -> str:
    return hashlib.sha256(clean_text(value).encode("utf-8")).hexdigest()


def to_json_safe(value: object) -> object:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_json_safe(item) for item in value]
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def tokenize(text: str) -> list[str]:
    words = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z0-9]+", clean_text(text).lower())
    chars = [char for char in clean_text(text) if "\u4e00" <= char <= "\u9fff"]
    return words + chars


VISUAL_ASSET_TEMPLATES = [
    {
        "key": "render_1",
        "label": "产品效果图 1",
        "size": "1024x1024",
        "prompt": "单张专业产品效果图，45度主视角，单一产品主体，白色或浅灰干净背景，真实PBR材质、圆角、阴影、高光和核心交互区清晰可见。",
    },
    {
        "key": "render_2",
        "label": "产品效果图 2",
        "size": "1024x1024",
        "prompt": "单张专业产品效果图，从略高的30度侧前方观察同一款产品，展示上盖、主控区和分格结构；不是拼贴图，不是多个产品角度合集。",
    },
    {
        "key": "exploded",
        "label": "产品爆炸图",
        "size": "1024x1792",
        "prompt": "单张完整爆炸图，沿中心垂直装配轴从上到下分层悬浮，展示外壳、功能模块、内部空间、连接件、可维护部件和装配关系；不是多宫格，不是拼贴图，不是另一款产品。",
    },
    {
        "key": "detail",
        "label": "产品细节图",
        "size": "1024x1024",
        "prompt": "产品细节特写图，只放大同一款产品上的关键结构、材质、开启方式、按键、屏幕、提示灯或连接细节，微距摄影质感。",
    },
    {
        "key": "three_view",
        "label": "产品三视图",
        "size": "1792x1024",
        "prompt": "工业设计三视图，同一产品以统一比例展示正视图、侧视图和俯视图，严格对齐，白色背景，无透视变形，适合工程表达。",
    },
    {
        "key": "board",
        "label": "设计展板",
        "size": "1600x2200",
        "prompt": "设计展板，整合产品效果图、爆炸图、细节图、三视图、使用效果图、需求分析和功能结构映射；信息层级清晰，少文字，多图像，适合论文和开题展示。",
    },
    {
        "key": "usage_1",
        "label": "产品使用效果图 1",
        "size": "1024x1024",
        "prompt": "单张真实使用场景图，目标用户在自然生活环境中使用同一款产品，人物动作、产品尺度、空间关系和核心功能表达真实合理。",
    },
    {
        "key": "usage_2",
        "label": "产品使用效果图 2",
        "size": "1024x1024",
        "prompt": "单张真实使用场景图，从另一自然视角展示同一款产品被目标用户操作或提醒；产品轮廓、材料、分格数量和核心交互区必须与母版完全一致。",
    },
]


def product_visual_constraints(product_name: str) -> str:
    if "药盒" in product_name:
        return (
            "固定为同一款智能分格药盒：圆角矩形盒体、半透明或透明上盖、清晰药格、前置提醒屏或指示灯、"
            "药片分区明确。不得生成耳机盒、充电盒、蓝牙耳机、化妆盒、首饰盒、普通收纳盒或多方案拼贴。"
        )
    return f"固定为同一款{product_name}，不得生成其他品类、替代产品、多方案拼贴或与{product_name}无关的对象。"


def build_visual_identity_lock(target_product: str, demand_text: str, requirements: list[dict], comments: list[dict]) -> str:
    requirement_text = "；".join(clean_text(item.get("title", "")) for item in requirements[:4] if item.get("title"))
    evidence_text = "；".join(clean_text(item.get("comment_original", "")) for item in comments[:2] if item.get("comment_original"))
    return (
        f"统一产品设计锁定：所有设计图片必须表现同一款“{target_product}”，只能改变镜头视角、拆解方式、展板排版和使用场景，"
        "不得改变产品本体；保持同一轮廓、同一主色、同一材料质感、同一关键部件数量、同一尺寸比例、同一操作区域。"
        f"目标需求：{demand_text or target_product}。"
        f"关键需求证据：{requirement_text or '安全、易用、稳定、符合目标用户痛点'}。"
        f"评论证据线索：{evidence_text[:220] or '暂无更多评论证据'}。"
        f"负向约束：{product_visual_constraints(target_product)}"
        "通用质量要求：photorealistic industrial design visualization, ultra realistic 3D product render, no logo, no watermark, no collage, no contact sheet, no unrelated object."
    )


def build_visual_assets(
    target_product: str,
    demand_text: str,
    requirements: list[dict],
    comments: list[dict],
    industrial_design_prompt: str = "",
) -> list[dict]:
    identity_lock = build_visual_identity_lock(target_product, demand_text, requirements, comments)
    assets = []
    for index, template in enumerate(VISUAL_ASSET_TEMPLATES, start=1):
        prompt = (
            f"{identity_lock}\n\n"
            f"{industrial_design_prompt}\n\n"
            f"图像任务 {index}：{template['label']}。{template['prompt']} "
            f"产品名称必须明确是{target_product}，画面只服务于当前这一款产品。"
        )
        assets.append({**template, "prompt": prompt})
    return assets


def keyword_score(query: str, *values: object) -> int:
    query_tokens = Counter(tokenize(query))
    if not query_tokens:
        return 0
    haystack = " ".join(clean_text(value) for value in values)
    haystack_tokens = Counter(tokenize(haystack))
    return sum(min(count, haystack_tokens.get(token, 0)) for token, count in query_tokens.items())


def normalize_database_url(database_url: str | None = None) -> str:
    configured = (database_url or os.getenv("PRODUCT_KB_DATABASE_URL") or os.getenv("DATABASE_URL") or "").strip()
    if configured:
        return configured
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH}"


@dataclass(frozen=True)
class ConnectionInfo:
    driver: str
    url: str


class ProductKnowledgeBase:
    """Persistent product-comment knowledge base.

    SQLite is used for local validation. PostgreSQL/Supabase is supported through
    PRODUCT_KB_DATABASE_URL or DATABASE_URL when psycopg is installed.
    """

    def __init__(self, database_url: str | None = None, owner_id: str = DEFAULT_OWNER_ID):
        self.database_url = normalize_database_url(database_url)
        self.owner_id = owner_id or DEFAULT_OWNER_ID
        self.info = self._parse_connection(self.database_url)

    @staticmethod
    def _parse_connection(database_url: str) -> ConnectionInfo:
        parsed = urlparse(database_url)
        if parsed.scheme in {"sqlite", ""}:
            return ConnectionInfo("sqlite", database_url)
        if parsed.scheme in {"postgres", "postgresql"}:
            return ConnectionInfo("postgres", database_url)
        raise ValueError(f"不支持的数据库连接：{parsed.scheme}")

    @contextmanager
    def connect(self) -> Iterator:
        if self.info.driver == "sqlite":
            db_path = self.database_url.replace("sqlite:///", "", 1)
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(db_path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()
            return

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL/Supabase 需要安装 psycopg[binary] 依赖。") from exc

        with psycopg.connect(self.database_url, row_factory=dict_row) as conn:
            yield conn

    def initialize(self) -> None:
        with self.connect() as conn:
            for statement in self._schema_statements():
                conn.execute(statement)

    def _schema_statements(self) -> list[str]:
        if self.info.driver == "postgres":
            auto_id = "BIGSERIAL PRIMARY KEY"
            text_type = "TEXT"
            timestamp_type = "TIMESTAMPTZ"
        else:
            auto_id = "INTEGER PRIMARY KEY AUTOINCREMENT"
            text_type = "TEXT"
            timestamp_type = "TEXT"
        return [
            f"""
            CREATE TABLE IF NOT EXISTS products (
                id {auto_id},
                owner_id {text_type} NOT NULL,
                name {text_type} NOT NULL,
                category {text_type} NOT NULL DEFAULT '',
                description {text_type} NOT NULL DEFAULT '',
                visibility {text_type} NOT NULL DEFAULT 'private',
                created_at {timestamp_type} NOT NULL,
                updated_at {timestamp_type} NOT NULL,
                UNIQUE(owner_id, name)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS comment_batches (
                id {auto_id},
                owner_id {text_type} NOT NULL,
                product_id INTEGER NOT NULL,
                source_filename {text_type} NOT NULL DEFAULT '',
                comment_count INTEGER NOT NULL DEFAULT 0,
                created_at {timestamp_type} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS comments (
                id {auto_id},
                owner_id {text_type} NOT NULL,
                product_id INTEGER NOT NULL,
                batch_id INTEGER NOT NULL,
                comment_original {text_type} NOT NULL,
                clean_comment {text_type} NOT NULL,
                fingerprint {text_type} NOT NULL,
                created_at {timestamp_type} NOT NULL,
                UNIQUE(owner_id, product_id, fingerprint)
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS requirements (
                id {auto_id},
                owner_id {text_type} NOT NULL,
                product_id INTEGER NOT NULL,
                batch_id INTEGER,
                title {text_type} NOT NULL,
                description {text_type} NOT NULL DEFAULT '',
                keywords {text_type} NOT NULL DEFAULT '',
                evidence_text {text_type} NOT NULL DEFAULT '',
                score REAL NOT NULL DEFAULT 0,
                created_at {timestamp_type} NOT NULL
            )
            """,
            f"""
            CREATE TABLE IF NOT EXISTS generation_runs (
                id {auto_id},
                owner_id {text_type} NOT NULL,
                target_product {text_type} NOT NULL,
                demand_text {text_type} NOT NULL,
                context_json {text_type} NOT NULL,
                result_json {text_type} NOT NULL,
                quality_score REAL NOT NULL,
                quality_status {text_type} NOT NULL,
                created_at {timestamp_type} NOT NULL
            )
            """,
        ]

    def upsert_product(self, name: str, category: str = "", description: str = "") -> int:
        name = clean_text(name)
        if not name:
            raise ValueError("产品名称不能为空。")
        now = utc_now()
        with self.connect() as conn:
            existing = self._fetchone(
                conn,
                "SELECT id FROM products WHERE owner_id = ? AND name = ?",
                (self.owner_id, name),
            )
            if existing:
                conn.execute(
                    self._sql("UPDATE products SET category = ?, description = ?, updated_at = ? WHERE id = ?"),
                    (category or "", description or "", now, existing["id"]),
                )
                return int(existing["id"])
            cursor = conn.execute(
                self._sql(
                    "INSERT INTO products (owner_id, name, category, description, visibility, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, 'private', ?, ?)"
                ),
                (self.owner_id, name, category or "", description or "", now, now),
            )
            return self._lastrowid(cursor, conn)

    def ingest_comment_batch(
        self,
        product_name: str,
        category: str,
        source_filename: str,
        comments: list[str],
    ) -> tuple[int, int]:
        report = self.ingest_comment_batch_with_report(product_name, category, source_filename, comments)
        return int(report["product_id"]), int(report["batch_id"])

    def ingest_comment_batch_with_report(
        self,
        product_name: str,
        category: str,
        source_filename: str,
        comments: list[str],
    ) -> dict:
        product_id = self.upsert_product(product_name, category=category)
        cleaned = [text for text in (clean_text(comment) for comment in comments) if text]
        fingerprints = [text_fingerprint(comment) for comment in cleaned]
        unique_fingerprints = set(fingerprints)
        now = utc_now()
        with self.connect() as conn:
            before_count = self._count_comments(conn, product_id)
            cursor = conn.execute(
                self._sql(
                    "INSERT INTO comment_batches (owner_id, product_id, source_filename, comment_count, created_at) "
                    "VALUES (?, ?, ?, ?, ?)"
                ),
                (self.owner_id, product_id, source_filename or "", len(cleaned), now),
            )
            batch_id = self._lastrowid(cursor, conn)
            self._executemany_ignore(
                conn,
                "INSERT INTO comments (owner_id, product_id, batch_id, comment_original, clean_comment, fingerprint, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        self.owner_id,
                        product_id,
                        batch_id,
                        comment,
                        comment,
                        fingerprint,
                        now,
                    )
                    for comment, fingerprint in zip(cleaned, fingerprints)
                ],
            )
            after_count = self._count_comments(conn, product_id)
        inserted_count = max(0, after_count - before_count)
        duplicate_total = max(0, len(cleaned) - inserted_count)
        duplicate_in_file_count = max(0, len(cleaned) - len(unique_fingerprints))
        duplicate_existing_count = max(0, duplicate_total - duplicate_in_file_count)
        return {
            "product_id": product_id,
            "batch_id": batch_id,
            "source_filename": source_filename or "",
            "input_count": len(comments),
            "valid_count": len(cleaned),
            "invalid_count": max(0, len(comments) - len(cleaned)),
            "inserted_count": inserted_count,
            "duplicate_in_file_count": duplicate_in_file_count,
            "duplicate_existing_count": duplicate_existing_count,
            "duplicate_total": duplicate_total,
        }

    def add_requirement(
        self,
        product_id: int,
        batch_id: int | None,
        title: str,
        description: str,
        keywords: list[str] | str,
        evidence_text: str,
        score: float = 0,
    ) -> int:
        keyword_text = "、".join(keywords) if isinstance(keywords, list) else clean_text(keywords)
        with self.connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "INSERT INTO requirements (owner_id, product_id, batch_id, title, description, keywords, evidence_text, score, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    self.owner_id,
                    product_id,
                    batch_id,
                    clean_text(title),
                    clean_text(description),
                    keyword_text,
                    clean_text(evidence_text),
                    float(score),
                    utc_now(),
                ),
            )
            return self._lastrowid(cursor, conn)

    def search_context(self, query: str, limit: int = 8) -> dict:
        with self.connect() as conn:
            products = self._fetchall(
                conn,
                "SELECT id, name, category, description FROM products WHERE owner_id = ?",
                (self.owner_id,),
            )
            requirements = self._fetchall(
                conn,
                """
                SELECT r.*, p.name AS product_name, p.category AS product_category
                FROM requirements r
                JOIN products p ON p.id = r.product_id
                WHERE r.owner_id = ?
                """,
                (self.owner_id,),
            )
            comments = self._fetchall(
                conn,
                """
                SELECT c.*, p.name AS product_name, p.category AS product_category
                FROM comments c
                JOIN products p ON p.id = c.product_id
                WHERE c.owner_id = ?
                """,
                (self.owner_id,),
            )

        scored_products = [
            {**item, "score": keyword_score(query, item["name"], item["category"], item["description"])}
            for item in products
        ]
        scored_requirements = [
            {
                **item,
                "score": max(float(item.get("score") or 0) / 10, 0)
                + keyword_score(query, item["title"], item["description"], item["keywords"], item["evidence_text"], item["product_name"]),
            }
            for item in requirements
        ]
        scored_comments = [
            {
                **item,
                "score": keyword_score(query, item["comment_original"], item["product_name"], item["product_category"]),
            }
            for item in comments
        ]

        products_out = sorted([p for p in scored_products if p["score"] > 0], key=lambda item: item["score"], reverse=True)[:limit]
        requirements_out = sorted([r for r in scored_requirements if r["score"] > 0], key=lambda item: item["score"], reverse=True)[:limit]
        comments_out = sorted([c for c in scored_comments if c["score"] > 0], key=lambda item: item["score"], reverse=True)[:limit]
        return {
            "query": query,
            "products": products_out,
            "requirements": requirements_out,
            "comments": comments_out,
            "evidence_count": len(requirements_out) + len(comments_out),
        }

    def list_products(self) -> list[dict]:
        with self.connect() as conn:
            rows = self._fetchall(
                conn,
                """
                SELECT p.id, p.name, p.category, p.description, p.created_at, p.updated_at,
                       COUNT(DISTINCT c.id) AS comment_count,
                       COUNT(DISTINCT r.id) AS requirement_count
                FROM products p
                LEFT JOIN comments c ON c.product_id = p.id
                LEFT JOIN requirements r ON r.product_id = p.id
                WHERE p.owner_id = ?
                GROUP BY p.id, p.name, p.category, p.description, p.created_at, p.updated_at
                ORDER BY p.updated_at DESC
                """,
                (self.owner_id,),
            )
        return rows

    def update_product(self, product_id: int, name: str, category: str = "", description: str = "") -> bool:
        name = clean_text(name)
        if not name:
            raise ValueError("产品名称不能为空。")
        now = utc_now()
        with self.connect() as conn:
            existing = self._fetchone(
                conn,
                "SELECT id FROM products WHERE owner_id = ? AND name = ? AND id <> ?",
                (self.owner_id, name, product_id),
            )
            if existing:
                raise ValueError("同名产品已存在，请换一个名称。")
            cursor = conn.execute(
                self._sql(
                    "UPDATE products SET name = ?, category = ?, description = ?, updated_at = ? "
                    "WHERE id = ? AND owner_id = ?"
                ),
                (name, category or "", description or "", now, product_id, self.owner_id),
            )
            return self._rowcount(cursor) > 0

    def delete_product(self, product_id: int) -> bool:
        with self.connect() as conn:
            product = self._fetchone(
                conn,
                "SELECT id FROM products WHERE id = ? AND owner_id = ?",
                (product_id, self.owner_id),
            )
            if not product:
                return False
            for table in ("comments", "requirements", "comment_batches"):
                conn.execute(
                    self._sql(f"DELETE FROM {table} WHERE product_id = ? AND owner_id = ?"),
                    (product_id, self.owner_id),
                )
            cursor = conn.execute(
                self._sql("DELETE FROM products WHERE id = ? AND owner_id = ?"),
                (product_id, self.owner_id),
            )
            return self._rowcount(cursor) > 0

    def save_generation_run(self, target_product: str, demand_text: str, context: dict, result: dict) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                self._sql(
                    "INSERT INTO generation_runs (owner_id, target_product, demand_text, context_json, result_json, quality_score, quality_status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    self.owner_id,
                    clean_text(target_product),
                    clean_text(demand_text),
                    json.dumps(to_json_safe(context), ensure_ascii=False, default=str),
                    json.dumps(to_json_safe(result), ensure_ascii=False, default=str),
                    float(result.get("quality_score", 0)),
                    str(result.get("quality_status", "")),
                    utc_now(),
                ),
            )
            return self._lastrowid(cursor, conn)

    def _sql(self, statement: str) -> str:
        if self.info.driver == "postgres":
            return statement.replace("?", "%s")
        return statement

    def _execute_ignore(self, conn, statement: str, params: tuple) -> None:
        if self.info.driver == "postgres":
            statement = statement + " ON CONFLICT DO NOTHING"
        else:
            statement = statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        conn.execute(self._sql(statement), params)

    def _executemany_ignore(self, conn, statement: str, params_list: list[tuple]) -> None:
        if not params_list:
            return
        if self.info.driver == "postgres":
            statement = statement + " ON CONFLICT DO NOTHING"
        else:
            statement = statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        if hasattr(conn, "executemany"):
            conn.executemany(self._sql(statement), params_list)
        else:
            with conn.cursor() as cursor:
                cursor.executemany(self._sql(statement), params_list)

    def _fetchone(self, conn, statement: str, params: tuple) -> dict | None:
        cursor = conn.execute(self._sql(statement), params)
        row = cursor.fetchone()
        return dict(row) if row else None

    def _fetchall(self, conn, statement: str, params: tuple) -> list[dict]:
        cursor = conn.execute(self._sql(statement), params)
        return [dict(row) for row in cursor.fetchall()]

    def _count_comments(self, conn, product_id: int) -> int:
        row = self._fetchone(
            conn,
            "SELECT COUNT(*) AS count FROM comments WHERE owner_id = ? AND product_id = ?",
            (self.owner_id, product_id),
        )
        return int((row or {}).get("count") or 0)

    def _lastrowid(self, cursor, conn) -> int:
        if self.info.driver == "postgres":
            row = conn.execute("SELECT LASTVAL() AS id").fetchone()
            return int(row["id"])
        return int(cursor.lastrowid)

    def _rowcount(self, cursor) -> int:
        return int(cursor.rowcount or 0)


def generate_design_package(
    target_product: str,
    demand_text: str,
    context: dict,
    industrial_constraints: dict[str, object] | None = None,
) -> dict:
    target_product = clean_text(target_product)
    demand_text = clean_text(demand_text)
    if industrial_constraints is None and isinstance(context.get("industrial_constraints"), dict):
        industrial_constraints = context["industrial_constraints"]
    requirements = context.get("requirements", [])[:6]
    comments = context.get("comments", [])[:6]
    products = context.get("products", [])[:4]
    evidence_count = int(context.get("evidence_count", 0))

    warnings = []
    if evidence_count < 2:
        warnings.append("当前知识库证据不足，建议先导入相近产品评论再生成正式方案。")
    if not target_product:
        warnings.append("目标产品名称为空。")
    if len(demand_text) < 6:
        warnings.append("需求描述过短，建议补充目标人群、场景和核心功能。")

    requirement_lines = []
    for item in requirements:
        requirement_lines.append(
            f"- {item.get('title', '用户需求')}：{item.get('description', '')}（证据：{item.get('evidence_text', '')}）"
        )
    if not requirement_lines:
        requirement_lines.append("- 暂无足够历史需求证据，以下方案仅按当前需求进行初步推导。")

    evidence_lines = []
    for item in comments:
        evidence_lines.append(f"- 来自{item.get('product_name', '历史产品')}：{item.get('comment_original', '')}")
    if not evidence_lines:
        evidence_lines.append("- 暂无可引用的原始评论。")

    similar_names = "、".join(dict.fromkeys(str(item.get("name", "")) for item in products if item.get("name"))) or "暂无"
    design_text = f"""# {target_product} 产品设计方案

## 一、输入需求
{demand_text or "未填写具体需求。"}

## 二、知识库参考范围
系统从历史产品评论库中检索到的相似产品包括：{similar_names}。

## 三、评论证据
{chr(10).join(evidence_lines)}

## 四、核心需求转译
{chr(10).join(requirement_lines)}

## 五、产品定位
建议将{target_product}定位为“以真实评论证据驱动的用户体验优化型产品”。设计重点不是堆叠功能，而是优先解决评论中反复出现的痛点，并把功能、结构和交互反馈保持一致。

## 六、功能方案
1. 核心功能围绕当前需求“{demand_text or target_product}”展开，优先提供明确、可感知、低学习成本的主功能。
2. 辅助功能从历史评论高频痛点中提取，避免与目标场景无关的功能膨胀。
3. 对适老、家庭、健康、安全等场景，优先考虑大字体、强提醒、防误操作和易清洁结构。

## 七、结构与材料建议
结构上采用模块化主体、清晰交互区和可维护部件。材料建议优先选择耐用、易清洁、触感温和的方案，并根据目标产品的真实使用环境控制体积、重量和成本。

## 八、验证结论
本方案已保留历史评论证据链。后续生成效果图时，应保持同一产品主体、同一结构语言和同一用户场景，避免生成与目标产品无关的外观。
"""

    industrial_design_prompt, normalized_constraints = build_industrial_design_prompt(
        industrial_constraints,
        product_name=target_product,
        demand_text=demand_text,
        context=context,
    )
    visual_assets = build_visual_assets(
        target_product,
        demand_text,
        requirements,
        comments,
        industrial_design_prompt=industrial_design_prompt,
    )
    image_prompts = [asset["prompt"] for asset in visual_assets]
    image_prompt_text = image_prompts[0]

    score = 45
    score += min(evidence_count * 12, 30)
    score += 15 if target_product else 0
    score += 10 if len(demand_text) >= 12 else 0
    score = min(score, 100)
    status = "达标" if score >= 80 and not warnings else "需补充证据"
    return {
        "target_product": target_product,
        "demand_text": demand_text,
        "design_text": design_text,
        "image_prompt_text": image_prompt_text,
        "image_prompts": image_prompts,
        "visual_assets": visual_assets,
        "industrial_design_prompt": industrial_design_prompt,
        "industrial_design_constraints": normalized_constraints,
        "quality_score": score,
        "quality_status": status,
        "quality_report": {
            "evidence_count": evidence_count,
            "similar_product_count": len(products),
            "requirement_count": len(requirements),
            "warnings": warnings,
            "checks": [
                "保留评论证据链",
                "区分历史参考产品与目标产品",
                "输出文本方案和写实渲染提示词",
                "证据不足时阻止误判为高质量结果",
            ],
        },
    }
