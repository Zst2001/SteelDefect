"""Opt-in real steel U-Net regression in temporary SQLite with a fake queue.

Only the audited builtin and prediction are restored in the offline runner.
Checkpoint deserialization is locally replaced with a fixed-hash, weights-only
reader; production loading semantics are unchanged. Synthetic inputs/GT are
contract fixtures, never official NEU-20 evaluation or accuracy evidence.
"""
from pathlib import Path
import hashlib
import io
import json
import platform
import runpy
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
WEIGHT_SHA256 = "d7b43b61db9d226ffec3ffce0fa3ee4c255def4935c7c843a66b2d8b881064fe"

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "docs/report/pcb-stage4-2026-10-29/legacy-steel-cpu.json")
    args = parser.parse_args()
    platform.uname()
    sys.path.insert(0, str(ROOT / "packages"))
    import torch
    from infer import engine
    engine._regression_get_builtin = engine.get_builtin_module
    engine._regression_predict = engine.predict_mask
    engine._regression_safe_load = torch.load
    engine._regression_report = args.report
    namespace = runpy.run_path(str(Path(__file__).with_name("run_phase_a_tests.py")))
    namespace["DEFAULT_TARGETS"].append("tests/check_steel_cpu_regression.py")
    sys.argv = ["tests/run_phase_a_tests.py", "tests/check_steel_cpu_regression.py"]
    raise SystemExit(namespace["main"]())

if "app.config" not in sys.modules or sys.modules["app.config"].Settings.__name__ != "OfflineSettings":
    raise RuntimeError("Use the explicit isolation bootstrap")

import numpy as np
from PIL import Image
from app.db.models import Dataset, DatasetVersion, Sample, Weight, Task, MetricSet, Artifact
from app.routers import uploads, demo as demo_router
from app.services import demo, tasks
from app.services.dispatch import Delivery
from app.util_time import new_id
from apps.worker import jobs
from infer import engine
from test_phase_a_authorization import lab, client


def png(array):
    out = io.BytesIO()
    Image.fromarray(array).save(out, format="PNG")
    return out.getvalue()


