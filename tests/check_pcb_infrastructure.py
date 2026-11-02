"""Opt-in real PCB CPU + MySQL + Redis/RQ acceptance in disposable containers.

Uses cached Docker images only. Never reads .env or connects to the existing
application database/Redis. New containers have no persistent volumes, bind only
loopback on random ports, and are removed by exact owned IDs in finally.
Run: .venv/Scripts/python.exe -B tests/check_pcb_infrastructure.py
"""
from __future__ import annotations

import argparse
from datetime import timedelta
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs/report/pcb-stage4-2026-10-29/infrastructure"
sys.path[:0] = [str(ROOT), str(ROOT / "apps/api"), str(ROOT / "packages"), str(ROOT / "third_party")]


def bootstrap(config_path):
    # This is a generated test-only file, never the repository's environment.
    cfg = json.loads(Path(config_path).read_text(encoding="utf-8"))
    assert cfg["mysql_dsn"].startswith("mysql+pymysql://root@127.0.0.1:")
    assert cfg["mysql_dsn"].endswith("/steel_lab_test_pcb?charset=utf8mb4")
    assert cfg["redis_queue_url"].startswith("redis://127.0.0.1:")
    assert Path(cfg["storage_root"]).name == "private-storage"
    platform.uname()
    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise AssertionError("PCB infrastructure test forbids .env access")
        if event == "socket.connect":
            address = args[1]
            if not isinstance(address, tuple) or address[0] not in {"127.0.0.1", "::1"}:
                raise AssertionError("PCB test forbids external connections")
    sys.addaudithook(guard)
    from app import config
    class IsolatedSettings(config.Settings):
        model_config = {**config.Settings.model_config, "env_file": None}
        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, *args, **kwargs):
            return (init_settings,)
    settings = IsolatedSettings(**cfg, seed_on_start=False, pcb_segmentation_enabled=True,
                                llm_api_key="", dashscope_api_key="", milvus_uri="")
    config.get_settings = lambda: settings
    return settings


def worker(config_path):
    settings = bootstrap(config_path)
    from app.cache import rq_connection
    from rq import Queue, SimpleWorker
    connection = rq_connection()
    worker = SimpleWorker([Queue(settings.rq_queue_name, connection=connection)],
                          connection=connection, name="pcb-isolated-cpu-worker")
    worker.work(burst=True, with_scheduler=False, logging_level="WARNING")


