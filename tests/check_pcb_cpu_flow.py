"""Explicit three-model CPU HTTP/Worker flow, isolated SQLite and fake queue.

Run with .venv/Scripts/python.exe -B tests/check_pcb_cpu_flow.py.
This is not a real Redis/RQ acceptance. Only trusted PCB weights are restored;
all default runner bans on .env, network and external services remain active.
"""
from pathlib import Path
import io
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
    if args.report and args.report.exists():
        raise RuntimeError("Choose a fresh report to preserve earlier acceptance evidence")
    platform.uname()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packages"))
    import torch
    import infer.pcb.runtime as trusted
    trusted._explicit_cpu_load = torch.load
    trusted._explicit_cpu_report = args.report
    print("EXPLICIT PCB CPU FLOW: all three admitted weights; isolated SQLite/temp storage/fake queue; synthetic inputs, no accuracy claim.")
    namespace = runpy.run_path(str(Path(__file__).with_name("run_phase_a_tests.py")))
    namespace["DEFAULT_TARGETS"].append("tests/check_pcb_cpu_flow.py")
    sys.argv = ["tests/run_phase_a_tests.py", "tests/check_pcb_cpu_flow.py"]
    raise SystemExit(namespace["main"]())

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use this script with its explicit isolation bootstrap")

import numpy as np
from PIL import Image
from app.db.models import MetricSet, Task
from app.routers import pcb_segmentation as router
from app.services import pcb_segmentation as service
from app.services.dispatch import Delivery
from apps.worker import pcb_segmentation as worker, jobs
from infer.pcb.runtime import MODELS
from test_phase_a_authorization import lab, client


def test_real_three_model_pcb_http_flow(lab, monkeypatch):
    import torch
    import infer.pcb.runtime as trusted
    monkeypatch.setattr(torch, "load", trusted._explicit_cpu_load)
    object.__setattr__(lab.settings, "pcb_segmentation_enabled", True)
    object.__setattr__(lab.settings, "pcb_job_timeout_sec", 120)
    monkeypatch.setattr(service, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(service, "invalidate_after_write", lambda *args: None)
    monkeypatch.setattr(worker, "invalidate_after_write", lambda *args: None)
    queued = []
    def enqueue(_settings, function, task_id, timeout, **kwargs):
        assert function == "apps.worker.jobs.run_pcb_segmentation" and timeout == 120
        queued.append(task_id)
        return Delivery("confirmed", f"task-{task_id}")
    monkeypatch.setattr(service, "enqueue", enqueue)
    yy, xx = np.indices((220, 220))
    image = np.stack(((xx * 7 + yy * 3) % 256, (xx * 2 + yy * 11) % 256, (xx * 13 + yy * 5) % 256), axis=2).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(image).save(buf, format="PNG")
    gt = io.BytesIO()
    Image.fromarray(((xx + yy) % 17 == 0).astype(np.uint8)).save(gt, format="PNG")
    evidence = {"scope": "Synthetic trusted CPU HTTP + direct Worker flow; no accuracy/generalization claim; fake queue",
                "runtime": {"torch": torch.__version__, "interop": torch.get_num_interop_threads()}, "runs": []}
    for index, model in enumerate(MODELS):
        has_gt = index == 2
        with client(lab, lab.owner) as http:
            http.app.include_router(router.router, prefix="/api")
            files = {"file": ("synthetic.png", buf.getvalue(), "image/png")}
            if has_gt:
                files["gt"] = ("synthetic-gt.png", gt.getvalue(), "image/png")
            response = http.post("/api/scenes/pcb/segmentation/uploads", files=files)
            assert response.status_code == 200, response.text
            batch_id = response.json()["batch_id"]
            response = http.post("/api/scenes/pcb/segmentation/tasks", json={"batch_id": batch_id, "model_id": model, "include_cam": True},
                                 headers={"Idempotency-Key": "pcb-real-cpu-" + model})
            assert response.status_code == 200, response.text
            task_id = response.json()["id"]
            assert task_id in queued
            start = time.perf_counter()
            jobs.run_pcb_segmentation(task_id)
            elapsed = time.perf_counter() - start
            lab.db.expire_all()
            response = http.get(f"/api/tasks/{task_id}")
            assert response.status_code == 200, response.text
            data = response.json()
            assert data["status"] == "success", data
            assert data["model"]["id"] == model and data["metrics"]["available"] is has_gt
            assert lab.db.query(MetricSet).filter_by(task_id=task_id).count() == int(has_gt)
            for artifact in data["artifacts"]:
                response = http.get(artifact["url"])
                assert response.status_code == 200, artifact
                if artifact["kind"] != "pcb_result":
                    with Image.open(io.BytesIO(response.content)) as result_image:
                        assert result_image.size == (220, 220)
            history = http.get("/api/records?type=pcb_segmentation").json()
            assert any(row["id"] == task_id for row in history["items"])
            result = http.get(data["result_download_url"]).json()
            assert result["weight_sha256"] == MODELS[model][0]
            assert result["deployment_source_hash"]
            assert http.get(f"/api/tasks/{task_id}/file/inputs.json").status_code == 404
            evidence["runs"].append({"model_id": model, "status": data["status"], "elapsed_seconds": elapsed,
                                     "cam": data["cam"], "has_gt": has_gt, "metric_available": data["metrics"]["available"],
                                     "artifact_kinds": [row["kind"] for row in data["artifacts"]],
                                     "foreground_pixels": result["foreground_pixels"], "download_ok": True, "history_ok": True})
        for actor in (lab.peer, lab.advisor):
            with client(lab, actor) as http:
                assert http.get(f"/api/tasks/{task_id}").status_code == 404
                assert http.get(data["result_download_url"]).status_code == 404
    destination = trusted._explicit_cpu_report or (Path(__file__).resolve().parents[1] / "docs/report/pcb-stage4-2026-10-29/cpu-http-flow.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
