from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from v2.adapters.postgres import KnowledgeRepository
from v2.application.imports import ImportService


class ImportServiceTests(unittest.TestCase):
    def test_reimport_does_not_duplicate_comments_or_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = KnowledgeRepository(f"sqlite:///{Path(temp_dir) / 'v2.sqlite3'}", "private-owner")
            repo.initialize()
            service = ImportService(repo)

            first = service.import_comments(
                "智能药盒", "适老健康", "a.csv", ["提醒声音太小，老人听不清"]
            )
            second = service.import_comments(
                "智能药盒", "适老健康", "b.csv", ["提醒声音太小，老人听不清"]
            )

            self.assertEqual(first.report.inserted_count, 1)
            self.assertGreater(first.new_requirement_count, 0)
            self.assertEqual(second.report.inserted_count, 0)
            self.assertEqual(second.new_requirement_count, 0)
            self.assertEqual(repo.count_rows("comments"), 1)
            self.assertEqual(repo.count_rows("requirements"), first.new_requirement_count)


if __name__ == "__main__":
    unittest.main()