def exercise(config_path):
    settings = bootstrap(config_path)
    from fastapi.testclient import TestClient
    from PIL import Image
    import numpy as np
    from app.db.session import Base, engine, SessionLocal
    from app.db.models import User, Session as AuthSession, Task, Artifact, MetricSet
    from app.main import app
    from app.util_time import new_id, utcnow
    from app.cache import rq_connection
    from rq import Queue
    from rq.job import Job
    from infer.pcb.runtime import MODELS, ROOT as ASSET_ROOT
    # This engine is provably the newly created isolated schema. No migrations
    # or schema changes touch the application's existing MySQL instance.
    Base.metadata.create_all(engine)
    tokens = {}
    with SessionLocal() as db:
        assert db.query(User).count() == 0
        for role in ("owner", "peer", "advisor"):
            user = User(id=new_id(), username=f"pcb_test_{role}", password_hash="unused-test-fixture",
                        role="advisor" if role == "advisor" else "student", status="active")
            db.add(user)
            db.flush()
            token = new_id()
            db.add(AuthSession(id=token, user_id=user.id, expires_at=utcnow() + timedelta(hours=1)))
            tokens[role] = token
        db.commit()
    def png(array):
        stream = io.BytesIO()
        Image.fromarray(array).save(stream, format="PNG")
        return stream.getvalue()
    texture = np.load(ASSET_ROOT / "reference_vectors/input_220_rgb.npy", allow_pickle=False)
    original = png(texture)
    gt = np.zeros((220, 220), dtype=np.uint8)
    gt[70:75, 70:75] = 255
    results = {"status": "RUNNING", "database": "disposable MySQL 8 InnoDB", "queue": "disposable Redis/RQ",
               "real_worker": "separate .venv Python process, RQ SimpleWorker",
               "data": "synthetic texture and artificial GT; not an accuracy experiment", "runs": [],
               "negative_cases": [], "cancellation": "NOT_SUPPORTED: application has no cancellation API; none added"}
    connection = rq_connection()
    queue = Queue(settings.rq_queue_name, connection=connection)
    with TestClient(app) as http:
        # Real session-cookie authentication; no dependency override or fake queue.
        assert http.get("/api/scenes/pcb/segmentation/models").status_code == 401
        http.cookies.set("lab_session", tokens["owner"])
        catalog = http.get("/api/scenes/pcb/segmentation/models")
        assert catalog.status_code == 200, catalog.text
        assert catalog.json()["enabled"] and catalog.json()["available"], catalog.text
        for index, model_id in enumerate(MODELS):
            files = {"file": ("synthetic.png", original, "image/png")}
            if index == 1:
                files["gt"] = ("synthetic-gt.png", png(gt), "image/png")
            uploaded = http.post("/api/scenes/pcb/segmentation/uploads", files=files)
            assert uploaded.status_code == 200, uploaded.text
            body = {"batch_id": uploaded.json()["batch_id"], "model_id": model_id, "include_cam": True}
            created = http.post("/api/scenes/pcb/segmentation/tasks", json=body,
                                headers={"Idempotency-Key": f"real-rq-{model_id}"})
            assert created.status_code == 200, created.text
            task_id = created.json()["id"]
            duplicate = http.post("/api/scenes/pcb/segmentation/tasks", json=body,
                                  headers={"Idempotency-Key": f"real-rq-{model_id}"})
            assert duplicate.status_code == 200 and duplicate.json()["id"] == task_id
            assert queue.count == 1
            before = time.perf_counter()
            process = subprocess.run([sys.executable, "-B", __file__, "--worker", str(config_path)], cwd=ROOT,
                                     capture_output=True, text=True, encoding="utf-8", timeout=180)
            (REPORT / f"worker-{model_id}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
            assert process.returncode == 0, "Isolated Worker process failed; see test log"
            response = http.get(f"/api/tasks/{task_id}")
            assert response.status_code == 200, response.text
            result = response.json()
            assert result["status"] == "success", result.get("error_summary")
            assert result["metrics"]["available"] is (index == 1)
            assert result["cam"]["status"] == "ok", result["cam"]
            assert queue.count == 0
            job = Job.fetch(f"task-{task_id}", connection=connection)
            assert str(job.get_status()).split(".")[-1].lower() == "finished"
            layers = []
            for artifact in result["artifacts"]:
                download = http.get(artifact["url"])
                assert download.status_code == 200, artifact
                if artifact["kind"] != "pcb_result":
                    image = Image.open(io.BytesIO(download.content))
                    assert image.size == (220, 220)
                layers.append(artifact["kind"])
            assert {"origin", "pred_mask", "overlay", "boundary", "probability", "cam"} <= set(layers)
            assert ("gt" in layers) is (index == 1) and ("error" in layers) is (index == 1)
            assert http.get(result["result_download_url"]).status_code == 200
            history = http.get("/api/records?type=pcb_segmentation").json()
            assert any(row["id"] == task_id for row in history["items"])
            for role in ("peer", "advisor"):
                http.cookies.set("lab_session", tokens[role])
                assert http.get(f"/api/tasks/{task_id}").status_code == 404
                assert http.get(result["result_download_url"]).status_code == 404
            http.cookies.set("lab_session", tokens["owner"])
            assert http.get(f"/api/tasks/{task_id}/file/inputs.json").status_code == 404
            assert http.get(f"/api/tasks/{task_id}/bundle").status_code == 404
            with SessionLocal() as db:
                assert db.query(MetricSet).filter_by(task_id=task_id).count() == int(index == 1)
                before_count = db.query(Artifact).filter_by(task_id=task_id).count()
            # Re-delivery of an already successful task is a lifecycle no-op.
            queue.enqueue("apps.worker.jobs.run_pcb_segmentation", task_id,
                          job_id=f"redelivery-{task_id}", job_timeout=120)
            rerun = subprocess.run([sys.executable, "-B", __file__, "--worker", str(config_path)], cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", timeout=60)
            assert rerun.returncode == 0
            with SessionLocal() as db:
                assert db.get(Task, task_id).status == "success"
                assert db.query(Artifact).filter_by(task_id=task_id).count() == before_count
            results["runs"].append({"model": model_id, "status": "success", "has_gt": index == 1,
                                     "cam": result["cam"]["status"], "layers": layers,
                                     "elapsed_with_worker_start_sec": time.perf_counter() - before,
                                     "idempotency": "PASS", "redelivery": "PASS", "private_download": "PASS"})
        # Real negative lifecycle checks, using only the fresh acceptance schema,
        # private queue and task IDs created above. Never change application jobs.
        for case in ("job_timeout", "actor_revoked_while_queued"):
            uploaded = http.post("/api/scenes/pcb/segmentation/uploads",
                                 files={"file": ("synthetic-negative.png", original, "image/png")})
            assert uploaded.status_code == 200, uploaded.text
            created = http.post("/api/scenes/pcb/segmentation/tasks", json={
                "batch_id": uploaded.json()["batch_id"], "model_id": "unet", "include_cam": True},
                headers={"Idempotency-Key": "negative-" + case})
            assert created.status_code == 200, created.text
            task_id = created.json()["id"]
            if case == "job_timeout":
                job = Job.fetch(f"task-{task_id}", connection=connection)
                # Deliberately exercise the actual RQ death penalty, including
                # cold-import time. No fake timeout or direct body invocation.
                job.timeout = 1
                job.save()
            else:
                with SessionLocal() as db:
                    task = db.get(Task, task_id)
                    db.get(User, task.creator_id).status = "disabled"
                    db.commit()
            process = subprocess.run([sys.executable, "-B", __file__, "--worker", str(config_path)], cwd=ROOT,
                                     capture_output=True, text=True, encoding="utf-8", timeout=180)
            (REPORT / f"worker-negative-{case}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
            job = Job.fetch(f"task-{task_id}", connection=connection)
            rq_status = str(job.get_status()).split(".")[-1].lower()
            with SessionLocal() as db:
                task = db.get(Task, task_id)
                app_status = task.status
                artifact_count = db.query(Artifact).filter_by(task_id=task_id).count()
                metric_count = db.query(MetricSet).filter_by(task_id=task_id).count()
                error_summary = task.error_summary
            task_root = settings.storage_path / "tasks" / task_id
            residual_files = sorted(path.relative_to(task_root).as_posix() for path in task_root.rglob("*") if path.is_file())
            clean = residual_files == ["inputs.json"]
            passed = process.returncode == 0 and rq_status == "failed" and app_status == "failed" and artifact_count == metric_count == 0 and clean
            item = {"case": case, "status": "PASS" if passed else "FAIL", "worker_returncode": process.returncode,
                    "rq_status": rq_status, "app_status": app_status, "artifact_count": artifact_count,
                    "metric_count": metric_count, "error_summary": error_summary,
                    "residual_files": residual_files, "cleanup": "PASS" if clean else "FAIL"}
            if case == "job_timeout":
                item["job_timeout_seconds"] = 1
                item["rq_timeout_observed"] = "JobTimeoutException" in (job.exc_info or "")
                if not item["rq_timeout_observed"]:
                    item["status"] = "FAIL"
            else:
                item["actor_rejection_observed"] = bool(error_summary and "TASK_ACTOR_UNAVAILABLE" in error_summary)
                if not item["actor_rejection_observed"]:
                    item["status"] = "FAIL"
            results["negative_cases"].append(item)
            # Preserve failures as evidence before any final assertion.
            (REPORT / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    results["status"] = "PASS" if all(row["status"] == "PASS" for row in results["negative_cases"]) else "FAIL"
    (REPORT / "result.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2))
    engine.dispose()
    assert results["status"] == "PASS", "PCB negative lifecycle acceptance failed; see result.json and negative Worker logs"


def docker(*args):
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout.strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker")
    parser.add_argument("--exercise")
    args = parser.parse_args()
    if args.worker:
        worker(args.worker)
        return
    if args.exercise:
        exercise(args.exercise)
        return
    REPORT.mkdir(parents=True, exist_ok=True)
    owned = []
    label = "steel.pcb.acceptance=" + uuid.uuid4().hex
    try:
        for image, port, extra in (
            ("mysql:8.0", 3306, ["--env", "MYSQL_ALLOW_EMPTY_PASSWORD=yes", "--env", "MYSQL_DATABASE=steel_lab_test_pcb", "--tmpfs", "/var/lib/mysql:rw"]),
            ("redis:7-alpine", 6379, ["--tmpfs", "/data:rw"]),
        ):
            ident = docker("run", "--pull=never", "-d", "--label", label, "--memory", "768m",
                           "-p", f"127.0.0.1::{port}", *extra, image)
            assert len(ident) == 64 and all(c in "0123456789abcdef" for c in ident)
            owned.append(ident)
        mysql_port = json.loads(docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", owned[0]))["3306/tcp"][0]["HostPort"]
        redis_port = json.loads(docker("inspect", "--format", "{{json .NetworkSettings.Ports}}", owned[1]))["6379/tcp"][0]["HostPort"]
        import pymysql
        for attempt in range(90):
            try:
                with pymysql.connect(host="127.0.0.1", port=int(mysql_port), user="root", database="steel_lab_test_pcb", connect_timeout=2):
                    break
            except pymysql.Error:
                time.sleep(1)
        else:
            raise RuntimeError("Isolated MySQL did not become ready")
        with tempfile.TemporaryDirectory(prefix="steel-pcb-acceptance-") as tmp:
            cfg = {"mysql_dsn": f"mysql+pymysql://root@127.0.0.1:{mysql_port}/steel_lab_test_pcb?charset=utf8mb4",
                   "redis_queue_url": f"redis://127.0.0.1:{redis_port}/0",
                   "redis_cache_url": f"redis://127.0.0.1:{redis_port}/1", "rq_queue_name": "pcb_acceptance",
                   "storage_root": str(Path(tmp) / "private-storage")}
            path = Path(tmp) / "isolated-runtime.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            run = subprocess.run([sys.executable, "-B", __file__, "--exercise", str(path)], cwd=ROOT,
                                 capture_output=True, text=True, encoding="utf-8", timeout=600,
                                 env={**os.environ, "PYTHONIOENCODING": "utf-8"})
            (REPORT / "execution.log").write_text(run.stdout + run.stderr, encoding="utf-8")
            print(run.stdout)
            if run.returncode:
                print(run.stderr)
                raise RuntimeError("PCB infrastructure acceptance failed")
    finally:
        for ident in reversed(owned):
            # Inspect exact IDs and ownership label before removing disposable data.
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", ident))
            key, value = label.split("=", 1)
            if labels.get(key) == value:
                docker("rm", "-f", ident)


if __name__ == "__main__":
    main()
