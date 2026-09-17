"""Slice F: official eval on seeded NEU-20; n=20 metrics; 8-sample viz; Acc in details."""

from __future__ import annotations

import io
import sys
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

from infer.task_io import check_drawio_bundle_names, select_preview_keys  # noqa: E402

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
    deadline = time.time() + 3600
    last = {}
    while time.time() < deadline:
        task = client.get(f"/tasks/{task_id}")
        task.raise_for_status()
        last = task.json()
        status = last["status"]
        print("status", status, "preview", len(last.get("preview_sample_keys") or []))
        if status in {"success", "partial_success", "failed"}:
            return last
        time.sleep(3)
    raise RuntimeError(f"task timeout {task_id} last={last}")


def main() -> int:
    env_user, env_pass = _creds()
    images_dir = ROOT / "assets" / "samples" / "neu" / "images"
    images = sorted(p for p in images_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png"})
    if len(images) < 2:
        print("missing NEU sample images")
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
        ready = []
        for dataset in datasets.json()["items"]:
            for version in dataset.get("versions") or []:
                if version.get("eval_ready"):
                    ready.append((dataset, version))
        if not ready:
            print("no eval_ready dataset version (need seeded NEU-20)")
            return 1
        dataset, version = ready[0]
        if dataset.get("name") != "NEU-20":
            print("expected NEU-20 as v1 official set", dataset.get("name"))
            return 1
        if int(version.get("sample_count") or 0) != 20:
            print("NEU-20 should have 20 samples", version)
            return 1

        forbidden = client.get(f"/datasets/{dataset['id']}/gt/{images[0].stem}")
        if forbidden.status_code != 403 or forbidden.json().get("code") != "GT_FORBIDDEN":
            print("preset GT should stay 403 for student", forbidden.status_code, forbidden.text[:200])
            return 1

        models = client.get("/models")
        models.raise_for_status()
        builtins = [
            m
            for m in models.json().get("items", models.json().get("builtins", []))
            if m.get("source") == "builtin" and m.get("status") == "runnable"
        ]
        if not builtins:
            grouped = models.json()
            builtins = [
                m
                for m in grouped.get("builtins", [])
                if m.get("source") == "builtin" and m.get("status") == "runnable"
            ]
        if not builtins:
            print("no runnable builtins", models.json().keys())
            return 1
        baseline_ids = [builtins[0]["id"]]

        image_files = [("files", (p.name, p.read_bytes(), "image/jpeg")) for p in images[:1]]
        uploaded = client.post("/uploads/images", files=image_files)
        if uploaded.status_code != 200:
            print("control upload failed", uploaded.status_code, uploaded.text)
            return 1
        blocked = client.post(
            "/tasks/eval",
            json={
                "dataset_version_id": uploaded.json()["batch_id"],
                "baseline_version_ids": baseline_ids,
                "student_version_id": None,
            },
        )
        if blocked.status_code != 400 or blocked.json().get("code") != "EVAL_DATASET_FORBIDDEN":
            print("upload batch must not enter eval", blocked.status_code, blocked.text)
            return 1

        created = client.post(
            "/tasks/eval",
            json={
                "dataset_version_id": version["id"],
                "baseline_version_ids": baseline_ids,
                "student_version_id": None,
            },
        )
        if created.status_code != 200:
            print("eval create failed", created.status_code, created.text)
            return 1
        task = created.json()
        if task.get("type") != "eval" or task.get("has_gt") is not True:
            print("eval task fields", task)
            return 1
        if task.get("n") != 20:
            print("eval should attach all 20 samples", task.get("n"), len(task.get("samples") or []))
            return 1
        task_id = task["id"]
        print("eval task", task_id)
        done = _wait_task(client, task_id)
        if done["status"] not in {"success", "partial_success"}:
            print("eval did not succeed", done.get("error_summary"))
            return 1

        expected_preview = select_preview_keys([p.stem for p in images], 8)
        preview = done.get("preview_sample_keys") or []
        if preview != expected_preview:
            print("preview keys mismatch", preview, "expected", expected_preview)
            return 1

        metrics = client.get(f"/tasks/{task_id}/metrics")
        metrics.raise_for_status()
        body = metrics.json()
        print("metrics", body)
        if body.get("available") is not True:
            print("official metrics must be available")
            return 1
        if body.get("scope") != "official_split" or body.get("n") != 20:
            print("scope/n mismatch", body.get("scope"), body.get("n"))
            return 1
        disclaimer = str(body.get("disclaimer") or "")
        if "NEU-20" not in disclaimer or "test split" not in disclaimer:
            print("missing honest NEU-20 disclaimer", disclaimer)
            return 1
        rows = body.get("models") or []
        if not rows:
            print("metrics models empty")
            return 1
        if any("Acc" not in row for row in rows):
            print("Acc should be present in official eval details payload", rows)
            return 1
        miou_values = [float(row["mIoU"]) for row in rows]
        if any(v < 0 or v > 1 for v in miou_values) or all(v == 0.0 for v in miou_values):
            print("mIoU invalid", miou_values)
            return 1

        montage_keys = sorted(
            {a["sample_key"] for a in done.get("artifacts") or [] if a.get("kind") == "montage" and a.get("sample_key")}
        )
        if montage_keys != expected_preview:
            print("montage sampling mismatch", montage_keys)
            return 1

        bundle = client.get(f"/tasks/{task_id}/bundle")
        if bundle.status_code != 200:
            print("bundle missing", bundle.status_code, bundle.text)
            return 1
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
            names = zf.namelist()
            check_drawio_bundle_names(names)
            origin_keys = sorted({name.split("/")[1].rsplit(".", 1)[0] for name in names if name.startswith("origin/")})
            if origin_keys != expected_preview:
                print("bundle origin sampling mismatch", origin_keys)
                return 1
            if any(name.endswith("metrics.json") for name in names) or any(name.endswith(".pdf") for name in names):
                print("bundle leaked metrics.json or pdf", names)
                return 1

        print("slice F smoke ok", task_id)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
