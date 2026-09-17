from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
for candidate in (ROOT, ROOT / "packages", ROOT / "third_party", ROOT / "apps" / "api"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)
