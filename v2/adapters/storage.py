from __future__ import annotations

import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Protocol
from uuid import UUID


_UNSAFE_NAME = re.compile(r"[^0-9A-Za-z._\-\u4e00-\u9fff]+")


@dataclass(frozen=True)
class StoredArtifact:
    run_id: str
    name: str
    path: str
    mime_type: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class DeleteReport:
    deleted: tuple[str, ...]
    failed: tuple[str, ...]


class ArtifactStore(Protocol):
    def put(self, run_id: UUID | str, name: str, data: bytes, mime_type: str) -> StoredArtifact: ...

    def read(self, path: str) -> bytes: ...

    def delete_many(self, paths: Iterable[str]) -> DeleteReport: ...


def safe_artifact_name(name: str) -> str:
    leaf = Path(str(name).replace("\\", "/")).name.strip(" .")
    cleaned = _UNSAFE_NAME.sub("-", leaf).strip("-.")
    return cleaned[:160] or "artifact.bin"


def artifact_path(run_id: UUID | str, name: str) -> str:
    normalized_run_id = str(UUID(str(run_id)))
    return f"runs/{normalized_run_id}/{safe_artifact_name(name)}"


def _artifact_record(run_id: UUID | str, name: str, path: str, data: bytes, mime_type: str) -> StoredArtifact:
    return StoredArtifact(
        run_id=str(UUID(str(run_id))),
        name=safe_artifact_name(name),
        path=path,
        mime_type=str(mime_type or "application/octet-stream"),
        size_bytes=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
    )


class LocalArtifactStore:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def put(self, run_id: UUID | str, name: str, data: bytes, mime_type: str) -> StoredArtifact:
        relative = artifact_path(run_id, name)
        destination = self._resolve(relative)
        if destination.exists() and destination.read_bytes() != data:
            suffix = hashlib.sha256(data).hexdigest()[:8]
            path = Path(relative)
            relative = str(path.with_name(f"{path.stem}-{suffix}{path.suffix}")).replace("\\", "/")
            destination = self._resolve(relative)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        return _artifact_record(run_id, name, relative, data, mime_type)

    def read(self, path: str) -> bytes:
        return self._resolve(path).read_bytes()

    def delete_many(self, paths: Iterable[str]) -> DeleteReport:
        deleted: list[str] = []
        failed: list[str] = []
        for path in paths:
            try:
                target = self._resolve(path)
                if target.exists():
                    target.unlink()
                deleted.append(path)
            except (OSError, ValueError):
                failed.append(path)
        return DeleteReport(tuple(deleted), tuple(failed))

    def _resolve(self, relative: str) -> Path:
        candidate = (self.root / str(relative).replace("\\", "/")).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("资产路径越过私有存储根目录。")
        return candidate


