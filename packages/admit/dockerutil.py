from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from admit.sanitize import sanitize_text

DEFAULT_IMAGE = "steel-lab-student:cpu"


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
) -> dict[str, Any]:
    if not docker_available():
        raise DockerUnavailable("当前环境未检测到可用的 Docker，无法隔离检查学生模型。")
    if not image_present(image):
        raise DockerUnavailable(
            f"学生隔离镜像 {image} 不存在。请在仓库根目录执行："
            " docker build -f deploy/student.Dockerfile -t steel-lab-student:cpu ."
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        "docker",
        "run",
        "--rm",
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
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
    except subprocess.TimeoutExpired as exc:
        raise DockerUnavailable(f"隔离检查超时（{timeout_sec}s）") from exc
    log = sanitize_text(
        "\n".join(part for part in (proc.stdout, proc.stderr) if part),
        extra_paths=extra_paths or [in_dir, out_dir],
    )
    result_path = out_dir / "result.json"
    if result_path.is_file():
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    else:
        payload = {
            "ok": False,
            "fail_stage": "resource",
            "message": log.strip() or f"容器退出码 {proc.returncode} 且未写出 result.json",
        }
    payload["docker_exit"] = proc.returncode
    payload["log"] = log[-8000:]
    return payload
