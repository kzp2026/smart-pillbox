from __future__ import annotations

from collections.abc import Iterable
import csv
from io import BytesIO
from pathlib import Path

import pandas as pd

from scripts.common import detect_comment_column


def _read_csv_with_stdlib(file_bytes: bytes) -> pd.DataFrame:
    """Read a valid CSV when pandas rejects its dialect or field layout."""
    last_error: UnicodeDecodeError | None = None
    for encoding in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
        try:
            text = file_bytes.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        sample = text[:8192]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",\t;|")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.reader(text.splitlines(), dialect=dialect))
        if not rows:
            return pd.DataFrame()
        width = len(rows[0])
        normalized_rows = [row[:width] + [""] * max(0, width - len(row)) for row in rows[1:]]
        return pd.DataFrame(normalized_rows, columns=rows[0])
    if last_error:
        raise last_error
    raise UnicodeDecodeError("csv", b"", 0, 0, "无法识别 CSV 编码")


def read_upload_table(filename: str, file_bytes: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    buffer = BytesIO(file_bytes)
    if suffix in [".xlsx", ".xls"]:
        return pd.read_excel(buffer)
    if suffix == ".csv":
        last_error: UnicodeDecodeError | None = None
        parser_error: pd.errors.ParserError | None = None
        for encoding in ["utf-8-sig", "utf-8", "gb18030", "gbk"]:
            try:
                buffer.seek(0)
                return pd.read_csv(buffer, encoding=encoding)
            except UnicodeDecodeError as exc:
                last_error = exc
            except pd.errors.ParserError as exc:
                parser_error = exc
                break
        try:
            return _read_csv_with_stdlib(file_bytes)
        except UnicodeDecodeError:
            if parser_error:
                raise parser_error
        if last_error:
            raise last_error
        if parser_error:
            raise parser_error
        return _read_csv_with_stdlib(file_bytes)
    raise ValueError(f"不支持的文件格式：{suffix}")


def read_uploaded_tables(uploaded_files: Iterable[tuple[str, bytes]]) -> pd.DataFrame:
    """Read selected CSV/Excel files and combine their rows in selection order."""
    frames = [read_upload_table(filename, file_bytes) for filename, file_bytes in uploaded_files]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def candidate_comment_columns(df: pd.DataFrame) -> list[str]:
    columns = [str(column) for column in df.columns if df[column].dropna().astype(str).str.strip().any()]
    return columns or [str(column) for column in df.columns]


def default_comment_column(df: pd.DataFrame) -> str:
    return str(detect_comment_column(df))


def extract_comments(df: pd.DataFrame, comment_column: str) -> list[str]:
    if comment_column not in df.columns:
        raise ValueError(f"未找到评论列：{comment_column}")
    return [text for text in df[comment_column].dropna().astype(str).str.strip().tolist() if text]
