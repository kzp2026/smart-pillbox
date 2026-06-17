from __future__ import annotations

import argparse

from common import (
    build_cooccurrence_matrix,
    compute_tfidf,
    doc_keyword_detail,
    ensure_output_dir,
    keyword_examples,
    load_cleaned_or_build,
    save_workbook,
    split_words,
)


def main() -> None:
    """第二阶段：TF-IDF 用户需求关键词提取。"""
    parser = argparse.ArgumentParser(description="第二阶段：提取用户需求关键词")
    parser.add_argument("--input", default=None, help="输入文件，默认读取 output/cleaned_comments.xlsx")
    parser.add_argument("--output-dir", default="output", help="输出目录")
    parser.add_argument("--top-n", type=int, default=80, help="输出关键词数量")
    args = parser.parse_args()

    output_dir = ensure_output_dir(args.output_dir)
    df = load_cleaned_or_build(args.input, output_dir)
    tokens_list = [split_words(value) for value in df["words"]]

    keyword_df = compute_tfidf(tokens_list, max_features=args.top_n, min_df=2)
    detail_df = doc_keyword_detail(df, keyword_df)
    co_df = build_cooccurrence_matrix(tokens_list, keyword_df["关键词"].head(50))
    example_df = keyword_examples(df, keyword_df["关键词"].head(50))

    output_path = output_dir / "需求关键词提取结果.xlsx"
    save_workbook(output_path, {
        "关键词排名": keyword_df,
        "评论关键词明细": detail_df,
        "关键词共现矩阵": co_df,
        "关键词示例评论": example_df,
    })

    print(f"已提取关键词数量：{len(keyword_df)}")
    print(f"已生成：{output_path}")


if __name__ == "__main__":
    main()
