from __future__ import annotations

import threading
import time
import unittest

from v2.application.image_jobs import ImageJobRegistry


class ImageJobRegistryTests(unittest.TestCase):
    def test_start_returns_immediately_while_work_continues_in_background(self) -> None:
        registry = ImageJobRegistry()
        started = threading.Event()
        release = threading.Event()

        def work(progress):
            started.set()
            release.wait(timeout=2)
            progress(1, 1, "产品效果图", True)
            return object()

        began = time.monotonic()
        self.assertTrue(registry.start("run-1", 1, work))
        self.assertLess(time.monotonic() - began, 0.2)
        self.assertTrue(started.wait(timeout=1))
        self.assertEqual(registry.snapshot("run-1").status, "running")
        self.assertEqual(registry.snapshot("run-1").completed, 0)

        release.set()
        self.assertTrue(registry.wait("run-1", timeout=1))
        snapshot = registry.snapshot("run-1")
        self.assertEqual(snapshot.status, "completed")
        self.assertEqual(snapshot.completed, 1)
        self.assertEqual(snapshot.succeeded, 1)

    def test_rejects_a_duplicate_active_job_for_the_same_run(self) -> None:
        registry = ImageJobRegistry()
        release = threading.Event()

        self.assertTrue(registry.start("run-1", 1, lambda progress: release.wait(timeout=2)))
        self.assertFalse(registry.start("run-1", 1, lambda progress: None))
        release.set()
        self.assertTrue(registry.wait("run-1", timeout=1))


if __name__ == "__main__":
    unittest.main()
