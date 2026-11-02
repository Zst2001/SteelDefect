"""Real browser -> local HTTP API -> isolated MySQL/RQ -> CPU -> browser.

Fresh disposable Docker containers, loopback-only random ports, synthetic user
and images. No production database, .env, model API, or persistent service.
"""
from datetime import timedelta
import argparse
import io
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import uuid

from check_pcb_infrastructure import ROOT, bootstrap, docker

OUT = ROOT / "docs/report/pcb-stage4-2026-10-29/live-browser"


def child(kind, config_path, port=None):
    print("Isolated process: configuring " + kind, flush=True)
    settings = bootstrap(config_path)
    print("Isolated process: configuration ready", flush=True)
    if kind == "--api":
        import uvicorn
        from app.main import app
        print("Isolated API: starting loopback listener", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=int(port), log_level="warning")
    else:
        from apps.worker.__main__ import main as worker_main
        print("Isolated worker: starting actual Worker entry (imports before queue consumption)", flush=True)
        worker_main()


def main():
    global OUT
    if len(sys.argv) > 1 and sys.argv[1] in {"--api", "--worker"}:
        child(*sys.argv[1:])
        return
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--closeout", action="store_true", help="Run PNG+GT and JPEG U-Net closure acceptance")
    parser.add_argument("--output", type=Path, help="Fresh evidence directory (never overwrite prior results)")
    args = parser.parse_args()
    if args.output:
        OUT = args.output.resolve()
    elif args.closeout:
        OUT = ROOT / "docs/report/pcb-stage4-closeout-20261030/live-browser"
    if (OUT / "results.json").exists():
        raise RuntimeError("Evidence already exists; choose a fresh --output directory")
    OUT.mkdir(parents=True, exist_ok=True)
    label = "steel.pcb.acceptance=" + uuid.uuid4().hex
    owned, processes, logs = [], [], []
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
        for _ in range(90):
            try:
                with pymysql.connect(host="127.0.0.1", port=int(mysql_port), user="root", database="steel_lab_test_pcb", connect_timeout=2):
                    break
            except pymysql.Error:
                time.sleep(1)
        else:
            raise RuntimeError("Isolated browser-test database not ready")
        with tempfile.TemporaryDirectory(prefix="steel-pcb-live-") as tmp:
            cfg = {"mysql_dsn": f"mysql+pymysql://root@127.0.0.1:{mysql_port}/steel_lab_test_pcb?charset=utf8mb4",
                   "redis_queue_url": f"redis://127.0.0.1:{redis_port}/0",
                   "redis_cache_url": f"redis://127.0.0.1:{redis_port}/1", "rq_queue_name": "pcb_live_acceptance",
                   "storage_root": str(Path(tmp) / "private-storage")}
            path = Path(tmp) / "isolated-runtime.json"
            path.write_text(json.dumps(cfg), encoding="utf-8")
            settings = bootstrap(path)
            from app.db.session import Base, engine, SessionLocal
            from app.db.models import User, Session as AuthSession
            from app.util_time import new_id, utcnow
            from infer.pcb.catalog import require_admitted
            from infer.pcb.runtime import ROOT as ASSET_ROOT
            require_admitted()
            Base.metadata.create_all(engine)
            token = new_id()
            credentials = {"username": "PCB真实链路验收", "password": uuid.uuid4().hex}
            peers = {}
            with SessionLocal() as db:
                assert db.query(User).count() == 0
                from app.security import hash_password
                user = User(id=new_id(), username="PCB真实链路验收", password_hash="unused-synthetic-fixture",
                            role="student", status="active")
                if args.closeout:
                    user.password_hash = hash_password(credentials["password"])
                db.add(user)
                db.flush()
                db.add(AuthSession(id=token, user_id=user.id, expires_at=utcnow() + timedelta(hours=1)))
                if args.closeout:
                    for role in ("peer", "advisor"):
                        peer = User(id=new_id(), username="PCB合成权限检查_" + role,
                                    password_hash="unused-synthetic-fixture", role="advisor" if role == "advisor" else "student", status="active")
                        db.add(peer)
                        db.flush()
                        peers[role] = new_id()
                        db.add(AuthSession(id=peers[role], user_id=peer.id, expires_at=utcnow() + timedelta(hours=1)))
                db.commit()
            with socket.socket() as available:
                available.bind(("127.0.0.1", 0))
                api_port = available.getsockname()[1]
            env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"}
            try:
                for kind in ("--api", "--worker"):
                    log = (OUT / f"{kind[2:]}.log").open("w", encoding="utf-8")
                    logs.append(log)
                    child_args = [sys.executable, "-B", __file__, kind, str(path)]
                    if kind == "--api":
                        child_args.append(str(api_port))
                    processes.append(subprocess.Popen(child_args, cwd=ROOT, stdout=log, stderr=log, env=env))
                import http.client
                api_base = f"http://127.0.0.1:{api_port}"
                for _ in range(90):
                    if processes[0].poll() is not None:
                        raise RuntimeError("Isolated HTTP API exited before readiness; see api.log")
                    probe = http.client.HTTPConnection("127.0.0.1", api_port, timeout=2)
                    try:
                        probe.request("GET", "/api/scenes/pcb/segmentation/models")
                        response = probe.getresponse()
                        if response.status == 401:
                            break
                    except (OSError, http.client.HTTPException):
                        pass
                    finally:
                        probe.close()
                    time.sleep(1)
                else:
                    raise RuntimeError("Isolated HTTP API not ready")
                from app.cache import rq_connection
                from rq import Worker
                for _ in range(180):
                    if processes[1].poll() is not None:
                        raise RuntimeError("Isolated Worker exited before readiness; see worker.log")
                    if any(w.name == "lab-worker" and w.get_state() == "idle"
                           for w in Worker.all(connection=rq_connection())):
                        break
                    time.sleep(1)
                else:
                    raise RuntimeError("Isolated Worker not ready to consume jobs")
                print("Isolated API and actual Worker are ready; starting real browser", flush=True)
                if args.closeout:
                    from pcb_closeout_verify import make_inputs
                    inputs = make_inputs(OUT)
                    payload = {"apiBase": api_base, "credentials": credentials, "peers": peers,
                               "cases": inputs, "output": str(OUT)}
                    script = "tests/check_pcb_closeout_frontend.mjs"
                else:
                    import numpy as np
                    from PIL import Image
                    import base64
                    image = np.load(ASSET_ROOT / "reference_vectors/input_220_rgb.npy", allow_pickle=False)
                    stream = io.BytesIO()
                    Image.fromarray(image).save(stream, format="PNG")
                    payload = {"apiBase": api_base, "session": token, "taskIds": [],
                               "imageBase64": base64.b64encode(stream.getvalue()).decode(), "output": str(OUT)}
                    script = "tests/check_pcb_live_frontend.mjs"
                # Session is delivered only through stdin; never a log/argv/report.
                playwright = Path(os.environ["USERPROFILE"]) / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright"
                run = subprocess.run(["node", script, str(playwright)], cwd=ROOT,
                                     input=json.dumps(payload), capture_output=True, text=True, encoding="utf-8",
                                     timeout=420 if args.closeout else 240, env=env)
                (OUT / "browser.log").write_text(run.stdout + run.stderr, encoding="utf-8")
                print(run.stdout)
                if run.returncode:
                    print(run.stderr)
                    raise RuntimeError("Live browser acceptance failed")
                if args.closeout:
                    from pcb_closeout_verify import verify_results
                    summary = verify_results(OUT, settings, SessionLocal)
                    print(json.dumps(summary, ensure_ascii=False))
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        if os.name == "nt":
                            # Windows venv launchers own another Python process.
                            # End only this exact Popen-owned tree, not all Python.
                            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                           capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                        else:
                            process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
                for log in logs:
                    log.close()
                engine.dispose()
    finally:
        for ident in reversed(owned):
            labels = json.loads(docker("inspect", "--format", "{{json .Config.Labels}}", ident))
            key, value = label.split("=", 1)
            if labels.get(key) == value:
                docker("rm", "-f", ident)


if __name__ == "__main__":
    main()
