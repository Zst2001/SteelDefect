"""Real loopback FastAPI private-file GET/HEAD refusal without Docker.

Starts the unchanged application routes with init-only settings, seed disabled,
PCB disabled, and unused temporary SQLite storage. No DB schema creation, Redis,
worker, login, inference, or mocked HTTP is involved. This only proves public
static-file refusal; the true MySQL/worker authorized download check is separate.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def serve(port, temporary):
    import faulthandler
    faulthandler.dump_traceback_later(45, repeat=True)
    print("Private API startup: initializing Windows event loop", flush=True)
    import asyncio
    # Windows asyncio creates its own local socketpair. Initialize only that
    # runtime plumbing before forbidding every application outgoing socket.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    print("Private API startup: event loop ready; installing strict audit guard", flush=True)
    sys.path[:0] = [str(ROOT), str(ROOT / "apps/api"), str(ROOT / "packages"), str(ROOT / "third_party")]
    def guard(event, args):
        if event == "open" and isinstance(args[0], (str, bytes, os.PathLike)):
            name = Path(os.fsdecode(args[0])).name.lower()
            if name == ".env" or name.startswith(".env."):
                raise AssertionError("Private API regression forbids .env reads")
        if event == "socket.connect":
            # The HTTP server only accepts inbound loopback connections. Any
            # outbound access, including Redis or a daily API, is a test failure.
            raise AssertionError("Private API regression forbids outgoing socket connections")
    sys.addaudithook(guard)
    from app import config
    print("Private API startup: settings module imported", flush=True)
    class IsolatedSettings(config.Settings):
        model_config = {**config.Settings.model_config, "env_file": None}
        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, *args, **kwargs):
            return (init_settings,)
    settings = IsolatedSettings(
        mysql_dsn="sqlite:///" + str(Path(temporary) / "unused.sqlite"),
        storage_root=str(Path(temporary) / "private-storage"),
        seed_on_start=False, pcb_segmentation_enabled=False,
        redis_queue_url="redis://127.0.0.1:9/0", redis_cache_url="redis://127.0.0.1:9/1",
        llm_api_key="", dashscope_api_key="", milvus_uri="",
    )
    config.get_settings = lambda: settings
    print("Private API startup: isolated settings installed; importing actual application", flush=True)
    from app.main import app
    print("Private API startup: application routes loaded; starting listener", flush=True)
    import uvicorn
    try:
        faulthandler.cancel_dump_traceback_later()
        loop.run_until_complete(uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False)).serve())
    finally:
        loop.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serve", type=int)
    parser.add_argument("--temporary")
    parser.add_argument("--output", type=Path, default=ROOT / "docs/report/pcb-stage4-closeout-20261030/private-get-api.json")
    args = parser.parse_args()
    if args.serve:
        serve(args.serve, args.temporary)
        return
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("Evidence already exists; use a fresh --output")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="steel-pcb-api-negative-") as tmp:
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        assert port not in (8000, 5173)
        log_path = output.with_name(output.stem + "-server.log")
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen([sys.executable, "-B", __file__, "--serve", str(port), "--temporary", tmp],
                cwd=ROOT, stdout=log, stderr=log, env={**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1"})
            try:
                startup_started = time.monotonic()
                readiness_deadline = startup_started + 180
                while time.monotonic() < readiness_deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Isolated negative-only API exited; see server log")
                    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                    try:
                        connection.request("GET", "/__pcb_private_asset_readiness__")
                        if connection.getresponse().status == 404:
                            break
                    except (OSError, http.client.HTTPException):
                        pass
                    finally:
                        connection.close()
                    time.sleep(0.5)
                else:
                    raise RuntimeError("Isolated negative-only API readiness timeout")
                startup_seconds = time.monotonic() - startup_started
                print(f"Private API ready after {startup_seconds:.2f}s", flush=True)
                script = "import {probePrivateAssets} from './tests/pcb_private_get_probe.mjs'; const r=await probePrivateAssets({origin:process.argv[1],root:process.argv[2],surface:'FastAPI',output:process.argv[3]}); console.log(JSON.stringify({status:r.status,requests:r.requests,failures:r.rows.filter(x=>!x.pass).length}));"
                run = subprocess.run(["node", "--input-type=module", "-e", script, f"http://127.0.0.1:{port}", str(ROOT), str(output)],
                    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=120)
                output.with_name(output.stem + "-execution.log").write_text(run.stdout + run.stderr + f"\nexit_code={run.returncode}\n", encoding="utf-8")
                print(run.stdout)
                if run.returncode:
                    raise RuntimeError("Real API private-file refusal matrix failed")
                report = json.loads(output.read_text(encoding="utf-8"))
                report["environment"] = "Actual FastAPI routes + Uvicorn HTTP; init-only Settings; PCB disabled; seed disabled; no database schema or outgoing sockets; no mocks"
                report["limitation"] = "Public private-file refusal only. Real MySQL/RQ/CPU authorized artifacts remain blocked by Docker Desktop startup and are not replaced by this check."
                report["sqlite_created"] = (Path(tmp) / "unused.sqlite").exists()
                assert report["sqlite_created"] is False
                report["exit_code"] = run.returncode
                report["startup_seconds"] = round(startup_seconds, 2)
                report["startup_and_probe_seconds"] = round(time.monotonic() - startup_started, 2)
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception as exc:
                report = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"surface": "FastAPI", "requests": 0, "rows": []}
                report.update(status="FAIL", error=str(exc), exit_code=1,
                    limitation="No substitute for blocked real MySQL/RQ/browser acceptance; this run did not complete its negative matrix")
                output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
                raise
            finally:
                if process.poll() is None:
                    if os.name == "nt":
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)
                    else:
                        process.terminate()
                    process.wait(timeout=10)
        # The exact Popen-owned process tree is gone before its private tempdir.
        assert process.poll() is not None
    cleanup = {"cleanup": "PASS", "owned_API_process_stopped": True, "owned_temporary_directory_removed": True}
    report = json.loads(output.read_text(encoding="utf-8"))
    report.update(cleanup)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({**cleanup, "report": str(output)}))


if __name__ == "__main__":
    main()
