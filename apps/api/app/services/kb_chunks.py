"""Structure-aware chunks for the academic corpus.

Paper cards, table rows, and bibliography entries stay intact.
Character sliding windows are not used.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.services.assistant_kb import SEED_DOCS

PARENT_MAX = 1500
MIN_CHARS = 20
HEADING_RE = re.compile(r"^(#{1,3})[ \t]+(.+?)\s*$", re.M)
FENCE_RE = re.compile(r"```.*?```", re.S)
CARD_RE = re.compile(r"^\d+\.\d+\b")


def _keyword_line(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("检索关键词"):
            return stripped
    return ""


def _too_small(text: str) -> bool:
    body = text.strip()
    if len(body) < MIN_CHARS:
        return True
    if re.fullmatch(r"[-—_\s]+", body):
        return True
    if re.fullmatch(r"检索关键词：[^\n]*", body):
        return True
    return False


def _pack_atoms(atoms: list[str], limit: int = PARENT_MAX) -> list[str]:
    groups: list[str] = []
    buf = ""
    for atom in atoms:
        piece = atom.strip()
        if not piece:
            continue
        if len(piece) > limit:
            if buf:
                groups.append(buf)
                buf = ""
            groups.append(piece)
            continue
        candidate = f"{buf}\n\n{piece}".strip() if buf else piece
        if len(candidate) <= limit:
            buf = candidate
        else:
            if buf:
                groups.append(buf)
            buf = piece
    if buf:
        groups.append(buf)
    return groups


def _atoms(text: str) -> list[str]:
    atoms: list[str] = []
    pos = 0
    for match in FENCE_RE.finditer(text):
        atoms.extend(_blank_pieces(text[pos : match.start()]))
        atoms.append(match.group(0).strip())
        pos = match.end()
    atoms.extend(_blank_pieces(text[pos:]))
    return [item for item in atoms if item.strip()]


def _blank_pieces(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]


def _is_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _is_sep(line: str) -> bool:
    return bool(re.fullmatch(r"\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?", line.strip()))


def _extract_tables(text: str) -> tuple[str, list[str]]:
    lines = text.splitlines()
    prose: list[str] = []
    rows: list[str] = []
    index = 0
    while index < len(lines):
        if index + 1 < len(lines) and _is_row(lines[index]) and _is_sep(lines[index + 1]):
            header = lines[index].strip()
            sep = lines[index + 1].strip()
            index += 2
            while index < len(lines) and _is_row(lines[index]):
                rows.append(f"{header}\n{sep}\n{lines[index].strip()}")
                index += 1
            continue
        prose.append(lines[index])
        index += 1
    return "\n".join(prose).strip(), rows


def _reference_items(text: str) -> list[str]:
    plain = FENCE_RE.sub(lambda match: "\n" + match.group(0).strip("` \n") + "\n", text)
    bibs = [item.strip() for item in re.findall(r"@\w+\{.*?\n\}", plain, flags=re.S) if item.strip()]
    label = ""
    numbered: list[str] = []
    for line in plain.splitlines():
        stripped = line.strip()
        if re.fullmatch(r"\*\*[^*]+\*\*", stripped):
            label = stripped.strip("*").strip()
            continue
        if not re.match(r"^(?:\[\d+\]|\d+\.)\s+", stripped):
            continue
        prefix = f"{label}\n" if label else ""
        numbered.append(prefix + stripped)
    if bibs:
        return bibs + numbered
    return numbered


def _is_reference_section(title: str, body: str) -> bool:
    if "参考文献" in title or "文献（" in title:
        return True
    doi_count = len(re.findall(r"doi", body, flags=re.I))
    numbered = len(re.findall(r"(?m)^(?:\[\d+\]|\d+\.)\s+", body))
    return doi_count >= 3 and numbered >= 3


def _is_paper_card(path_titles: list[str], title: str) -> bool:
    if any("必读论文卡" in item for item in path_titles[:-1]) and CARD_RE.match(title):
        return True
    return "必读论文卡" in " / ".join(path_titles) and CARD_RE.match(title)


def _block_type(path: Path, path_titles: list[str], title: str) -> str:
    if _is_paper_card(path_titles, title):
        return "paper_card"
    if "学习路线" in path.name:
        return "stage"
    return "narrative"


def _sections(text: str) -> list[tuple[str, str, list[str]]]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        return [("", text, [])]
    nodes: list[tuple[str, str, list[str]]] = []
    if matches[0].start() > 0:
        nodes.append(("", text[: matches[0].start()], []))
    stack: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        level = len(match.group(1))
        title = match.group(2).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        while stack and stack[-1][0] >= level:
            stack.pop()
        stack.append((level, title))
        nodes.append((title, body, [item[1] for item in stack]))
    return nodes


def _row(
    path: Path,
    section_path: str,
    block_type: str,
    body: str,
    *,
    keyword: str = "",
) -> dict[str, Any] | None:
    parent = body.strip()
    if keyword and keyword not in parent:
        parent = f"{keyword}\n{parent}".strip()
    if _too_small(parent):
        return None
    visible = f"{section_path}\n{parent}".strip() if section_path else parent
    return {
        "text": visible,
        "parent_text": parent,
        "parent_id": uuid4().hex,
        "chunk_level": "child",
        "file_id": path.stem,
        "file_name": path.name,
        "section_path": section_path or path.stem,
        "source_label": path.name,
        "category": "kb",
        "slug": path.stem,
        "approved": True,
        "parser": "markdown-struct",
        "block_type": block_type,
    }


def chunks_from_markdown(path: Path, text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for title, body, titles in _sections(text):
        section_path = " / ".join(titles) if titles else path.stem
        keyword = _keyword_line(body)
        if _is_paper_card(titles, title):
            made = _row(path, section_path, "paper_card", body, keyword=keyword)
            if made:
                rows.append(made)
            continue
        if _is_reference_section(title, body):
            items = _reference_items(body)
            if items:
                for item in items:
                    made = _row(path, section_path, "reference", item, keyword=keyword)
                    if made:
                        rows.append(made)
                continue
        prose, table_rows = _extract_tables(body)
        for table_row in table_rows:
            made = _row(path, section_path, "table_row", table_row, keyword=keyword)
            if made:
                rows.append(made)
        kind = _block_type(path, titles, title)
        for piece in _pack_atoms(_atoms(prose)):
            made = _row(path, section_path, kind, piece, keyword=keyword)
            if made:
                rows.append(made)
    return rows


def chunks_from_seed() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in SEED_DOCS:
        parent = str(item["body"]).strip()
        if _too_small(parent):
            continue
        rows.append(
            {
                "text": f"{item['title']}\n{parent}",
                "parent_text": parent,
                "parent_id": f"seed-{item['slug']}",
                "chunk_level": "child",
                "file_id": item["slug"],
                "file_name": item["title"],
                "section_path": item["title"],
                "source_label": "导师审定",
                "category": item["category"],
                "slug": item["slug"],
                "approved": True,
                "parser": "seed",
                "block_type": "narrative",
            }
        )
    return rows


def collect_corpus(kb_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if kb_dir.is_dir():
        for path in sorted(kb_dir.glob("*.md")):
            rows.extend(chunks_from_markdown(path, path.read_text(encoding="utf-8")))
    rows.extend(chunks_from_seed())
    return rows
