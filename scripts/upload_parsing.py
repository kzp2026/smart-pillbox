from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd

from scripts.common import detect_comment_column


def read_upload_table(filename: str, file_bytes: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    buffer = BytesIO(file_bytes)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(buffer)
    if suffix == ".csv":
        last_error: UnicodeDecodeError | None = None
        for encoding in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
            try:
                buffer.seek(0)
                return pd.read_csv(buffer, encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
        if last_error:
            raise last_error
        buffer.seek(0)
        return pd.read_csv(buffer)
    raise ValueError(f"不支持的文件格式：{suffix}")


def candidate_comment_columns(df: pd.DataFrame) -> list[str]:
    columns = [str(column) for column in df.columns if df[column].dropna().astype(str).str.strip().any()]
    return columns or [str(column) for column in df.columns]


def default_comment_column(df: pd.DataFrame) -> str:
    return str(detect_comment_column(df))


def extract_comments(df: pd.DataFrame, comment_column: str) -> list[str]:
    if comment_column not in df.columns:
        raise ValueError(f"未找到评论列：{comment_column}")
    return [text for text in df[comment_column].dropna().astype(str).str.strip().tolist() if text]
