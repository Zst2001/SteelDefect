"""Slice E / AC-04: paired GT yields real mIoU; images-only stays available=false."""

from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

from infer.task_io import check_drawio_bundle_names  # noqa: E402

BASE = "http://127.0.0.1:8000/api"


def _creds() -> tuple[str, str]:
    env_user = "student"
    env_pass = "StudentDev!234"
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_STUDENT_USERNAME="):
                env_user = line.split("=", 1)[1].strip()
            if line.startswith("SEED_STUDENT_PASSWORD="):
                env_pass = line.split("=", 1)[1].strip()
    return env_user, env_pass


def _wait_task(client: httpx.Client, task_id: str) -> dict:
    deadline = time.time() + 1800
    last = {}
    while time.time() < deadline:
        task = client.get(f"/tasks/{task_id}")
        task.raise_for_status()
        last = task.json()
        status = last["status"]
        print("status", status)
        if status in {"success", "partial_success", "failed"}:
            return last
        time.sleep(3)
    raise RuntimeError(f"task timeout {task_id} last={last}")


def main() -> int:
    env_user, env_pass = _creds()
    images_dir = ROOT / "assets" / "samples" / "neu" / "images"
    masks_dir = ROOT / "assets" / "samples" / "neu" / "masks"
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})[:2]
    masks = [masks_dir / f"{p.stem}.png" for p in images]
    if not images or not all(p.is_file() for p in masks):
        print("missing sample image/mask pairs")
        return 1

    with httpx.Client(base_url=BASE, timeout=120.0, follow_redirects=True, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()
        login = client.post("/auth/login", json={"username": env_user, "password": env_pass})
        if login.status_code != 200:
            print("login failed", login.status_code, login.text)
            return 1

        datasets = client.get("/datasets")
        datasets.raise_for_status()
        preset = next((d for d in datasets.json()["items"] if d.get("visibility") == "preset"), None)
        if preset:
            forbidden = client.get(f"/datasets/{preset['id']}/gt/{images[0].stem}")
            if forbidden.status_code != 403:
                print("preset GT should stay 403 for student", forbidden.status_code, forbidden.text[:200])
                return 1
            if forbidden.json().get("code") != "GT_FORBIDDEN":
                print("expected GT_FORBIDDEN", forbidden.text)
                return 1

        models = client.get("/models")
        models.raise_for_status()
        builtins = [m for m in models.json()["items"] if m["source"] == "builtin" and m["status"] == "runnable"]
        if not builtins:
            print("no runnable builtins")
            return 1
        baseline_ids = [m["id"] for m in builtins[:3]]

        image_files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in images]
        uploaded = client.post("/uploads/images", files=image_files)
        if uploaded.status_code != 200:
            print("image upload failed", uploaded.status_code, uploaded.text)
            return 1
        batch_id = uploaded.json()["batch_id"]
        mask_files = [("files", (p.name, p.read_bytes(), "image/png")) for p in masks]
        masked = client.post("/uploads/masks", data={"batch_id": batch_id}, files=mask_files)
        if masked.status_code != 200:
            print("mask upload failed", masked.status_code, masked.text)
            return 1
        if masked.json().get("has_gt") is not True:
            print("paired masks should set has_gt true", masked.json())
            return 1

        created = client.post(
            "/tasks/compare",
            json={"batch_id": batch_id, "baseline_version_ids": baseline_ids, "student_version_id": None},
        )
        if created.status_code != 200:
            print("compare failed", created.status_code, created.text)
            return 1
        task = created.json()
        if task.get("has_gt") is not True:
            print("task.has_gt expected true", task)
            return 1
        gt_task_id = task["id"]
        print("gt task", gt_task_id)
        done = _wait_task(client, gt_task_id)
        if done["status"] not in {"success", "partial_success"}:
            print("gt task did not succeed", done.get("error_summary"))
            return 1

        metrics = client.get(f"/tasks/{gt_task_id}/metrics")
        metrics.raise_for_status()
        body = metrics.json()
        print("metrics", body)
        if body.get("available") is not True:
            print("AC-04 fail: metrics.available must be true with GT")
            return 1
        if "不代表完整测试集" not in str(body.get("disclaimer", "")):
            print("missing batch-reference disclaimer", body.get("disclaimer"))
            return 1
        rows = body.get("models") or []
        if not rows:
            print("metrics models empty")
            return 1
        miou_values = [float(row["mIoU"]) for row in rows]
        if any(v < 0 or v > 1 for v in miou_values):
            print("mIoU out of range", miou_values)
            return 1
        if all(v == 0.0 for v in miou_values):
            print("AC-04 fail: all mIoU are zero (zero-fill)")
            return 1
        blob = str(body).lower()
        if '"acc"' in blob or "acc_per_class" in blob:
            print("Acc should not be a headline field in Slice E payload")
            return 1

        bundle = client.get(f"/tasks/{gt_task_id}/bundle")
        if bundle.status_code != 200:
            print("bundle missing", bundle.status_code, bundle.text)
            return 1
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
            names = zf.namelist()
            check_drawio_bundle_names(names)
            if not any(name.startswith("gt/") for name in names):
                print("bundle missing gt/", names)
                return 1
            if not any(name.startswith("error/") for name in names):
                print("bundle missing error/", names)
                return 1
            if any(name.endswith("metrics.json") for name in names) or any(name.endswith(".pdf") for name in names):
                print("bundle leaked metrics.json or pdf", names)
                return 1

        # No-GT control: same two images, no masks.
        uploaded2 = client.post("/uploads/images", files=image_files)
        uploaded2.raise_for_status()
        created2 = client.post(
            "/tasks/compare",
            json={
                "batch_id": uploaded2.json()["batch_id"],
                "baseline_version_ids": baseline_ids[:1],
                "student_version_id": None,
            },
        )
        if created2.status_code != 200:
            print("no-gt compare failed", created2.status_code, created2.text)
            return 1
        if created2.json().get("has_gt") is not False:
            print("no-gt task should have has_gt false")
            return 1
        no_gt_id = created2.json()["id"]
        print("no-gt task", no_gt_id)
        done2 = _wait_task(client, no_gt_id)
        if done2["status"] not in {"success", "partial_success"}:
            print("no-gt task failed", done2.get("error_summary"))
            return 1
        metrics2 = client.get(f"/tasks/{no_gt_id}/metrics")
        metrics2.raise_for_status()
        body2 = metrics2.json()
        if body2 != {"available": False}:
            print("no-gt metrics must be {available:false}", body2)
            return 1
        blob2 = str(body2).lower()
        if any(key in blob2 for key in ("miou", "dice", "acc")):
            print("no-gt metrics leaked accuracy fields", body2)
            return 1

        print("AC-04 / slice E smoke ok", "gt", gt_task_id, "no-gt", no_gt_id)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
