from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXPECTED_SHA1 = {
    "app.py": "af75821eaea41827af64d7c63fd152948aa2bc4c",
    "app_legacy_current.py": "60ca9b89938f8ceb2dbb360b600604c77a006eca",
    "pages/01_现有流程备份.py": "899ca064214251430ecea75e7f1bc3617a2e42cd",
    "pages/02_产品管理.py": "92836021ce996dffaf14787de7b4c9bcff4bb951",
    "pages/03_旧版结果预览.py": "de0fdadd1f9d1b2a6ed55263fb2868ca4e10e2fd",
}


class OriginalSiteFreezeTests(unittest.TestCase):
    def test_original_entrypoints_are_unchanged(self) -> None:
        actual = {}
        for relative in EXPECTED_SHA1:
            content = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
            git_blob = b"blob " + str(len(content)).encode("ascii") + b"\0" + content
            actual[relative] = hashlib.sha1(git_blob).hexdigest()

        self.assertEqual(actual, EXPECTED_SHA1)


if __name__ == "__main__":
    unittest.main()
