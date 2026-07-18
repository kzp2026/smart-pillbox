from __future__ import annotations

import hashlib
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Sequence

from v2.adapters.storage import StoredArtifact
from v2.domain.models import (
    ArtifactKind,
    CreateRunCommand,
    ImportReport,
    PipelineRun,
    ProductSummary,
    RunStatus,
    WorkspaceSnapshot,
)


_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_TABLES = {
    "products",
    "comment_batches",
    "comments",
    "requirements",
    "generation_runs",
    "pipeline_runs",
    "stage_runs",
    "artifacts",
    "artifact_blobs",
    "migration_ledger",
    "login_audit",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", "" if value is None else str(value)).strip()


def fingerprint(*values: object) -> str:
    normalized = "\x1f".join(clean_text(value) for value in values)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class KnowledgeRepository:
    def __init__(self, database_url: str, owner_id: str, schema: str = "agent_v2") -> None:
        if not _SAFE_IDENTIFIER.fullmatch(schema):
            raise ValueError("schema 必须是安全的 PostgreSQL 标识符。")
        self.database_url = database_url.strip()
        self.owner_id = clean_text(owner_id)
        self.schema = schema
        self.is_sqlite = self.database_url.startswith("sqlite:///")
        if not self.owner_id:
            raise ValueError("owner_id 不能为空。")
        if not self.is_sqlite and not self.database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("V2 仅支持 SQLite 或 PostgreSQL 数据库连接。")

    @contextmanager
    def connect(self) -> Iterator[object]:
        if self.is_sqlite:
            database_path = Path(self.database_url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                connection.close()
            return

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError("PostgreSQL 连接需要 psycopg[binary]。") from exc

        with psycopg.connect(
            self.database_url,
            row_factory=dict_row,
            prepare_threshold=None,
        ) as connection:
            connection.execute(f'SET search_path TO "{self.schema}", public')
            yield connection

    def initialize(self) -> None:
        with self.connect() as connection:
            if self.is_sqlite:
                for statement in self._sqlite_schema():
                    connection.execute(statement)
                return
            sql_path = Path(__file__).resolve().parents[1] / "migrations" / "001_agent_v2_schema.sql"
            connection.execute(sql_path.read_text(encoding="utf-8"))

    def ingest_comments(
        self,
        product_name: str,
        category: str,
        source_filename: str,
        comments: Sequence[str],
    ) -> ImportReport:
        normalized = [clean_text(comment) for comment in comments]
        valid = [comment for comment in normalized if comment]
        now = utc_now()
        with self.connect() as connection:
            product_id = self._upsert_product(connection, clean_text(product_name), clean_text(category), now)
            cursor = connection.execute(
                self._sql(
                    "INSERT INTO comment_batches "
                    "(owner_id, product_id, source_filename, comment_count, created_at) VALUES (?, ?, ?, ?, ?)"
                ),
                (self.owner_id, product_id, clean_text(source_filename), len(valid), now),
            )
            batch_id = self._last_id(connection, cursor)
            inserted_count = 0
            for comment in valid:
                comment_fingerprint = fingerprint(comment)
                statement = (
                    "INSERT INTO comments "
                    "(owner_id, product_id, batch_id, comment_original, clean_comment, fingerprint, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)"
                )
                if self.is_sqlite:
                    statement = statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
                else:
                    statement += " ON CONFLICT DO NOTHING"
                inserted = connection.execute(
                    self._sql(statement),
                    (self.owner_id, product_id, batch_id, comment, comment, comment_fingerprint, now),
                )
                inserted_count += max(0, int(inserted.rowcount or 0))
            connection.execute(
                self._sql("UPDATE products SET updated_at = ? WHERE id = ? AND owner_id = ?"),
                (now, product_id, self.owner_id),
            )

        return ImportReport(
            product_id=product_id,
            batch_id=batch_id,
            input_count=len(comments),
            valid_count=len(valid),
            invalid_count=len(comments) - len(valid),
            inserted_count=inserted_count,
            duplicate_count=len(valid) - inserted_count,
        )

    def upsert_product(self, name: str, category: str = "", description: str = "") -> int:
        now = utc_now()
        with self.connect() as connection:
            product_id = self._upsert_product(connection, clean_text(name), clean_text(category), now)
            connection.execute(
                self._sql("UPDATE products SET description = ?, updated_at = ? WHERE id = ? AND owner_id = ?"),
                (clean_text(description), now, product_id, self.owner_id),
            )
        return product_id

    def add_requirement_once(
        self,
        product_id: int,
        batch_id: int | None,
        title: str,
        description: str,
        keywords: Sequence[str] | str,
        evidence_text: str,
        score: float = 0,
        dedupe_identity: str | None = None,
    ) -> int:
        keyword_text = "、".join(clean_text(item) for item in keywords) if not isinstance(keywords, str) else clean_text(keywords)
        requirement_fingerprint = fingerprint(
            product_id,
            title,
            keyword_text,
            evidence_text,
            clean_text(dedupe_identity or ""),
        )
        now = utc_now()
        with self.connect() as connection:
            statement = (
                "INSERT INTO requirements "
                "(owner_id, product_id, batch_id, title, description, keywords, evidence_text, score, fingerprint, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            )
            if self.is_sqlite:
                statement = statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
            else:
                statement += " ON CONFLICT DO NOTHING"
            connection.execute(
                self._sql(statement),
                (
                    self.owner_id,
                    product_id,
                    batch_id,
                    clean_text(title),
                    clean_text(description),
                    keyword_text,
                    clean_text(evidence_text),
                    float(score),
                    requirement_fingerprint,
                    now,
                ),
            )
            row = connection.execute(
                self._sql("SELECT id FROM requirements WHERE owner_id = ? AND fingerprint = ?"),
                (self.owner_id, requirement_fingerprint),
            ).fetchone()
        if not row:
            raise RuntimeError("需求证据写入失败。")
        return int(row["id"])

    def create_pipeline_run(self, command: CreateRunCommand, idempotency_key: str) -> PipelineRun:
        key = clean_text(idempotency_key)
        if not key:
            raise ValueError("idempotency_key 不能为空。")
        with self.connect() as connection:
            existing = connection.execute(
                self._sql("SELECT * FROM pipeline_runs WHERE owner_id = ? AND idempotency_key = ?"),
                (self.owner_id, key),
            ).fetchone()
            if existing:
                return self._pipeline_from_row(existing)
            now = utc_now()
            run_id = str(uuid.uuid4())
            connection.execute(
                self._sql(
                    "INSERT INTO pipeline_runs "
                    "(id, owner_id, target_product, demand_text, provider, model, image_count, status, current_stage, "
                    "idempotency_key, error_summary, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?)"
                ),
                (
                    run_id,
                    self.owner_id,
                    clean_text(command.target_product),
                    clean_text(command.demand_text),
                    clean_text(command.provider),
                    clean_text(command.model),
                    max(0, int(command.image_count)),
                    RunStatus.PENDING.value,
                    "",
                    key,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                self._sql("SELECT * FROM pipeline_runs WHERE id = ? AND owner_id = ?"),
                (run_id, self.owner_id),
            ).fetchone()
        return self._pipeline_from_row(row)

    def get_pipeline_run(self, run_id: str) -> PipelineRun:
        with self.connect() as connection:
            row = connection.execute(
                self._sql("SELECT * FROM pipeline_runs WHERE id = ? AND owner_id = ?"),
                (run_id, self.owner_id),
            ).fetchone()
        if not row:
            raise KeyError("未找到该 V2 运行记录。")
        return self._pipeline_from_row(row)

    def list_pipeline_runs(
        self,
        limit: int = 50,
        target_product: str | None = None,
    ) -> list[PipelineRun]:
        safe_limit = max(1, min(int(limit), 200))
        product = clean_text(target_product or "")
        with self.connect() as connection:
            if product:
                rows = connection.execute(
                    self._sql(
                        "SELECT * FROM pipeline_runs WHERE owner_id = ? AND target_product = ? "
                        "ORDER BY updated_at DESC LIMIT ?"
                    ),
                    (self.owner_id, product, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    self._sql(
                        "SELECT * FROM pipeline_runs WHERE owner_id = ? "
                        "ORDER BY updated_at DESC LIMIT ?"
                    ),
                    (self.owner_id, safe_limit),
                ).fetchall()
        return [self._pipeline_from_row(row) for row in rows]

    def update_pipeline_run(
        self,
        run_id: str,
        status: RunStatus,
        current_stage: str = "",
        error_summary: str = "",
    ) -> PipelineRun:
        with self.connect() as connection:
            cursor = connection.execute(
                self._sql(
                    "UPDATE pipeline_runs SET status = ?, current_stage = ?, error_summary = ?, updated_at = ? "
                    "WHERE id = ? AND owner_id = ?"
                ),
                (
                    status.value,
                    clean_text(current_stage),
                    clean_text(error_summary)[:1200],
                    utc_now(),
                    run_id,
                    self.owner_id,
                ),
            )
        if int(cursor.rowcount or 0) == 0:
            raise KeyError("未找到该 V2 运行记录。")
        return self.get_pipeline_run(run_id)

    def record_stage_run(
        self,
        pipeline_run_id: str,
        stage_id: str,
        status: RunStatus,
        input_hash: str = "",
        error_summary: str = "",
    ) -> str:
        stage_uuid = str(uuid.uuid5(uuid.UUID(pipeline_run_id), clean_text(stage_id)))
        now = utc_now()
        statement = (
            "INSERT INTO stage_runs "
            "(id, owner_id, pipeline_run_id, stage_id, status, input_hash, error_summary, started_at, finished_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(owner_id, pipeline_run_id, stage_id) DO UPDATE SET "
            "status = excluded.status, input_hash = excluded.input_hash, error_summary = excluded.error_summary, "
            "finished_at = excluded.finished_at"
        )
        with self.connect() as connection:
            connection.execute(
                self._sql(statement),
                (
                    stage_uuid,
                    self.owner_id,
                    pipeline_run_id,
                    clean_text(stage_id),
                    status.value,
                    clean_text(input_hash),
                    clean_text(error_summary)[:1200],
                    now,
                    now,
                ),
            )
        return stage_uuid

    def save_generation_run(
        self,
        pipeline_run_id: str,
        context_json: str,
        result_json: str,
        quality_score: float,
        quality_status: str,
    ) -> str:
        with self.connect() as connection:
            existing = connection.execute(
                self._sql("SELECT id FROM generation_runs WHERE owner_id = ? AND pipeline_run_id = ?"),
                (self.owner_id, pipeline_run_id),
            ).fetchone()
            if existing:
                return str(existing["id"])
            generation_id = str(uuid.uuid4())
            connection.execute(
                self._sql(
                    "INSERT INTO generation_runs "
                    "(id, owner_id, pipeline_run_id, context_json, result_json, quality_score, quality_status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    generation_id,
                    self.owner_id,
                    pipeline_run_id,
                    context_json,
                    result_json,
                    float(quality_score),
                    clean_text(quality_status),
                    utc_now(),
                ),
            )
        return generation_id

    def get_generation_run(self, pipeline_run_id: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                self._sql(
                    "SELECT * FROM generation_runs WHERE owner_id = ? AND pipeline_run_id = ?"
                ),
                (self.owner_id, pipeline_run_id),
            ).fetchone()
        return dict(row) if row else None

    def record_artifact(
        self,
        pipeline_run_id: str,
        kind: ArtifactKind | str,
        artifact: StoredArtifact,
    ) -> str:
        kind_value = kind.value if isinstance(kind, ArtifactKind) else clean_text(kind)
        with self.connect() as connection:
            existing = connection.execute(
                self._sql("SELECT id FROM artifacts WHERE owner_id = ? AND storage_path = ?"),
                (self.owner_id, artifact.path),
            ).fetchone()
            if existing:
                return str(existing["id"])
            artifact_id = str(uuid.uuid4())
            connection.execute(
                self._sql(
                    "INSERT INTO artifacts "
                    "(id, owner_id, pipeline_run_id, kind, name, storage_path, mime_type, size_bytes, sha256, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                ),
                (
                    artifact_id,
                    self.owner_id,
                    pipeline_run_id,
                    kind_value,
                    artifact.name,
                    artifact.path,
                    artifact.mime_type,
                    artifact.size_bytes,
                    artifact.sha256,
                    utc_now(),
                ),
            )
        return artifact_id

    def find_artifact_by_name(self, name: str) -> dict | None:
        with self.connect() as connection:
            row = connection.execute(
                self._sql(
                    "SELECT * FROM artifacts WHERE owner_id = ? AND name = ? ORDER BY created_at DESC LIMIT 1"
                ),
                (self.owner_id, clean_text(name)),
            ).fetchone()
        return dict(row) if row else None

    def list_artifacts(self) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                self._sql("SELECT * FROM artifacts WHERE owner_id = ? ORDER BY created_at"),
                (self.owner_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def list_artifacts_for_run(self, pipeline_run_id: str) -> list[dict]:
        with self.connect() as connection:
            rows = connection.execute(
                self._sql(
                    "SELECT * FROM artifacts WHERE owner_id = ? AND pipeline_run_id = ? ORDER BY created_at"
                ),
                (self.owner_id, pipeline_run_id),
            ).fetchall()
        return [dict(row) for row in rows]

    def find_comment_id(self, product_id: int, comment: str) -> int | None:
        with self.connect() as connection:
            row = connection.execute(
                self._sql(
                    "SELECT id FROM comments WHERE owner_id = ? AND product_id = ? AND fingerprint = ?"
                ),
                (self.owner_id, product_id, fingerprint(comment)),
            ).fetchone()
        return int(row["id"]) if row else None

    def get_migration_target(self, source_type: str, source_id: str, sha256: str = "") -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                self._sql(
                    "SELECT target_id FROM migration_ledger "
                    "WHERE owner_id = ? AND source_type = ? AND source_id = ? AND sha256 = ?"
                ),
                (self.owner_id, clean_text(source_type), clean_text(source_id), clean_text(sha256)),
            ).fetchone()
        return str(row["target_id"]) if row else None

    def record_migration(
        self,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
        sha256: str = "",
    ) -> None:
        statement = (
            "INSERT INTO migration_ledger "
            "(owner_id, source_type, source_id, target_type, target_id, sha256, migrated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)"
        )
        if self.is_sqlite:
            statement = statement.replace("INSERT INTO", "INSERT OR IGNORE INTO", 1)
        else:
            statement += " ON CONFLICT DO NOTHING"
        with self.connect() as connection:
            connection.execute(
                self._sql(statement),
                (
                    self.owner_id,
                    clean_text(source_type),
                    clean_text(source_id),
                    clean_text(target_type),
                    clean_text(target_id),
                    clean_text(sha256),
                    utc_now(),
                ),
            )

    def total_business_rows(self) -> int:
        return sum(
            self.count_rows(table)
            for table in (
                "products",
                "comment_batches",
                "comments",
                "requirements",
                "generation_runs",
                "pipeline_runs",
                "stage_runs",
                "artifacts",
            )
        )

    def list_products(self) -> list[ProductSummary]:
        with self.connect() as connection:
            rows = connection.execute(
                self._sql(
                    "SELECT p.id, p.name, p.category, p.description, p.created_at, p.updated_at, "
                    "COUNT(DISTINCT c.id) AS comment_count, COUNT(DISTINCT r.id) AS requirement_count "
                    "FROM products p "
                    "LEFT JOIN comments c ON c.product_id = p.id AND c.owner_id = p.owner_id "
                    "LEFT JOIN requirements r ON r.product_id = p.id AND r.owner_id = p.owner_id "
                    "WHERE p.owner_id = ? "
                    "GROUP BY p.id, p.name, p.category, p.description, p.created_at, p.updated_at "
                    "ORDER BY p.updated_at DESC"
                ),
                (self.owner_id,),
            ).fetchall()
        return [
            ProductSummary(
                id=int(row["id"]),
                name=str(row["name"]),
                category=str(row["category"]),
                description=str(row["description"]),
                comment_count=int(row["comment_count"] or 0),
                requirement_count=int(row["requirement_count"] or 0),
                created_at=str(row["created_at"]),
                updated_at=str(row["updated_at"]),
            )
            for row in rows
        ]

    def search_context(self, query: str, limit: int = 8) -> dict:
        from scripts.product_knowledge_base import keyword_score

        safe_limit = max(1, min(int(limit), 30))
        with self.connect() as connection:
            products = [
                dict(row)
                for row in connection.execute(
                    self._sql(
                        "SELECT id, name, category, description FROM products WHERE owner_id = ?"
                    ),
                    (self.owner_id,),
                ).fetchall()
            ]
            requirements = [
                dict(row)
                for row in connection.execute(
                    self._sql(
                        "SELECT r.*, p.name AS product_name, p.category AS product_category "
                        "FROM requirements r JOIN products p ON p.id = r.product_id "
                        "WHERE r.owner_id = ? AND p.owner_id = ?"
                    ),
                    (self.owner_id, self.owner_id),
                ).fetchall()
            ]
            comments = [
                dict(row)
                for row in connection.execute(
                    self._sql(
                        "SELECT c.*, p.name AS product_name, p.category AS product_category "
                        "FROM comments c JOIN products p ON p.id = c.product_id "
                        "WHERE c.owner_id = ? AND p.owner_id = ?"
                    ),
                    (self.owner_id, self.owner_id),
                ).fetchall()
            ]

        product_scores = [
            {
                **item,
                "score": keyword_score(
                    query, item.get("name"), item.get("category"), item.get("description")
                ),
            }
            for item in products
        ]
        requirement_scores = [
            {
                **item,
                "score": max(float(item.get("score") or 0) / 10, 0)
                + keyword_score(
                    query,
                    item.get("title"),
                    item.get("description"),
                    item.get("keywords"),
                    item.get("evidence_text"),
                    item.get("product_name"),
                ),
            }
            for item in requirements
        ]
        comment_scores = [
            {
                **item,
                "score": keyword_score(
                    query,
                    item.get("comment_original"),
                    item.get("product_name"),
                    item.get("product_category"),
                ),
            }
            for item in comments
        ]

        selected_products = sorted(
            (item for item in product_scores if item["score"] > 0),
            key=lambda item: item["score"],
            reverse=True,
        )[:safe_limit]
        selected_requirements = sorted(
            (item for item in requirement_scores if item["score"] > 0),
            key=lambda item: item["score"],
            reverse=True,
        )[:safe_limit]
        selected_comments = sorted(
            (item for item in comment_scores if item["score"] > 0),
            key=lambda item: item["score"],
            reverse=True,
        )[:safe_limit]
        return {
            "query": clean_text(query),
            "products": selected_products,
            "requirements": selected_requirements,
            "comments": selected_comments,
            "evidence_count": len(selected_requirements) + len(selected_comments),
        }

    def delete_product(self, product_id: int) -> bool:
        with self.connect() as connection:
            cursor = connection.execute(
                self._sql("DELETE FROM products WHERE id = ? AND owner_id = ?"),
                (int(product_id), self.owner_id),
            )
        return int(cursor.rowcount or 0) > 0

    def update_product(
        self,
        product_id: int,
        name: str,
        category: str = "",
        description: str = "",
    ) -> bool:
        clean_name = clean_text(name)
        if not clean_name:
            raise ValueError("产品名称不能为空。")
        with self.connect() as connection:
            cursor = connection.execute(
                self._sql(
                    "UPDATE products SET name = ?, category = ?, description = ?, updated_at = ? "
                    "WHERE id = ? AND owner_id = ?"
                ),
                (
                    clean_name,
                    clean_text(category),
                    clean_text(description),
                    utc_now(),
                    int(product_id),
                    self.owner_id,
                ),
            )
        return int(cursor.rowcount or 0) > 0

    def count_rows(self, table: str) -> int:
        if table not in _TABLES:
            raise ValueError("不允许查询未知表。")
        with self.connect() as connection:
            row = connection.execute(
                self._sql(f"SELECT COUNT(*) AS count FROM {table} WHERE owner_id = ?"),
                (self.owner_id,),
            ).fetchone()
        return int(row["count"] or 0)

    def workspace_snapshot(self) -> WorkspaceSnapshot:
        """Return all navigation counters in one database round-trip."""
        with self.connect() as connection:
            row = connection.execute(
                self._sql(
                    "SELECT "
                    "(SELECT COUNT(*) FROM products WHERE owner_id = ?) AS product_count, "
                    "(SELECT COUNT(*) FROM comments WHERE owner_id = ?) AS comment_count, "
                    "(SELECT COUNT(*) FROM requirements WHERE owner_id = ?) AS requirement_count, "
                    "(SELECT COUNT(*) FROM generation_runs WHERE owner_id = ?) AS generation_run_count, "
                    "(SELECT COUNT(*) FROM artifacts WHERE owner_id = ?) AS artifact_count, "
                    "(SELECT COUNT(*) FROM artifacts WHERE owner_id = ? AND kind = ?) AS image_count"
                ),
                (
                    self.owner_id,
                    self.owner_id,
                    self.owner_id,
                    self.owner_id,
                    self.owner_id,
                    self.owner_id,
                    ArtifactKind.IMAGE.value,
                ),
            ).fetchone()
        return WorkspaceSnapshot(
            product_count=int(row["product_count"] or 0),
            comment_count=int(row["comment_count"] or 0),
            requirement_count=int(row["requirement_count"] or 0),
            generation_run_count=int(row["generation_run_count"] or 0),
            artifact_count=int(row["artifact_count"] or 0),
            image_count=int(row["image_count"] or 0),
        )

    def _upsert_product(self, connection: object, name: str, category: str, now: str) -> int:
        if not name:
            raise ValueError("产品名称不能为空。")
        existing = connection.execute(
            self._sql("SELECT id FROM products WHERE owner_id = ? AND name = ?"),
            (self.owner_id, name),
        ).fetchone()
        if existing:
            connection.execute(
                self._sql("UPDATE products SET category = ?, updated_at = ? WHERE id = ? AND owner_id = ?"),
                (category, now, int(existing["id"]), self.owner_id),
            )
            return int(existing["id"])
        cursor = connection.execute(
            self._sql(
                "INSERT INTO products "
                "(owner_id, name, category, description, visibility, created_at, updated_at) "
                "VALUES (?, ?, ?, '', 'private', ?, ?)"
            ),
            (self.owner_id, name, category, now, now),
        )
        return self._last_id(connection, cursor)

    def _pipeline_from_row(self, row: object) -> PipelineRun:
        return PipelineRun(
            id=str(row["id"]),
            target_product=str(row["target_product"]),
            demand_text=str(row["demand_text"]),
            provider=str(row["provider"]),
            model=str(row["model"]),
            image_count=int(row["image_count"]),
            status=RunStatus(str(row["status"])),
            current_stage=str(row["current_stage"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    def _last_id(self, connection: object, cursor: object) -> int:
        if self.is_sqlite:
            return int(cursor.lastrowid)
        return int(connection.execute("SELECT LASTVAL() AS id").fetchone()["id"])

    def _sql(self, statement: str) -> str:
        return statement if self.is_sqlite else statement.replace("?", "%s")

    @staticmethod
    def _sqlite_schema() -> list[str]:
        return [
            """CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, name TEXT NOT NULL,
                category TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                visibility TEXT NOT NULL DEFAULT 'private', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(owner_id, name))""",
            """CREATE TABLE IF NOT EXISTS comment_batches (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, product_id INTEGER NOT NULL,
                source_filename TEXT NOT NULL DEFAULT '', comment_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, product_id INTEGER NOT NULL,
                batch_id INTEGER NOT NULL, comment_original TEXT NOT NULL, clean_comment TEXT NOT NULL,
                fingerprint TEXT NOT NULL, created_at TEXT NOT NULL,
                FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY(batch_id) REFERENCES comment_batches(id) ON DELETE CASCADE,
                UNIQUE(owner_id, product_id, fingerprint))""",
            """CREATE TABLE IF NOT EXISTS requirements (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, product_id INTEGER NOT NULL,
                batch_id INTEGER, title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', keywords TEXT NOT NULL DEFAULT '',
                evidence_text TEXT NOT NULL DEFAULT '', score REAL NOT NULL DEFAULT 0, fingerprint TEXT NOT NULL,
                created_at TEXT NOT NULL, FOREIGN KEY(product_id) REFERENCES products(id) ON DELETE CASCADE,
                FOREIGN KEY(batch_id) REFERENCES comment_batches(id) ON DELETE SET NULL,
                UNIQUE(owner_id, fingerprint))""",
            """CREATE TABLE IF NOT EXISTS pipeline_runs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, target_product TEXT NOT NULL, demand_text TEXT NOT NULL,
                provider TEXT NOT NULL, model TEXT NOT NULL, image_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL, current_stage TEXT NOT NULL DEFAULT '', idempotency_key TEXT NOT NULL,
                error_summary TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                UNIQUE(owner_id, idempotency_key))""",
            """CREATE TABLE IF NOT EXISTS generation_runs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pipeline_run_id TEXT, context_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}', quality_score REAL NOT NULL DEFAULT 0,
                quality_status TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL,
                FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE,
                UNIQUE(owner_id, pipeline_run_id))""",
            """CREATE TABLE IF NOT EXISTS stage_runs (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pipeline_run_id TEXT NOT NULL, stage_id TEXT NOT NULL,
                status TEXT NOT NULL, input_hash TEXT NOT NULL DEFAULT '', error_summary TEXT NOT NULL DEFAULT '',
                started_at TEXT, finished_at TEXT, UNIQUE(owner_id, pipeline_run_id, stage_id),
                FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, owner_id TEXT NOT NULL, pipeline_run_id TEXT, kind TEXT NOT NULL,
                name TEXT NOT NULL, storage_path TEXT NOT NULL, mime_type TEXT NOT NULL DEFAULT '', size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(owner_id, storage_path),
                FOREIGN KEY(pipeline_run_id) REFERENCES pipeline_runs(id) ON DELETE CASCADE)""",
            """CREATE TABLE IF NOT EXISTS artifact_blobs (
                owner_id TEXT NOT NULL, storage_path TEXT NOT NULL, data BLOB NOT NULL,
                mime_type TEXT NOT NULL DEFAULT '', size_bytes INTEGER NOT NULL,
                sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                PRIMARY KEY(owner_id, storage_path))""",
            """CREATE TABLE IF NOT EXISTS migration_ledger (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, source_type TEXT NOT NULL,
                source_id TEXT NOT NULL, target_type TEXT NOT NULL, target_id TEXT NOT NULL, sha256 TEXT NOT NULL DEFAULT '',
                migrated_at TEXT NOT NULL, UNIQUE(owner_id, source_type, source_id, sha256))""",
            """CREATE TABLE IF NOT EXISTS login_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT, owner_id TEXT NOT NULL, session_fingerprint TEXT NOT NULL,
                outcome TEXT NOT NULL, created_at TEXT NOT NULL)""",
        ]
