from __future__ import annotations

import tempfile
import unittest
import os
from pathlib import Path

from verify_contract import (
    REQUIRED_PATHS,
    build_test_environment,
    build_unittest_command,
    check_required_paths,
    count_top_level_tuple_items,
    find_forbidden_markers,
)


class ContractVerifierTests(unittest.TestCase):
    def test_public_error_sanitizer_and_regression_test_are_required(self) -> None:
        self.assertIn("v2/ui/errors.py", REQUIRED_PATHS)
        self.assertIn("tests/v2/test_error_messages.py", REQUIRED_PATHS)

    def test_missing_required_path_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            errors = check_required_paths(Path(temp_dir), ("app.py", "v2/app.py"))

        self.assertEqual(errors, ["缺少必需路径：app.py", "缺少必需路径：v2/app.py"])

    def test_top_level_tuple_count_reads_project_catalogs(self) -> None:
        source = "LEGACY_STAGES = (\n    object(),\n    object(),\n)\n"

        self.assertEqual(count_top_level_tuple_items(source, "LEGACY_STAGES"), 2)

    def test_unfinished_skill_markers_are_rejected(self) -> None:
        errors = find_forbidden_markers("description: [TODO]\ntext \ufffd")

        self.assertEqual(errors, ["Skill 中仍有 TODO 占位符。", "Skill 中存在乱码替换字符。"])

    def test_repository_test_dependencies_are_added_to_pythonpath(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / ".test_deps").mkdir()

            env = build_test_environment(root, {"PYTHONPATH": "existing-deps"})

        self.assertEqual(
            env["PYTHONPATH"].split(os.pathsep),
            [str(root / ".test_deps"), "existing-deps"],
        )

    def test_full_suite_uses_repo_top_level_to_avoid_v2_package_shadowing(self) -> None:
        command = build_unittest_command("all")

        self.assertEqual(command[-7:], ["discover", "-s", "tests", "-t", ".", "-p", "test_*.py"])


if __name__ == "__main__":
    unittest.main()
