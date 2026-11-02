"""Explicit opt-in real MobileNet CPU smoke; never included in default tests.

Run: .venv/Scripts/python.exe -B tests/check_classification_cpu_flow.py
Uses the existing isolation runner, temporary SQLite/storage, fake queue, real
validated trusted weights, synthetic images and in-process HTTP routes only.
"""
from pathlib import Path
import json
import platform
import runpy
import sys
import time

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    platform.uname()
    # Preserve only this reviewed trusted CPU executor before the normal runner
    # disables all executors. The test injects it into this worker only.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
    import infer.classification as trusted
    import torch
    trusted._explicit_cpu_smoke_predict = trusted.predict_images
    trusted._explicit_cpu_smoke_load = torch.load
    trusted._explicit_cpu_smoke_report = args.report
    print("EXPLICIT CPU SMOKE: only trusted MobileNet prediction is restored inside this test; all other runner isolation remains enabled.")
    namespace = runpy.run_path(str(Path(__file__).with_name("run_phase_a_tests.py")))
    namespace["DEFAULT_TARGETS"].append("tests/check_classification_cpu_flow.py")
    sys.argv = ["tests/run_phase_a_tests.py", "tests/check_classification_cpu_flow.py"]
    raise SystemExit(namespace["main"]())

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use explicit CPU flow script with its isolation bootstrap")

from app.db.models import MetricSet, Task
from app.routers import classification as router
from app.services import classification as service
from app.services.dispatch import Delivery
from apps.worker import classification as worker, jobs
from test_classification_backend import files
from test_phase_a_authorization import lab, client


def test_real_mobilenet_cpu_http_flow(lab, monkeypatch):
    import infer.classification as trusted
    import torch
    monkeypatch.setattr(worker, "predict_images", trusted._explicit_cpu_smoke_predict)
    monkeypatch.setattr(torch, "load", trusted._explicit_cpu_smoke_load)
    monkeypatch.setattr(service, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(service, "invalidate_after_write", lambda *args: None)
    monkeypatch.setattr(worker, "invalidate_after_write", lambda *args: None)
    queued = []
    def enqueue(_s, function, task_id, timeout, **kwargs):
        queued.append(task_id)
        assert function == "apps.worker.jobs.run_classification"
        return Delivery("confirmed", f"task-{task_id}")
    monkeypatch.setattr(service, "enqueue", enqueue)
    evidence = {"scope": "Synthetic CPU smoke; not an accuracy evaluation", "model": "mobilenet_v3_small", "runs": []}
    for labels in (None, [0, 1]):
        with client(lab, lab.owner) as http:
            http.app.include_router(router.router, prefix="/api")
            data = {} if labels is None else {"labels_json": json.dumps(labels)}
            response = http.post("/api/classification/uploads", files=[("files", (name, content, "image/png")) for name, content in files()], data=data)
            assert response.status_code == 200, response.text
            batch = response.json()
            response = http.post("/api/classification/tasks", json={"batch_id": batch["batch_id"], "model_slugs": ["mobilenet_v3_small"]}, headers={"Idempotency-Key": "cpu-flow-" + str(labels)})
            assert response.status_code == 200, response.text
            task_id = response.json()["id"]
            assert task_id in queued
            start = time.perf_counter()
            jobs.run_classification(task_id)
            elapsed = time.perf_counter() - start
            lab.db.expire_all()
            result = http.get(f"/api/tasks/{task_id}")
            assert result.status_code == 200, result.text
            result = result.json()
            assert result["status"] == "success", result["error_summary"]
            assert len(result["predictions"]) == 2
            assert result["metrics"]["available"] is bool(labels)
            assert lab.db.query(MetricSet).filter_by(task_id=task_id).count() == int(bool(labels))
            downloaded = http.get(result["result_download_url"])
            assert downloaded.status_code == 200 and len(downloaded.json()["predictions"]) == 2
            for sample in result["samples"]:
                image = http.get(sample["preview_url"])
                assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
            history = http.get("/api/records")
            assert history.status_code == 200 and any(row["id"] == task_id for row in history.json()["items"])
            assert http.get(f"/api/tasks/{task_id}/bundle").status_code == 404
            evidence["runs"].append({"has_gt": bool(labels), "images": 2, "task_status": result["status"],
                                      "elapsed_seconds": elapsed, "predicted_class_ids": [r["class_id"] for r in result["predictions"]],
                                      "metrics_available": result["metrics"]["available"], "download_ok": True, "history_ok": True})
        with client(lab, lab.peer) as http:
            assert http.get(f"/api/tasks/{task_id}").status_code == 404
            assert http.get(result["result_download_url"]).status_code == 404
    destination = trusted._explicit_cpu_smoke_report or (Path(__file__).resolve().parents[1] / "docs/report/classification-2026-10-28/cpu-http-flow.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