class RepositoryArtifactStore:
    """Persistent private blob storage inside the configured V2 database."""

    def __init__(self, repository: object) -> None:
        self.repository = repository

    def put(self, run_id: UUID | str, name: str, data: bytes, mime_type: str) -> StoredArtifact:
        relative = artifact_path(run_id, name)
        digest = hashlib.sha256(data).hexdigest()
        with self.repository.connect() as connection:
            existing = connection.execute(
                self.repository._sql(
                    "SELECT sha256 FROM artifact_blobs WHERE owner_id = ? AND storage_path = ?"
                ),
                (self.repository.owner_id, relative),
            ).fetchone()
            if existing and str(existing["sha256"]) != digest:
                path = Path(relative)
                relative = str(
                    path.with_name(f"{path.stem}-{digest[:12]}{path.suffix}")
                ).replace("\\", "/")
                existing = connection.execute(
                    self.repository._sql(
                        "SELECT sha256 FROM artifact_blobs WHERE owner_id = ? AND storage_path = ?"
                    ),
                    (self.repository.owner_id, relative),
                ).fetchone()
            if not existing:
                connection.execute(
                    self.repository._sql(
                        "INSERT INTO artifact_blobs "
                        "(owner_id, storage_path, data, mime_type, size_bytes, sha256, created_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?)"
                    ),
                    (
                        self.repository.owner_id,
                        relative,
                        data,
                        str(mime_type or "application/octet-stream"),
                        len(data),
                        digest,
                        datetime.now(timezone.utc).isoformat(timespec="microseconds"),
                    ),
                )
        return _artifact_record(run_id, name, relative, data, mime_type)

    def read(self, path: str) -> bytes:
        self._validate_path(path)
        with self.repository.connect() as connection:
            row = connection.execute(
                self.repository._sql(
                    "SELECT data FROM artifact_blobs WHERE owner_id = ? AND storage_path = ?"
                ),
                (self.repository.owner_id, path),
            ).fetchone()
        if not row:
            raise FileNotFoundError(path)
        return bytes(row["data"])

    def delete_many(self, paths: Iterable[str]) -> DeleteReport:
        deleted: list[str] = []
        failed: list[str] = []
        with self.repository.connect() as connection:
            for path in paths:
                try:
                    self._validate_path(path)
                    connection.execute(
                        self.repository._sql(
                            "DELETE FROM artifact_blobs WHERE owner_id = ? AND storage_path = ?"
                        ),
                        (self.repository.owner_id, path),
                    )
                    deleted.append(path)
                except (TypeError, ValueError):
                    failed.append(path)
        return DeleteReport(tuple(deleted), tuple(failed))

    @staticmethod
    def _validate_path(path: str) -> None:
        normalized = str(path).replace("\\", "/")
        if not normalized.startswith("runs/") or ".." in Path(normalized).parts:
            raise ValueError("非法私有资产路径。")


class SupabaseArtifactStore:
    def __init__(self, storage_url: str, bucket: str, service_key: str, timeout_seconds: int = 45) -> None:
        self.storage_url = storage_url.rstrip("/")
        self.bucket = safe_artifact_name(bucket)
        self._service_key = service_key
        self.timeout_seconds = max(1, int(timeout_seconds))
        if not self.storage_url.startswith("https://"):
            raise ValueError("V2_STORAGE_URL 必须使用 HTTPS。")
        if not self._service_key:
            raise ValueError("V2_STORAGE_SERVICE_KEY 不能为空。")

    def put(self, run_id: UUID | str, name: str, data: bytes, mime_type: str) -> StoredArtifact:
        relative = artifact_path(run_id, name)
        request = urllib.request.Request(
            self._object_url(relative),
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._service_key}",
                "apikey": self._service_key,
                "Content-Type": str(mime_type or "application/octet-stream"),
                "x-upsert": "false",
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            response.read()
        return _artifact_record(run_id, name, relative, data, mime_type)

    def read(self, path: str) -> bytes:
        request = urllib.request.Request(
            self._object_url(path),
            headers={"Authorization": f"Bearer {self._service_key}", "apikey": self._service_key},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            return response.read()

    def delete_many(self, paths: Iterable[str]) -> DeleteReport:
        candidates = tuple(paths)
        if not candidates:
            return DeleteReport((), ())
        if any(not path.startswith("runs/") or ".." in Path(path).parts for path in candidates):
            safe = tuple(path for path in candidates if path.startswith("runs/") and ".." not in Path(path).parts)
            unsafe = tuple(path for path in candidates if path not in safe)
        else:
            safe, unsafe = candidates, ()
        if not safe:
            return DeleteReport((), unsafe)
        body = json.dumps({"prefixes": list(safe)}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.storage_url}/object/{urllib.parse.quote(self.bucket)}",
            data=body,
            method="DELETE",
            headers={
                "Authorization": f"Bearer {self._service_key}",
                "apikey": self._service_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
        except OSError:
            return DeleteReport((), candidates)
        return DeleteReport(safe, unsafe)

    def _object_url(self, path: str) -> str:
        if not path.startswith("runs/") or ".." in Path(path).parts:
            raise ValueError("非法私有资产路径。")
        encoded_path = urllib.parse.quote(path, safe="/")
        return f"{self.storage_url}/object/{urllib.parse.quote(self.bucket)}/{encoded_path}"
