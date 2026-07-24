from __future__ import annotations

from dataclasses import dataclass
from threading import RLock, Thread
from typing import Callable, Hashable


ImageProgress = Callable[[int, int, str, bool], None]
ImageWork = Callable[[ImageProgress], object]


@dataclass(frozen=True)
class ImageJobSnapshot:
    total: int
    completed: int
    succeeded: int
    failed: int
    status: str
    last_label: str = ""
    error: str = ""


class ImageJobRegistry:
    """Keeps paid image work out of Streamlit's request/rerun thread.

    This is intentionally process-local: artifacts and run status are persisted by
    ``ImageGenerationService``; the transient snapshot only improves live feedback.
    A process restart leaves a safe, retryable run record instead of blocking UI.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._threads: dict[Hashable, Thread] = {}
        self._snapshots: dict[Hashable, ImageJobSnapshot] = {}

    def start(self, key: Hashable, total: int, work: ImageWork) -> bool:
        with self._lock:
            active = self._threads.get(key)
            if active and active.is_alive():
                return False
            self._snapshots[key] = ImageJobSnapshot(
                total=max(0, int(total)),
                completed=0,
                succeeded=0,
                failed=0,
                status="running",
            )
            thread = Thread(target=self._run, args=(key, work), daemon=True)
            self._threads[key] = thread
            thread.start()
            return True

    def snapshot(self, key: Hashable) -> ImageJobSnapshot | None:
        with self._lock:
            return self._snapshots.get(key)

    def wait(self, key: Hashable, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._threads.get(key)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _run(self, key: Hashable, work: ImageWork) -> None:
        try:
            result = work(lambda completed, total, label, succeeded: self._progress(
                key, completed, total, label, succeeded
            ))
        except Exception:
            with self._lock:
                before = self._snapshots.get(key) or ImageJobSnapshot(0, 0, 0, 0, "failed")
                self._snapshots[key] = ImageJobSnapshot(
                    before.total,
                    before.completed,
                    before.succeeded,
                    before.failed,
                    "failed",
                    before.last_label,
                    "图像后台任务异常，请重新生成。",
                )
            return
        with self._lock:
            before = self._snapshots.get(key) or ImageJobSnapshot(0, 0, 0, 0, "completed")
            has_failures = bool(getattr(result, "failures", ()))
            self._snapshots[key] = ImageJobSnapshot(
                before.total,
                before.completed,
                before.succeeded,
                before.failed,
                "partial" if has_failures and before.succeeded else ("failed" if has_failures else "completed"),
                before.last_label,
            )

    def _progress(
        self,
        key: Hashable,
        completed: int,
        total: int,
        label: str,
        succeeded: bool,
    ) -> None:
        with self._lock:
            before = self._snapshots.get(key)
            if before is None:
                return
            completed_value = max(before.completed, min(max(0, int(completed)), max(0, int(total))))
            total_value = max(before.total, max(0, int(total)))
            succeeded_value = before.succeeded + (1 if succeeded and completed_value > before.completed else 0)
            failed_value = before.failed + (1 if not succeeded and completed_value > before.completed else 0)
            self._snapshots[key] = ImageJobSnapshot(
                total_value,
                completed_value,
                succeeded_value,
                failed_value,
                "running",
                str(label),
            )