def test_real_steel_compare_and_demo_cpu(lab, monkeypatch):
    import torch
    weight_path = (ROOT / "assets/baselines/neu/best_unet.pth").resolve()
    def safe_checkpoint(path):
        path = Path(path).resolve()
        assert path == weight_path
        with path.open("rb") as stream:
            digest = hashlib.sha256()
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
            assert digest.hexdigest() == WEIGHT_SHA256
            stream.seek(0)
            # No fallback, safe-global allowlist, or pickle execution is enabled.
            return engine._regression_safe_load(stream, map_location="cpu", weights_only=True)
    monkeypatch.setattr(engine, "load_checkpoint_file", safe_checkpoint)
    monkeypatch.setattr(jobs, "get_builtin_module", engine._regression_get_builtin)
    monkeypatch.setattr(jobs, "predict_mask", engine._regression_predict)
    monkeypatch.setattr(uploads, "get_settings", lambda: lab.settings)
    monkeypatch.setattr(demo_router, "assert_demo_submit_rate", lambda *_: None)
    monkeypatch.setattr(demo, "invalidate_after_write", lambda *_: None)
    queued = []
    def enqueue(_settings, function, task_id, timeout):
        assert function in {"apps.worker.jobs.run_compare", "apps.worker.jobs.run_demo"}
        queued.append(task_id)
        return Delivery("confirmed", f"task-{task_id}")
    monkeypatch.setattr(tasks, "_enqueue_task", enqueue)
    monkeypatch.setattr(demo, "_enqueue_task", enqueue)
    lab.spec.apply_clahe = True
    lab.db.add(Weight(id=new_id(), version_id=lab.builtin.id, file_uri="asset:baselines/neu/best_unet.pth", sha256=WEIGHT_SHA256))
    lab.db.commit()
    rng = np.random.RandomState(20261029)
    image = rng.randint(30, 200, (200, 200, 3), dtype=np.uint8)
    original = png(image)
    gt = np.zeros((200, 200), dtype=np.uint8)
    gt[40:70, 40:70] = 1
    gt[100:120, 100:120] = 2
    gt[150:160, 100:160] = 3
    evidence = {"status": "RUNNING", "model": "steel builtin UNet", "weight_sha256": WEIGHT_SHA256,
        "scope": "real CPU inference; temporary SQLite/private storage; fake queue; HTTP dependency auth fixtures",
        "loading": "test-only fixed-hash weights_only=True reader + existing strict builder; production loader unchanged",
        "data": "synthetic input and GT; not accuracy evaluation; official NEU-20 untouched", "runs": []}
    threads = torch.get_num_threads()
    torch.set_num_threads(2)
    try:
        for mode in ("compare_no_gt", "compare_gt", "demo"):
            with client(lab, lab.owner) as http:
                http.app.include_router(uploads.router, prefix="/api")
                if mode != "demo":
                    uploaded = http.post("/api/uploads/images", files=[("files", ("synthetic.png", original, "image/png"))])
                    assert uploaded.status_code == 200, uploaded.text
                    batch_id = uploaded.json()["batch_id"]
                    if mode == "compare_gt":
                        uploaded_gt = http.post("/api/uploads/masks", data={"batch_id": batch_id},
                            files=[("files", ("synthetic.png", png(gt), "image/png"))])
                        assert uploaded_gt.status_code == 200, uploaded_gt.text
                    response = http.post("/api/tasks/compare", json={"batch_id": batch_id, "baseline_version_ids": [lab.builtin.id]},
                                         headers={"Idempotency-Key": mode})
                else:
                    # Private test-only catalog fixtures. Nothing is added to the actual demo library.
                    dataset = Dataset(id=new_id(), owner_id=None, name="synthetic-only-demo", visibility="public")
                    version = DatasetVersion(id=new_id(), dataset_id=dataset.id, kind="demo_samples",
                        class_map_json={}, preprocess_id=lab.spec.id, is_fixed_test=False, forbid_student_gt_download=True)
                    lab.db.add_all([dataset, version])
                    lab.db.flush()
                    (lab.tmp / "synthetic-demo.png").write_bytes(original)
                    lab.db.add(Sample(id=new_id(), version_id=version.id, sample_key="synthetic",
                        origin_uri="data:synthetic-demo.png", mask_uri=None, width=200, height=200,
                        sha256=hashlib.sha256(original).hexdigest()))
                    lab.db.commit()
                    response = http.post("/api/demo/tasks", json={"sample_keys": ["synthetic"], "baseline_version_ids": [lab.builtin.id]},
                                         headers={"Idempotency-Key": mode})
                assert response.status_code == 200, response.text
                task_id = response.json()["id"]
                assert task_id in queued
                start = time.perf_counter()
                (jobs.run_demo if mode == "demo" else jobs.run_compare)(task_id)
                elapsed = time.perf_counter() - start
                lab.db.expire_all()
                route = f"/api/demo/tasks/{task_id}" if mode == "demo" else f"/api/tasks/{task_id}"
                result = http.get(route)
                assert result.status_code == 200, result.text
                result = result.json()
                assert result["status"] == "success", result
                count = lab.db.query(MetricSet).filter_by(task_id=task_id).count()
                assert count == int(mode == "compare_gt")
                if mode == "demo":
                    assert demo.payload_has_no_metric_fields(result)
                    assert not lab.db.get(Task, task_id).has_gt
                    assert not (lab.tmp / "tasks" / task_id / "metrics.json").exists()
                else:
                    metric_response = http.get(f"/api/tasks/{task_id}/metrics")
                    assert metric_response.status_code == 200
                    assert metric_response.json()["available"] is (mode == "compare_gt")
                artifacts = lab.db.query(Artifact).filter_by(task_id=task_id).all()
                kinds = {a.kind for a in artifacts}
                assert {"origin", "pred_color", "overlay", "boundary"} <= kinds
                assert ("gt" in kinds) is (mode == "compare_gt")
                downloaded = 0
                for artifact in artifacts:
                    if artifact.kind in {"origin", "pred_color", "overlay", "boundary", "gt", "error"}:
                        response = http.get(route + "/file/" + artifact.rel_path)
                        assert response.status_code == 200, artifact.rel_path
                        assert Image.open(io.BytesIO(response.content)).size == (200, 200)
                        downloaded += 1
                assert http.get(route + "/bundle").status_code == 200
                evidence["runs"].append({"mode": mode, "status": "success", "elapsed_seconds": elapsed,
                    "metric_rows": count, "downloaded_layers": downloaded, "bundle_download": "PASS",
                    "kind_set": sorted(kinds)})
            if mode != "demo":
                with client(lab, lab.peer) as http:
                    assert http.get(f"/api/tasks/{task_id}").status_code == 404
                    assert http.get(f"/api/tasks/{task_id}/bundle").status_code == 404
        evidence["status"] = "PASS"
        evidence["safety"] = {"env_read": False, "network": False, "student_execution": False,
                              "production_data_modified": False, "unsafe_pickle": False}
        engine._regression_report.parent.mkdir(parents=True, exist_ok=True)
        engine._regression_report.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    finally:
        torch.set_num_threads(threads)
        engine.drop_l1()
