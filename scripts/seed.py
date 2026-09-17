from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for candidate in (ROOT, ROOT / "packages", ROOT / "third_party", ROOT / "apps" / "api"):
    sys.path.insert(0, str(candidate))

from app.config import get_settings
from app.db.session import SessionLocal
from app.services.seed import seed_all


def main() -> None:
    settings = get_settings()
    db = SessionLocal()
    try:
        seed_all(db, settings)
        print("seed ok")
    finally:
        db.close()


if __name__ == "__main__":
    main()
