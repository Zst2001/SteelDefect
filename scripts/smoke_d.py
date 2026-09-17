"""Slice D smoke: student import static fail + optional Docker admit."""

from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import httpx
import torch
import torch.nn as nn

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages")]

BASE = "http://127.0.0.1:8000/api"
FIXTURES = ROOT / "tests" / "fixtures" / "student"


class TinySeg(nn.Module):
    def __init__(self, num_classes: int = 4, in_channels: int = 3, **kwargs):
        super().__init__()
        self.stem = nn.Conv2d(in_channels, 8, kernel_size=3, padding=1)
        self.head = nn.Conv2d(8, num_classes, kernel_size=1)

    def forward(self, x):
        return self.head(torch.relu(self.stem(x)))


def _creds() -> tuple[str, str]:
    user, password = "student", "StudentDev!234"
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("SEED_STUDENT_USERNAME="):
                user = line.split("=", 1)[1].strip()
            if line.startswith("SEED_STUDENT_PASSWORD="):
                password = line.split("=", 1)[1].strip()
    return user, password


def _import(client: httpx.Client, name: str, py_path: Path, pth_bytes: bytes, requires_cuda: bool = False) -> dict:
    files = {
        "py_file": (py_path.name, py_path.read_bytes(), "text/x-python"),
        "pth_file": ("weights.pth", pth_bytes, "application/octet-stream"),
    }
    data = {
        "name": name,
        "entry_symbol": "build_model",
        "num_classes": "4",
        "in_channels": "3",
        "requires_cuda": "true" if requires_cuda else "false",
    }
    response = client.post("/models/import", data=data, files=files, timeout=60.0)
    if response.status_code >= 400:
        raise RuntimeError(f"import failed {response.status_code} {response.text}")
    return response.json()


def main() -> int:
    user, password = _creds()
    buffer = io.BytesIO()
    torch.save({"model_state": TinySeg().state_dict()}, buffer)
    pth_bytes = buffer.getvalue()

    with httpx.Client(base_url=BASE, timeout=60.0, follow_redirects=True) as client:
        health = client.get("/health")
        health.raise_for_status()
        health_body = health.json()
        login = client.post("/auth/login", json={"username": user, "password": password})
        if login.status_code != 200:
            print("login failed", login.status_code, login.text)
            return 1

        blocked = _import(client, "恶意子进程", FIXTURES / "bad_subprocess.py", pth_bytes)
        if blocked.get("status") != "cannot_start" or blocked.get("fail_stage") != "static":
            print("expected static cannot_start", json.dumps(blocked, ensure_ascii=False)[:800])
            return 1

        cuda_blocked = _import(client, "CUDA标记", FIXTURES / "good_tiny.py", pth_bytes, requires_cuda=True)
        if cuda_blocked.get("fail_stage") != "resource":
            print("expected CUDA resource fail", cuda_blocked)
            return 1

        good = _import(client, "TinySeg", FIXTURES / "good_tiny.py", pth_bytes)
        if good.get("fail_stage") == "static":
            print("good model failed static", good)
            return 1

        if health_body.get("docker") and health_body.get("student_image"):
            version_id = good["id"]
            status = good.get("status")
            for _ in range(40):
                if status not in {"uploaded", "checking"}:
                    break
                time.sleep(3)
                card = client.get(f"/models/{version_id}")
                card.raise_for_status()
                good = card.json()
                status = good.get("status")
            if status != "runnable":
                print("docker admit did not reach runnable", json.dumps(good, ensure_ascii=False)[:800])
                return 1
            print("slice D smoke ok", "static_block", blocked["id"], "runnable", version_id)
            return 0

        if good.get("status") == "checking":
            print("slice D smoke ok (image missing, queued checking)", good["id"], "health", health_body)
            return 0
        if good.get("fail_stage") == "resource":
            print("slice D smoke ok (docker/image unavailable)", good.get("fail_message"))
            return 0
        print("slice D smoke unexpected good payload", json.dumps(good, ensure_ascii=False)[:800])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
