"""H6 smoke: AC-10～AC-13 against a running API + Worker.

Clears local `lab:demo:*` quota keys so the 24h guest window can be re-checked.
Does not change HomeView or compare/eval protocols.
"""

from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "apps" / "api"), str(ROOT / "packages")]

BASE = "http://127.0.0.1:8000/api"
BANNED = ("miou", "mdice", "m_iou", "metric_set", "metrics.json")


def _env(prefix: str) -> tuple[str, str]:
    user_key = f"SEED_{prefix}_USERNAME="
    pass_key = f"SEED_{prefix}_PASSWORD="
    username = "advisor" if prefix == "ADVISOR" else "student"
    password = "AdvisorDev!234" if prefix == "ADVISOR" else "StudentDev!234"
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith(user_key):
                username = line.split("=", 1)[1].strip()
            if line.startswith(pass_key):
                password = line.split("=", 1)[1].strip()
    return username, password


def _client() -> httpx.Client:
    return httpx.Client(base_url=BASE, timeout=120.0, follow_redirects=True, trust_env=False)


def _flush_demo_quota() -> None:
    from app.cache import cache_redis

    redis = cache_redis()
    removed = 0
    for pattern in ("lab:demo:ip:*", "lab:demo:sid:*", "lab:demo:submit:*"):
        for key in redis.scan_iter(match=pattern, count=200):
            redis.delete(key)
            removed += 1
    print("flushed demo quota keys", removed)


def _fail(message: str, response: httpx.Response | None = None) -> int:
    extra = ""
    if response is not None:
        extra = f" {response.status_code} {response.text[:400]}"
    print(message + extra)
    return 1


def _no_metrics(payload: object, label: str) -> str | None:
    blob = json.dumps(payload, ensure_ascii=False).lower()
    for token in BANNED:
        if token in blob:
            return f"{label} leaked {token}"
    return None


def _login(client: httpx.Client, username: str, password: str) -> httpx.Response:
    return client.post("/auth/login", json={"username": username, "password": password})


def _wait_demo(client: httpx.Client, task_id: str) -> dict | None:
    deadline = time.time() + 600
    body: dict = {}
    while time.time() < deadline:
        response = client.get(f"/demo/tasks/{task_id}")
        if response.status_code != 200:
            print("demo poll failed", response.status_code, response.text[:300])
            return None
        body = response.json()
        status = body.get("status")
        print("demo status", status)
        if status in {"success", "partial_success", "failed"}:
            return body
        time.sleep(3)
    print("demo timeout", body.get("status"))
    return None


