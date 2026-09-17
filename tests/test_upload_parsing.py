from __future__ import annotations

from io import BytesIO
import unittest
from unittest.mock import patch

import pandas as pd

from scripts.upload_parsing import extract_comments, read_upload_table, read_uploaded_tables


class UploadParsingTests(unittest.TestCase):
    def test_can_extract_comments_from_selected_column(self) -> None:
        frame = pd.DataFrame(
            {
                "订单号": ["A001", "A002", "A003"],
                "评价内容": ["提醒声音要明显", "药仓分格清楚", ""],
                "备注": ["快递快", "送给父母", None],
            }
        )

        comments = extract_comments(frame, "评价内容")

        self.assertEqual(comments, ["提醒声音要明显", "药仓分格清楚"])

    def test_reads_csv_upload_bytes_with_chinese_encoding(self) -> None:
        csv_bytes = "评论,评分\n提醒声音要明显,5\n药仓分格清楚,4\n".encode("gbk")

        frame = read_upload_table("comments.csv", csv_bytes)

        self.assertEqual(list(frame.columns), ["评论", "评分"])
        self.assertEqual(extract_comments(frame, "评论"), ["提醒声音要明显", "药仓分格清楚"])

    def test_reads_csv_with_standard_library_fallback_after_pandas_parser_error(self) -> None:
        csv_bytes = "评论,评分\n提醒声音要明显,5\n药仓分格清楚,4\n".encode("utf-8-sig")

        with patch("scripts.upload_parsing.pd.read_csv", side_effect=pd.errors.ParserError("fixture")):
            frame = read_upload_table("comments.csv", csv_bytes)

        self.assertEqual(list(frame.columns), ["评论", "评分"])
        self.assertEqual(extract_comments(frame, "评论"), ["提醒声音要明显", "药仓分格清楚"])

    def test_reads_excel_upload_bytes(self) -> None:
        buffer = BytesIO()
        pd.DataFrame({"评论": ["字体要大"]}).to_excel(buffer, index=False)

        frame = read_upload_table("comments.xlsx", buffer.getvalue())

        self.assertEqual(extract_comments(frame, "评论"), ["字体要大"])

    def test_merges_multiple_uploaded_files_in_selection_order(self) -> None:
        uploaded_files = [
            ("first.csv", "评论,评分\n提醒声音要明显,5\n".encode("utf-8")),
            ("second.csv", "评论,评分\n药仓分格清楚,4\n".encode("utf-8")),
        ]

        frame = read_uploaded_tables(uploaded_files)

        self.assertEqual(frame["评论"].tolist(), ["提醒声音要明显", "药仓分格清楚"])
        self.assertEqual(frame["评分"].tolist(), [5, 4])


if __name__ == "__main__":
    unittest.main()
