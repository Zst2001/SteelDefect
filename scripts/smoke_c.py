"""Slice C smoke: dashboard, model cards, authenticated bundle download."""

from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

from infer.task_io import check_drawio_bundle_names  # noqa: E402

BASE = "http://127.0.0.1:8000/api"


def main() -> int:
    env_user = "student"
    env_pass = "StudentDev!234"
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_STUDENT_USERNAME="):
                env_user = line.split("=", 1)[1].strip()
            if line.startswith("SEED_STUDENT_PASSWORD="):
                env_pass = line.split("=", 1)[1].strip()

    with httpx.Client(base_url=BASE, timeout=60.0, follow_redirects=True, trust_env=False) as client:
        login = client.post("/auth/login", json={"username": env_user, "password": env_pass})
        if login.status_code != 200:
            print("login failed", login.status_code, login.text)
            return 1
        me = login.json()
        if me.get("role") != "student" or "role_label" not in me:
            print("auth payload missing role_label", me)
            return 1

        dash = client.get("/me/dashboard")
        dash.raise_for_status()
        body = dash.json()
        if "notices" not in body or "recent_tasks" not in body or "recent_models" not in body:
            print("dashboard missing fields", body.keys())
            return 1
        blob = str(body).lower()
        if "miou" in blob or "dice" in blob:
            print("dashboard leaked metrics names")
            return 1

        models = client.get("/models")
        models.raise_for_status()
        grouped = models.json()
        builtins = grouped.get("builtins") or []
        if len(builtins) < 3:
            print("expected 3 builtins", grouped)
            return 1
        if "mine" not in grouped or "shared" not in grouped:
            print("models list missing grouped sections", grouped.keys())
            return 1
        card = client.get(f"/models/{builtins[0]['id']}")
        card.raise_for_status()
        detail = card.json()
        if detail.get("task_type") != "语义分割":
            print("model card missing task type", detail)
            return 1
        if detail.get("flops") != "未测量":
            print("flops must stay 未测量", detail.get("flops"))
            return 1

        ready = [t for t in body.get("recent_tasks", []) if t.get("bundle_ready")]
        if not ready:
            print("no bundle_ready task; run smoke_ac01 first")
            return 1
        bundle = client.get(f"/tasks/{ready[0]['id']}/bundle")
        if bundle.status_code != 200 or bundle.headers.get("content-type", "").startswith("application/json"):
            print("bundle download failed", bundle.status_code, bundle.headers.get("content-type"), bundle.text[:200])
            return 1
        if len(bundle.content) < 100:
            print("bundle too small")
            return 1
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
            names = zf.namelist()
            check_drawio_bundle_names(names)
        print("slice C smoke ok", "builtins", len(builtins), "bundle", len(bundle.content), "files", len(names))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
