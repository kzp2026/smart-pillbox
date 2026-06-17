from __future__ import annotations

import argparse

from common import build_cleaned_dataframe, ensure_output_dir, save_workbook


def main() -> None:
    """第一阶段：评论数据读取与清洗。"""
    parser = argparse.ArgumentParser(description="第一阶段：读取并清洗智能药盒评论数据")
    parser.add_argument("--input", default=None, help="输入文件路径，可不带扩展名，例如 data/京东智能药盒评论")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    cleaned_df, source_path, comment_col = build_cleaned_dataframe(args.input)
    output_path = output_dir / "cleaned_comments.xlsx"

    summary_df = cleaned_df.head(30).copy()
    info_df = cleaned_df.iloc[:0].copy()
    info_df.loc[0, "源文件"] = str(source_path)
    info_df.loc[0, "识别评论列"] = comment_col
    info_df.loc[0, "有效评论数"] = len(cleaned_df)

    save_workbook(output_path, {
        "清洗后评论": cleaned_df,
        "字段识别说明": info_df,
        "前30行预览": summary_df,
    })

    print(f"源文件：{source_path}")
    print(f"识别到的评论文本列：{comment_col}")
    print(f"有效评论数：{len(cleaned_df)}")
    print(f"已生成：{output_path}")


if __name__ == "__main__":
    main()
