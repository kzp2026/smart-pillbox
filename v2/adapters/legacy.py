from __future__ import annotations

import hashlib
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Sequence


_LEGACY_TABLES = ("products", "comment_batches", "comments", "requirements", "generation_runs")
_MIGRATABLE_EXTENSIONS = {
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".txt",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".cypher",
    ".md",
}


@dataclass(frozen=True)
class LegacyFile:
    path: Path
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class LegacySnapshot:
    products: tuple[dict, ...]
    comment_batches: tuple[dict, ...]
    comments: tuple[dict, ...]
    requirements: tuple[dict, ...]
    generation_runs: tuple[dict, ...]
    files: tuple[LegacyFile, ...]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "products": len(self.products),
            "comment_batches": len(self.comment_batches),
            "comments": len(self.comments),
            "requirements": len(self.requirements),
            "generation_runs": len(self.generation_runs),
            "files": len(self.files),
        }


class LegacyReader:
    def __init__(
        self,
        database_url: str,
        owner_id: str = "private",
        output_roots: Sequence[Path] = (),
    ) -> None:
        self.database_url = database_url.strip()
        self.owner_id = owner_id
        self.output_roots = tuple(Path(root) for root in output_roots)
        self.is_sqlite = self.database_url.startswith("sqlite:///")

    def scan(self) -> LegacySnapshot:
        tables: dict[str, tuple[dict, ...]] = {table: () for table in _LEGACY_TABLES}
        if self.database_url:
            with self.connect() as connection:
                existing = self._existing_tables(connection)
                for table in _LEGACY_TABLES:
                    if table not in existing:
                        continue
                    placeholder = "?" if self.is_sqlite else "%s"
                    rows = connection.execute(
                        f"SELECT * FROM {table} WHERE owner_id = {placeholder}",
                        (self.owner_id,),
                    ).fetchall()
                    tables[table] = tuple(dict(row) for row in rows)
        return LegacySnapshot(
            products=tables["products"],
            comment_batches=tables["comment_batches"],
            comments=tables["comments"],
            requirements=tables["requirements"],
            generation_runs=tables["generation_runs"],
            files=self._scan_files(),
        )

    @contextmanager
    def connect(self) -> Iterator[object]:
        if self.is_sqlite:
            path = Path(self.database_url.removeprefix("sqlite:///"))
            connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            connection.row_factory = sqlite3.Row
            try:
                yield connection
            finally:
                connection.close()
            return
        if not self.database_url.startswith(("postgres://", "postgresql://")):
            raise ValueError("原数据库连接格式不受支持。")
        import psycopg
        from psycopg.rows import dict_row

        with psycopg.connect(self.database_url, row_factory=dict_row) as connection:
            connection.execute("SET TRANSACTION READ ONLY")
            connection.execute("SET search_path TO public")
            yield connection

    def _existing_tables(self, connection: object) -> set[str]:
        if self.is_sqlite:
            rows = connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
            return {str(row["name"]) for row in rows}
        rows = connection.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
        return {str(row["table_name"]) for row in rows}

    def _scan_files(self) -> tuple[LegacyFile, ...]:
        files: list[LegacyFile] = []
        seen: set[tuple[str, str]] = set()
        for root in self.output_roots:
            if not root.exists():
                continue
            for path in sorted(item for item in root.rglob("*") if item.is_file()):
                if path.suffix.lower() not in _MIGRATABLE_EXTENSIONS:
                    continue
                data = path.read_bytes()
                digest = hashlib.sha256(data).hexdigest()
                relative = path.relative_to(root).as_posix()
                identity = (relative, digest)
                if identity in seen:
                    continue
                seen.add(identity)
                files.append(LegacyFile(path, relative, len(data), digest))
        return tuple(files)
