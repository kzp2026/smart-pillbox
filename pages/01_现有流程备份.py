from __future__ import annotations

import runpy
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
LEGACY_APP = ROOT_DIR / "app_legacy_current.py"

runpy.run_path(str(LEGACY_APP), run_name="__main__")
