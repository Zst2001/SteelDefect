from __future__ import annotations

import sys
from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_third_party() -> Path:
    root = repo_root()
    third_party = root / "third_party"
    inserted = str(third_party)
    if inserted not in sys.path:
        sys.path.insert(0, inserted)
    packages = str(root / "packages")
    if packages not in sys.path:
        sys.path.insert(0, packages)
    return third_party


def assets_root() -> Path:
    return repo_root() / "assets"
