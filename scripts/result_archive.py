from __future__ import annotations

import hashlib
import io
import re
import zipfile
from pathlib import Path


def safe_path_part(value: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value)).strip(" ._")
    return cleaned[:40] or "未命名产品"


def build_result_archive(output_dir: Path, product_name: str) -> bytes:
    output_dir = Path(output_dir)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(output_dir.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(output_dir).as_posix())
        archive.writestr(
            "archive_manifest.txt",
            f"产品名称：{product_name}\n归档说明：本文件可在系统侧边栏“恢复历史结果归档”中重新导入。\n",
        )
    return buffer.getvalue()


def extract_result_archive(archive_bytes: bytes, output_root: Path, product_name: str) -> Path:
    digest = hashlib.sha256(archive_bytes).hexdigest()[:16]
    target_dir = Path(output_root) / f"{safe_path_part(product_name)}_restored_{digest}"
    target_dir.mkdir(parents=True, exist_ok=True)
    root_resolved = target_dir.resolve()

    with zipfile.ZipFile(io.BytesIO(archive_bytes)) as archive:
        for member in archive.infolist():
            member_name = member.filename.replace("\\", "/")
            if member.is_dir() or member_name.endswith("/"):
                continue
            target_path = (target_dir / member_name).resolve()
            try:
                target_path.relative_to(root_resolved)
            except ValueError:
                raise ValueError("归档文件包含不安全路径，已拒绝导入。")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, open(target_path, "wb") as destination:
                destination.write(source.read())
    return target_dir


def find_restored_input_file(output_dir: Path) -> Path | None:
    for name in ["uploaded_comments.xlsx", "uploaded_comments.xls", "uploaded_comments.csv"]:
        candidate = Path(output_dir) / name
        if candidate.exists():
            return candidate
    return None
