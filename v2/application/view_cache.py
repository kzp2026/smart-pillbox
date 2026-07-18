from __future__ import annotations

import time
from collections.abc import Callable
from threading import RLock
from typing import Generic, Hashable, TypeVar


T = TypeVar("T")


class ExpiringViewCache(Generic[T]):
    """Small process-local cache for read-only UI data.

    V2 is a single-user app. A short-lived cache removes repeated network
    round-trips during Streamlit reruns while explicit invalidation keeps
    writes immediately visible.
    """

    def __init__(
        self,
        ttl_seconds: float = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = max(0.1, float(ttl_seconds))
        self._clock = clock
        self._values: dict[Hashable, tuple[float, T]] = {}
        self._lock = RLock()

    def get(self, key: Hashable, loader: Callable[[], T]) -> T:
        now = self._clock()
        with self._lock:
            cached = self._values.get(key)
            if cached and now - cached[0] < self.ttl_seconds:
                return cached[1]

        value = loader()
        with self._lock:
            self._values[key] = (self._clock(), value)
        return value

    def invalidate(self, prefix: tuple[object, ...] | None = None) -> None:
        with self._lock:
            if prefix is None:
                self._values.clear()
                return
            for key in tuple(self._values):
                if isinstance(key, tuple) and key[: len(prefix)] == prefix:
                    del self._values[key]
