from __future__ import annotations

from typing import Any

from v2.application.view_cache import ExpiringViewCache


# Streamlit executes the entry script in a fresh module on every widget change.
# State kept in this imported module survives those reruns for the process lifetime.
LOGIN_GUARDS: dict[str, Any] = {}
REPOSITORIES: dict[tuple[str, str, str], Any] = {}
STORES: dict[tuple[str, ...], object] = {}
VIEW_CACHE: ExpiringViewCache[Any] = ExpiringViewCache(ttl_seconds=30)
