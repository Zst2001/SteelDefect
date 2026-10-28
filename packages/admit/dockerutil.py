from __future__ import annotations

import json
import logging
import hashlib
import uuid
import shutil
import subprocess
from pathlib import Path
from typing import Any

from admit.sanitize import sanitize_text

DEFAULT_IMAGE = "steel-lab-student:cpu"
logger = logging.getLogger(__name__)


def _target_missing(stderr: str | None, name: str) -> bool:
    # Accept only complete Docker diagnostics naming this exact container.
    return (stderr or "").strip() in {
        f"Error: No such object: {name}",
        f"Error: No such container: {name}",
        f"Error response from daemon: No such container: {name}",
    }


def _cleanup(name: str, events: list[dict], *, creation_completed: bool = False) -> bool:
    """Operate only on this invocation's exact name AND ownership label."""
    def call(action, args):
        try:
            result = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=10, check=False)
            events.append({"action": action, "exit": result.returncode})
            return result
        except (OSError, subprocess.TimeoutExpired, UnicodeError) as exc:
            events.append({"action": action, "error": type(exc).__name__})
            return None
    result = call("inspect", ["inspect", name])
    if result is None:
        return False
    if result.returncode:
        missing = _target_missing(result.stderr, name)
        if missing and not creation_completed:
            events.append({"action": "not_found_creation_unconfirmed"})
        return missing and creation_completed
    try:
        state = json.loads(result.stdout)[0]
        labels = state["Config"]["Labels"]
        if not isinstance(labels, dict) or not isinstance(state["State"]["Running"], bool):
            raise ValueError("invalid container state")
        if labels.get("steel.operation") != name:
            events.append({"action": "ownership_mismatch"})
            return False
        if state["State"]["Running"]:
            stopped = call("stop", ["stop", "--time", "2", name])
            if stopped is None or stopped.returncode:
                call("kill", ["kill", name])
        removed = call("rm", ["rm", "--force", name])
        return bool(removed and (removed.returncode == 0 or _target_missing(removed.stderr, name)))
    except (ValueError, KeyError, TypeError, IndexError):
        events.append({"action": "invalid_inspect"})
        return False


class DockerUnavailable(RuntimeError):
    def __init__(self, message: str) -> None:
        super().__init__(message)


def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        proc = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def image_present(image: str) -> bool:
    try:
        proc = subprocess.run(
            ["docker", "image", "inspect", image],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0


def _volume_path(path: Path) -> str:
    return path.resolve().as_posix()


def run_student_container(
    *,
    image: str,
    mode: str,
    in_dir: Path,
    out_dir: Path,
    timeout_sec: int,
    memory: str = "4g",
    cpus: str = "2",
    extra_paths: list[Path] | None = None,
    code_dir: Path | None = None,
    operation_id: str | None = None,
) -> dict[str, Any]:
    if mode not in {"admit", "infer", "perf"}:
        raise DockerUnavailable("未知隔离操作")
    identity = hashlib.sha256((operation_id or mode).encode()).hexdigest()[:12]
    name = f"steel-{mode}-{identity}-{uuid.uuid4().hex}"
    events = [{"action": "start", "container": name, "mode": mode}]
    logger.info("container operation=%s mode=%s container=%s", identity, mode, name)
    if not docker_available():
        logger.error("container not started: daemon unavailable container=%s", name)
        raise DockerUnavailable("当前环境未检测到可用的 Docker，无法隔离检查学生模型。")
    if not image_present(image):
        logger.error("container not started: image unavailable container=%s", name)
        raise DockerUnavailable(
            f"学生隔离镜像 {image} 不存在。请在仓库根目录执行："
            " docker build -f deploy/student.Dockerfile -t steel-lab-student:cpu ."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker",
        "run",
        "--rm",
        "--name", name,
        "--label", f"steel.operation={name}",
        "--network=none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,noexec,nosuid,size=256m",
        "--user",
        "1000:1000",
        "--security-opt",
        "no-new-privileges",
        "--cap-drop",
        "ALL",
        "--memory",
        memory,
        "--cpus",
        cpus,
        "-v",
        f"{_volume_path(in_dir)}:/in:ro",
        "-v",
        f"{_volume_path(out_dir)}:/out",
    ]
    if code_dir is not None and code_dir.is_dir():
        cmd.extend(["-v", f"{_volume_path(code_dir)}:/opt/lab/admit:ro"])
    cmd.extend(
        [
            image,
            mode,
            "--in",
            "/in",
            "--out",
            "/out",
        ]
    )
    error = None
    creation_completed = False
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        # A successful foreground run proves creation finished. Timeout/client failure
        # may race a late daemon-side create, so one negative inspect is insufficient.
        creation_completed = proc.returncode == 0
        events.append({"action": "exit", "exit": proc.returncode})
        log = sanitize_text("\n".join(p for p in (proc.stdout, proc.stderr) if p),
                            extra_paths=extra_paths or [in_dir, out_dir])
        result_path = out_dir / "result.json"
        payload = json.loads(result_path.read_text(encoding="utf-8")) if result_path.is_file() else {
            "ok": False, "fail_stage": "resource",
            "message": log.strip() or f"容器退出码 {proc.returncode} 且未写出 result.json"}
        if not isinstance(payload, dict):
            raise ValueError("invalid result object")
        if proc.returncode and payload.get("ok"):
            payload.update(ok=False, fail_stage="resource", message=f"容器退出码 {proc.returncode}")
    except Exception as exc:
        error = "timeout" if isinstance(exc, subprocess.TimeoutExpired) else type(exc).__name__
        events.append({"action": "failure", "error": error})
    finally:
        released = _cleanup(name, events, creation_completed=creation_completed)
        events.append({"action": "cleanup", "released": released})
        logger.log(logging.INFO if released else logging.ERROR, "container lifecycle %s", json.dumps(events))
    if error or not released:
        message = f"隔离操作失败（{error or 'cleanup'}）；容器 {name}；" + ("已清理" if released else "清理未确认，需按容器 ID 排查")
        raise DockerUnavailable(message)
    payload["docker_exit"] = proc.returncode
    payload["log"] = log[-8000:]
    payload["container_id"] = name
    payload["cleanup_confirmed"] = released
    return payload
