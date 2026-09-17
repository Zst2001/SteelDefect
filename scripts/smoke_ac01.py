"""AC-01 smoke: login → upload no-GT images → compare builtins → metrics available=false."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
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

    images_dir = ROOT / "assets" / "samples" / "neu" / "images"
    files = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[:2]
    if not files:
        print("missing sample images")
        return 1

    with httpx.Client(base_url=BASE, timeout=120.0, follow_redirects=True) as client:
        health = client.get("/health")
        health.raise_for_status()
        print("health", health.json())

        login = client.post("/auth/login", json={"username": env_user, "password": env_pass})
        if login.status_code != 200:
            print("login failed", login.status_code, login.text)
            return 1

        models = client.get("/models")
        models.raise_for_status()
        builtins = [m for m in models.json()["items"] if m["source"] == "builtin" and m["status"] == "runnable"]
        if len(builtins) < 1:
            print("no runnable builtins")
            return 1
        baseline_ids = [m["id"] for m in builtins[:3]]

        multipart = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in files]
        uploaded = client.post("/uploads/images", files=multipart)
        if uploaded.status_code != 200:
            print("upload failed", uploaded.status_code, uploaded.text)
            return 1
        batch_id = uploaded.json()["batch_id"]

        created = client.post(
            "/tasks/compare",
            json={"batch_id": batch_id, "baseline_version_ids": baseline_ids, "student_version_id": None},
        )
        if created.status_code != 200:
            print("compare failed", created.status_code, created.text)
            return 1
        task_id = created.json()["id"]
        print("task", task_id)

        deadline = time.time() + 1800
        status = "queued"
        while time.time() < deadline:
            task = client.get(f"/tasks/{task_id}")
            task.raise_for_status()
            status = task.json()["status"]
            print("status", status)
            if status in {"success", "partial_success", "failed"}:
                break
            time.sleep(3)
        if status not in {"success", "partial_success"}:
            print("task did not succeed", status, task.json().get("error_summary"))
            return 1

        metrics = client.get(f"/tasks/{task_id}/metrics")
        metrics.raise_for_status()
        body = metrics.json()
        print("metrics", body)
        if body.get("available") is not False:
            print("AC-01 fail: metrics.available must be false without GT")
            return 1
        blob = str(body).lower()
        if any(key in blob for key in ("miou", "dice", "acc")):
            print("AC-01 fail: metrics payload contains accuracy fields")
            return 1

        page = str(task.json()).lower()
        if "miou" in page or "\"dice\"" in page:
            print("AC-01 fail: task JSON contains metric names")
            return 1

        view = client.get(f"/tasks/{task_id}/samples/{files[0].stem}/view")
        view.raise_for_status()
        bundle = client.get(f"/tasks/{task_id}/bundle")
        if bundle.status_code != 200:
            print("bundle missing", bundle.status_code, bundle.text)
            return 1
        print("AC-01 smoke ok", "bytes", len(bundle.content))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