def main() -> int:
    advisor_user, advisor_pass = _env("ADVISOR")
    student_user, student_pass = _env("STUDENT")

    try:
        _flush_demo_quota()
    except Exception as exc:
        print("quota flush failed (is Redis up?)", exc)
        return 1

    guest = _client()
    other = _client()
    advisor = _client()
    student = _client()
    try:
        health = guest.get("/health")
        if health.status_code != 200:
            return _fail("health failed", health)
        print("health", health.json())

        registered = guest.post("/auth/register", json={"username": "h6intruder", "password": "NopeNope!234"})
        if registered.status_code != 403 or registered.json().get("code") != "REGISTER_DISABLED":
            return _fail("AC-13 register should be 403 REGISTER_DISABLED", registered)
        print("AC-13 register disabled")

        login = _login(advisor, advisor_user, advisor_pass)
        if login.status_code != 200:
            return _fail("advisor login failed", login)
        stamp = str(int(time.time()))[-8:]
        new_name = f"h6s{stamp}"
        created = advisor.post(
            "/admin/users",
            json={"username": new_name, "password": "H6smoke!234", "reason": "H6 AC-13"},
        )
        if created.status_code != 200:
            return _fail("AC-13 advisor provision failed", created)
        provisioned = created.json()
        newbie = _client()
        try:
            entered = _login(newbie, new_name, "H6smoke!234")
            if entered.status_code != 200 or entered.json().get("role") != "student":
                return _fail("AC-13 provisioned student cannot login", entered)
            me = newbie.get("/auth/me")
            if me.status_code != 200:
                return _fail("AC-13 /auth/me failed", me)
        finally:
            newbie.close()
        stopped = advisor.patch(
            f"/admin/users/{provisioned['id']}",
            json={"status": "disabled", "reason": "H6 smoke cleanup"},
        )
        if stopped.status_code != 200 or stopped.json().get("status") != "disabled":
            return _fail("AC-13 disable student failed", stopped)
        print("AC-13 advisor provision + login + disable ok", new_name)

        catalog = guest.get("/demo/samples")
        if catalog.status_code != 200:
            return _fail("AC-10 catalog failed", catalog)
        samples = catalog.json()
        leak = _no_metrics(samples, "catalog")
        if leak:
            print("AC-10", leak)
            return 1
        items = samples.get("items") or []
        if len(items) != 20:
            print("AC-10 expected 20 demo samples", len(items))
            return 1
        if any("mask" in row or "gt" in row for row in items):
            print("AC-10 catalog leaked GT fields")
            return 1
        listed = guest.get("/demo/models")
        if listed.status_code != 200:
            return _fail("AC-10 models failed", listed)
        models = listed.json().get("items") or []
        if len(models) != 3:
            print("AC-12 expected 3 builtins", models)
            return 1
        sample_key = items[0]["sample_key"]
        model_id = models[0]["id"]
        print("AC-10 catalog ok", sample_key, models[0].get("slug"))

        uploaded = guest.post("/uploads/images", files=[("files", ("x.png", b"not-an-image", "image/png"))])
        if uploaded.status_code != 401:
            return _fail("AC-12 guest upload should be 401", uploaded)
        compare = guest.post(
            "/tasks/compare",
            json={"batch_id": "nope", "baseline_version_ids": [model_id], "student_version_id": None},
        )
        if compare.status_code != 401:
            return _fail("AC-12 guest compare should be 401", compare)
        unknown = guest.post("/demo/tasks", json={"sample_keys": ["not-a-sample"], "baseline_version_ids": [model_id]})
        if unknown.status_code != 400 or unknown.json().get("code") not in {"SAMPLE_NOT_FOUND", "SAMPLE_COUNT"}:
            return _fail("AC-12 unknown sample should fail", unknown)
        forbidden = guest.post(
            "/demo/tasks",
            json={"sample_keys": [sample_key], "baseline_version_ids": ["00000000-0000-0000-0000-000000000000"]},
        )
        if forbidden.status_code not in {400, 404}:
            return _fail("AC-12 bogus model should fail", forbidden)
        print("AC-12 guest upload/compare/sample/model blocked")

        first = guest.post("/demo/tasks", json={"sample_keys": [sample_key], "baseline_version_ids": [model_id]})
        if first.status_code != 200:
            return _fail("AC-10 enqueue failed", first)
        task = first.json()
        leak = _no_metrics(task, "enqueue")
        if leak:
            print("AC-10", leak)
            return 1
        task_id = task["id"]
        done = _wait_demo(guest, task_id)
        if done is None or done.get("status") not in {"success", "partial_success"}:
            print("AC-10 demo did not succeed")
            return 1
        leak = _no_metrics(done, "result")
        if leak:
            print("AC-10", leak)
            return 1
        guest_metrics = guest.get(f"/tasks/{task_id}/metrics")
        if guest_metrics.status_code != 401:
            return _fail("AC-10 guest /metrics should be 401", guest_metrics)
        advisor_metrics = advisor.get(f"/tasks/{task_id}/metrics")
        if advisor_metrics.status_code != 404 or advisor_metrics.json().get("code") != "DEMO_NO_METRICS":
            return _fail("AC-10 advisor /metrics should be DEMO_NO_METRICS", advisor_metrics)
        bundle = guest.get(f"/demo/tasks/{task_id}/bundle")
        if bundle.status_code != 200:
            return _fail("AC-10 bundle missing", bundle)
        with zipfile.ZipFile(io.BytesIO(bundle.content)) as zf:
            names = zf.namelist()
        if any(name.lower().endswith("metrics.json") or name.lower().endswith(".pdf") for name in names):
            print("AC-10 bundle contains metrics.json or pdf", names)
            return 1
        print("AC-10 demo ok", task_id, "files", len(names))

        for index in range(2):
            more = guest.post("/demo/tasks", json={"sample_keys": [sample_key], "baseline_version_ids": [model_id]})
            if more.status_code != 200:
                return _fail(f"AC-11 enqueue {index + 2} failed", more)
            print("AC-11 queued", more.json()["id"])
        fourth = guest.post("/demo/tasks", json={"sample_keys": [sample_key], "baseline_version_ids": [model_id]})
        if fourth.status_code != 429 or fourth.json().get("code") != "DEMO_QUOTA":
            return _fail("AC-11 fourth enqueue should be DEMO_QUOTA", fourth)
        if "明日再试或登录" not in fourth.json().get("message", ""):
            return _fail("AC-11 quota message missing 明日再试或登录", fourth)
        fresh = other.post("/demo/tasks", json={"sample_keys": [sample_key], "baseline_version_ids": [model_id]})
        if fresh.status_code != 429 or fresh.json().get("code") != "DEMO_QUOTA":
            return _fail("AC-11 new sid same IP should still be DEMO_QUOTA", fresh)

        signed = _login(student, student_user, student_pass)
        if signed.status_code != 200:
            return _fail("student login failed", signed)
        skipped = student.post("/demo/tasks", json={"sample_keys": [sample_key], "baseline_version_ids": [model_id]})
        if skipped.status_code != 200:
            return _fail("AC-11 logged-in demo should skip guest quota", skipped)
        print("AC-11 quota + login skip ok", skipped.json()["id"])
        return 0
    finally:
        guest.close()
        other.close()
        advisor.close()
        student.close()


if __name__ == "__main__":
    raise SystemExit(main())
