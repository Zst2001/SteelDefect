from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for candidate in (ROOT, ROOT / "packages", ROOT / "third_party", ROOT / "apps" / "api"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

from app.cache import rq_connection  # noqa: E402
from app.config import get_settings  # noqa: E402
from rq import Queue, SimpleWorker  # noqa: E402


def main() -> None:
    settings = get_settings()
    connection = rq_connection()
    queue = Queue(settings.rq_queue_name, connection=connection)
    # SimpleWorker keeps L1 builtin modules in-process and works on Windows (no fork).
    worker = SimpleWorker([queue], connection=connection, name="lab-worker")
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
