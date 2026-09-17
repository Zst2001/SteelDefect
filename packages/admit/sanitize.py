from __future__ import annotations

import os
from pathlib import Path


def sanitize_text(text: str, *, extra_paths: list[Path] | None = None) -> str:
    replacements: list[tuple[str, str]] = []
    for path in extra_paths or []:
        resolved = path.resolve()
        replacements.append((str(resolved), "<path>"))
        replacements.append((resolved.as_posix(), "<path>"))
    home = Path.home()
    replacements.append((str(home), "<home>"))
    replacements.append((home.as_posix(), "<home>"))
    env_user = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    if env_user:
        replacements.append((env_user, "<home>"))
    cleaned = text
    for src, dst in sorted(replacements, key=lambda item: len(item[0]), reverse=True):
        if src:
            cleaned = cleaned.replace(src, dst)
    return cleaned
