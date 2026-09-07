"""Minimal recoverable code snapshot used by offline reproduction."""
from pathlib import Path


def source_snapshot() -> dict[str, bytes]:
    root=Path(__file__).resolve().parents[2]
    # Explicit code-only allowlist: never include Secrets, .env, data or caches.
    selected=[root/'v2/__init__.py',root/'v2/application/__init__.py',root/'v2/application/imports.py',
              root/'v2/adapters/__init__.py',root/'v2/adapters/postgres.py',root/'v2/adapters/storage.py',
              root/'v2/domain/__init__.py',root/'v2/domain/models.py']
    selected += [root/'experiment/__init__.py', root/'experiment/pipeline/semantics.py']
    selected+=sorted((root/'v2/research').glob('*.py'))
    return {p.relative_to(root).as_posix():p.read_bytes() for p in selected if p.exists()}
