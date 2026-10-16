"""Rebuild ippilab from the three survey manuscripts in docs/kb plus short entries.

Chunks follow document structure (stage, paper card, table row, reference).
Does not read or write paper_literature.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api")]

from app.config import get_settings  # noqa: E402
from app.services.kb_chunks import collect_corpus  # noqa: E402
from app.services.kb_embed import embed_text  # noqa: E402
from app.services.kb_milvus import (  # noqa: E402
    ALLOWED_COLLECTION,
    clear_collection,
    collection_name,
    ensure_collection,
    insert_rows,
)


def main() -> int:
    settings = get_settings()
    try:
        name = collection_name(settings)
    except Exception as exc:
        print(f"FAIL: {exc}")
        return 1
    if name != ALLOWED_COLLECTION:
        print("FAIL: collection is not ippilab")
        return 1
    kb_dir = settings.repo_root / "docs" / "kb"
    corpus = collect_corpus(kb_dir)
    print(f"collection={name} chunks={len(corpus)} kb_dir={kb_dir}")
    if not corpus:
        print("FAIL: no chunks")
        return 1
    ensure_collection(settings)
    clear_collection(settings)
    rows = []
    for index, item in enumerate(corpus, start=1):
        vector = embed_text(item["text"], settings=settings)
        if len(vector) != int(settings.llm_embed_dim):
            print(f"FAIL: dim {len(vector)} at chunk {index}")
            return 1
        rows.append({**item, "vector": vector})
        if index % 20 == 0 or index == len(corpus):
            print(f"embedded {index}/{len(corpus)}")
    written = insert_rows(settings, rows)
    print(f"PASS: inserted {written} into {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
