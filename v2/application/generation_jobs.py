from __future__ import annotations

from dataclasses import dataclass
from threading import RLock, Thread
from typing import Callable, Hashable


GenerationWork = Callable[[], object]


@dataclass(frozen=True)
class GenerationJobSnapshot:
    status: str
    error: str = ""


class GenerationJobRegistry:
    """Keep text generation out of Streamlit's request/rerun thread."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._threads: dict[Hashable, Thread] = {}
        self._snapshots: dict[Hashable, GenerationJobSnapshot] = {}

    def start(self, key: Hashable, work: GenerationWork) -> bool:
        with self._lock:
            active = self._threads.get(key)
            if active and active.is_alive():
                return False
            self._snapshots[key] = GenerationJobSnapshot("running")
            thread = Thread(target=self._run, args=(key, work), daemon=True)
            self._threads[key] = thread
            thread.start()
            return True

    def snapshot(self, key: Hashable) -> GenerationJobSnapshot | None:
        with self._lock:
            return self._snapshots.get(key)

    def wait(self, key: Hashable, timeout: float | None = None) -> bool:
        with self._lock:
            thread = self._threads.get(key)
        if thread is None:
            return True
        thread.join(timeout=timeout)
        return not thread.is_alive()

    def _run(self, key: Hashable, work: GenerationWork) -> None:
        try:
            work()
        except Exception:
            with self._lock:
                self._snapshots[key] = GenerationJobSnapshot(
                    "failed", "设计方案后台任务异常，请重新生成。"
                )
            return
        with self._lock:
            self._snapshots[key] = GenerationJobSnapshot("completed")
