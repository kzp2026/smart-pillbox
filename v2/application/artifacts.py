from __future__ import annotations

import io
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath


_ALLOWED_EXTENSIONS = {
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


class UnsafeArchive(ValueError):
    """Raised when an uploaded result archive violates safety limits."""


@dataclass(frozen=True)
class ArchiveLimits:
    max_archive_bytes: int
    max_entries: int
    max_total_uncompressed: int
    max_single_file: int
    max_compression_ratio: float

    @classmethod
    def default(cls) -> "ArchiveLimits":
        return cls(
            max_archive_bytes=50 * 1024 * 1024,
            max_entries=500,
            max_total_uncompressed=250 * 1024 * 1024,
            max_single_file=50 * 1024 * 1024,
            max_compression_ratio=100,
        )


@dataclass(frozen=True)
class ArchiveEntry:
    path: str
    size_bytes: int
    compressed_bytes: int


@dataclass(frozen=True)
class ArchiveManifest:
    entries: tuple[ArchiveEntry, ...]
    total_uncompressed: int


def inspect_archive(data: bytes, limits: ArchiveLimits) -> ArchiveManifest:
    if len(data) > limits.max_archive_bytes:
        raise UnsafeArchive("归档文件超过允许的上传大小。")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise UnsafeArchive("上传文件不是有效 ZIP 归档。") from exc

    entries: list[ArchiveEntry] = []
    total = 0
    with archive:
        infos = [info for info in archive.infolist() if not info.is_dir()]
        if len(infos) > limits.max_entries:
            raise UnsafeArchive("归档文件条目过多。")
        for info in infos:
            normalized = info.filename.replace("\\", "/")
            pure = PurePosixPath(normalized)
            windows = PureWindowsPath(info.filename)
            if pure.is_absolute() or windows.is_absolute() or windows.drive or ".." in pure.parts:
                raise UnsafeArchive("归档包含越权路径。")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise UnsafeArchive("归档不能包含符号链接。")
            if pure.suffix.lower() not in _ALLOWED_EXTENSIONS:
                raise UnsafeArchive(f"归档包含不支持的文件类型：{pure.suffix or '无扩展名'}")
            if info.file_size > limits.max_single_file:
                raise UnsafeArchive("归档内单个文件过大。")
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > limits.max_compression_ratio:
                raise UnsafeArchive("归档压缩比异常，可能是 ZIP 炸弹。")
            total += info.file_size
            if total > limits.max_total_uncompressed:
                raise UnsafeArchive("归档展开后的总大小超限。")
            entries.append(ArchiveEntry(normalized, info.file_size, info.compress_size))
    return ArchiveManifest(tuple(entries), total)


def extract_archive(data: bytes, destination: Path, limits: ArchiveLimits) -> ArchiveManifest:
    manifest = inspect_archive(data, limits)
    root = destination.resolve()
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in manifest.entries:
            target = (root / entry.path).resolve()
            if root not in target.parents:
                raise UnsafeArchive("归档目标路径越界。")
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(entry.path) as source:
                target.write_bytes(source.read())
    return manifest
