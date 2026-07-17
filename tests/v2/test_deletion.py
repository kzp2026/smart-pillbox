from __future__ import annotations

import unittest

from v2.adapters.storage import DeleteReport
from v2.application.deletion import DeletionPlan, DeletionService


class FakeRepository:
    def __init__(self) -> None:
        self.deleted: list[int] = []

    def delete_product(self, product_id: int) -> bool:
        self.deleted.append(product_id)
        return True


class FakeStore:
    def __init__(self, report: DeleteReport) -> None:
        self.report = report

    def delete_many(self, paths: list[str]) -> DeleteReport:
        return self.report


class DeletionServiceTests(unittest.TestCase):
    def test_storage_failure_does_not_delete_database_or_report_success(self) -> None:
        repository = FakeRepository()
        store = FakeStore(DeleteReport(deleted=("runs/one/a.png",), failed=("runs/one/b.png",)))
        service = DeletionService(repository, store)
        plan = DeletionPlan(
            product_id=7,
            product_name="智能药盒",
            artifact_paths=("runs/one/a.png", "runs/one/b.png"),
            comment_count=10,
            requirement_count=3,
            run_count=1,
        )

        result = service.execute(plan)

        self.assertEqual(result.status, "partial")
        self.assertEqual(result.failed_paths, ("runs/one/b.png",))
        self.assertEqual(repository.deleted, [])

    def test_database_is_deleted_after_all_files_are_removed(self) -> None:
        repository = FakeRepository()
        store = FakeStore(DeleteReport(deleted=("runs/one/a.png",), failed=()))
        service = DeletionService(repository, store)
        plan = DeletionPlan(7, "智能药盒", ("runs/one/a.png",), 10, 3, 1)

        result = service.execute(plan)

        self.assertEqual(result.status, "succeeded")
        self.assertEqual(repository.deleted, [7])


if __name__ == "__main__":
    unittest.main()
