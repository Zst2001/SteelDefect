from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_api_tree_never_imports_student_runner() -> None:
    api_root = ROOT / "apps" / "api"
    forbidden = ("admit.runner", "spec_from_file_location")
    hits: list[str] = []
    for path in api_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(token in text for token in forbidden):
            hits.append(str(path.relative_to(ROOT)))
    assert hits == []


def test_web_process_docs_forbid_student_import() -> None:
    jobs = (ROOT / "apps" / "worker" / "jobs.py").read_text(encoding="utf-8")
    assert "infer_student_masks" in jobs
    assert "student_model" not in jobs
