from __future__ import annotations

import unittest

from v2.application.view_cache import ExpiringViewCache


class ExpiringViewCacheTests(unittest.TestCase):
    def test_reuses_value_until_ttl_expires(self) -> None:
        now = [100.0]
        cache = ExpiringViewCache(ttl_seconds=30, clock=lambda: now[0])
        calls = []

        def load() -> str:
            calls.append("load")
            return f"value-{len(calls)}"

        self.assertEqual(cache.get(("private", "snapshot"), load), "value-1")
        self.assertEqual(cache.get(("private", "snapshot"), load), "value-1")
        self.assertEqual(calls, ["load"])

        now[0] += 31

        self.assertEqual(cache.get(("private", "snapshot"), load), "value-2")
        self.assertEqual(calls, ["load", "load"])

    def test_prefix_invalidation_refreshes_only_one_private_scope(self) -> None:
        cache = ExpiringViewCache(ttl_seconds=30, clock=lambda: 100.0)
        calls = {"first": 0, "second": 0}

        def load(name: str) -> str:
            calls[name] += 1
            return f"{name}-{calls[name]}"

        first_key = ("private-a", "snapshot")
        second_key = ("private-b", "snapshot")
        self.assertEqual(cache.get(first_key, lambda: load("first")), "first-1")
        self.assertEqual(cache.get(second_key, lambda: load("second")), "second-1")

        cache.invalidate(("private-a",))

        self.assertEqual(cache.get(first_key, lambda: load("first")), "first-2")
        self.assertEqual(cache.get(second_key, lambda: load("second")), "second-1")


if __name__ == "__main__":
    unittest.main()
