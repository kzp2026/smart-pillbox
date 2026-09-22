"""Keep prompt views free of raw review text while retaining source records in the private library."""

from __future__ import annotations

import re


_COMMENT_LINE = re.compile(
    r"评论证据线索：.*?(?=(?:负向约束：|通用质量要求：)|\Z)", re.DOTALL
)
_COMMENT_SECTION = re.compile(r"^##\s*三、评论证据\s*$.*?(?=^##\s|\Z)", re.MULTILINE | re.DOTALL)


def sanitize_visual_prompt(value: object) -> str:
    """Replace legacy embedded review excerpts in a visual prompt for display/download."""

    prompt = str(value or "")
    return _COMMENT_LINE.sub("评论证据线索：已保留于评论库，可按编号追溯。", prompt).strip()


def sanitize_design_text(value: object) -> str:
    """Hide the legacy raw-review section without changing the stored historic result."""

    return _COMMENT_SECTION.sub("", str(value or "")).strip()
