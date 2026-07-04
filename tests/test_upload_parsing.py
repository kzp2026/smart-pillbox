from __future__ import annotations

from io import BytesIO
import unittest

import pandas as pd

from scripts.upload_parsing import extract_comments, read_upload_table


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

    def test_reads_excel_upload_bytes(self) -> None:
        buffer = BytesIO()
        pd.DataFrame({"评论": ["字体要大"]}).to_excel(buffer, index=False)

        frame = read_upload_table("comments.xlsx", buffer.getvalue())

        self.assertEqual(extract_comments(frame, "评论"), ["字体要大"])


if __name__ == "__main__":
    unittest.main()
