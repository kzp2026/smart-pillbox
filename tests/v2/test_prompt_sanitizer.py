from __future__ import annotations

import unittest

from v2.application.prompt_sanitizer import sanitize_design_text, sanitize_visual_prompt


class PromptSanitizerTests(unittest.TestCase):
    def test_visual_prompt_replaces_historic_comment_excerpt(self) -> None:
        prompt = "统一产品设计锁定：智能药盒。评论证据线索：提醒声音太小，老人听不清。负向约束：不要水印。"

        sanitized = sanitize_visual_prompt(prompt)

        self.assertNotIn("提醒声音太小", sanitized)
        self.assertIn("评论证据线索：已保留于评论库，可按编号追溯。", sanitized)

    def test_design_text_removes_comment_evidence_section(self) -> None:
        text = "# 方案\n\n## 三、评论证据\n提醒声音太小，老人听不清。\n\n## 四、核心需求转译\n提醒反馈。"

        sanitized = sanitize_design_text(text)

        self.assertNotIn("提醒声音太小", sanitized)
        self.assertIn("## 四、核心需求转译", sanitized)


if __name__ == "__main__":
    unittest.main()
