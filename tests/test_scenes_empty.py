from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.authz import get_current_user
from app.deps import get_db
from app.errors import AppError, app_error_handler
from app.routers.scenes import router

FORBIDDEN = ("miou", "mdice", "map", "f1", "accuracy", "precision", "recall")


@pytest.fixture(autouse=True)
def pcb_disabled_by_default(monkeypatch):
    from app.services import scenes
    monkeypatch.setattr(scenes, "pcb_ready", lambda: False)


def _db():
    yield None


def _user():
    return SimpleNamespace(id="stu-1", role="student", status="active")


def _client(*, signed_in: bool) -> TestClient:
    application = FastAPI()
    application.add_exception_handler(AppError, app_error_handler)
    application.include_router(router, prefix="/api")
    application.dependency_overrides[get_db] = _db
    if signed_in:
        application.dependency_overrides[get_current_user] = _user
    return TestClient(application)


def _assert_no_metrics(payload: dict) -> None:
    text = json.dumps(payload, ensure_ascii=False).lower()
    for token in FORBIDDEN:
        assert token not in text


def test_scenes_require_login() -> None:
    client = _client(signed_in=False)
    for method, path in (
        ("get", "/api/scenes"),
        ("get", "/api/scenes/pcb/detection"),
        ("post", "/api/scenes/solar/detection/tasks"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 401
        assert response.json()["code"] == "UNAUTHENTICATED"


def test_scene_list_marks_pcb_and_solar_detection_empty(monkeypatch) -> None:
    from app.services import scenes
    monkeypatch.setattr(scenes, "classification_ready", lambda: False)
    client = _client(signed_in=True)
    response = client.get("/api/scenes")
    assert response.status_code == 200
    payload = response.json()
    _assert_no_metrics(payload)
    by_id = {row["id"]: row for row in payload["scenes"]}
    assert set(by_id) == {"steel", "pcb", "solar"}
    steel_status = {task["kind"]: task["status"] for task in by_id["steel"]["tasks"]}
    assert steel_status["segmentation"] == "open"
    assert steel_status["eval"] == "open"
    assert steel_status["detection"] == "empty"
    assert steel_status["classification"] == "empty"
    paths = {task["kind"]: task["path"] for task in by_id["steel"]["tasks"]}
    assert paths["segmentation"] == "/inspect/steel/segmentation"
    assert paths["detection"] == "/inspect/steel/detection"
    assert paths["classification"] == "/inspect/steel/classification"
    assert by_id["pcb"]["tasks"][0]["path"] == "/inspect/pcb"
    assert by_id["solar"]["tasks"][0]["path"] == "/inspect/solar"
    assert {task["kind"]: task["status"] for task in by_id["pcb"]["tasks"]} == {"segmentation": "empty", "classification": "empty", "detection": "empty"}
    assert len(by_id["solar"]["tasks"]) == 1
    assert by_id["solar"]["tasks"][0]["kind"] == "detection"
    assert by_id["solar"]["tasks"][0]["status"] == "empty"


def test_only_steel_classification_opens_when_assets_are_ready(monkeypatch) -> None:
    from app.services import scenes
    monkeypatch.setattr(scenes, "classification_ready", lambda: True)
    by_id = {row["id"]: row for row in _client(signed_in=True).get("/api/scenes").json()["scenes"]}
    steel = {row["kind"]: row["status"] for row in by_id["steel"]["tasks"]}
    assert steel["classification"] == "open"
    assert steel["detection"] == "empty"
    assert all(task["status"] == "empty" for task in by_id["pcb"]["tasks"])
    assert len(by_id["solar"]["tasks"]) == 1
    assert by_id["solar"]["tasks"][0]["status"] == "empty"


def test_pcb_segmentation_gate_does_not_open_detection(monkeypatch):
    from app.services import scenes
    monkeypatch.setattr(scenes, "classification_ready", lambda: False)
    monkeypatch.setattr(scenes, "pcb_ready", lambda: True)
    payload = _client(signed_in=True).get("/api/scenes").json()
    _assert_no_metrics(payload)
    pcb = {task["kind"]: task["status"] for task in payload["scenes"][1]["tasks"]}
    assert pcb == {"segmentation": "open", "classification": "empty", "detection": "empty"}
    response = _client(signed_in=True).post("/api/scenes/pcb/detection/tasks")
    assert response.status_code == 409 and response.json()["code"] == "SCENE_EMPTY"


def test_empty_detection_get_has_no_metrics() -> None:
    client = _client(signed_in=True)
    for scene, name in (("pcb", "PCB板"), ("solar", "太阳能电池板")):
        response = client.get(f"/api/scenes/{scene}/detection")
        assert response.status_code == 200
        payload = response.json()
        _assert_no_metrics(payload)
        assert payload == {
            "scene": scene,
            "name": name,
            "task": "detection",
            "status": "empty",
            "runnable": False,
            "message": "缺陷检测尚未接入权重与推理，不能提交任务。",
        }


def test_pcb_classification_gate_is_independent(monkeypatch):
    from app.services import scenes, pcb_classification
    monkeypatch.setattr(scenes, "pcb_ready", lambda: False)
    monkeypatch.setattr(pcb_classification, "catalog_payload", lambda: {"available": True})
    rows = _client(signed_in=True).get("/api/scenes").json()["scenes"][1]["tasks"]
    assert {r["kind"]: r["status"] for r in rows} == {"segmentation": "empty", "classification": "open", "detection": "empty"}
    assert next(r["path"] for r in rows if r["kind"] == "classification") == "/inspect/pcb/classification"


def test_empty_detection_post_is_rejected() -> None:
    client = _client(signed_in=True)
    for scene in ("pcb", "solar"):
        response = client.post(f"/api/scenes/{scene}/detection/tasks")
        assert response.status_code == 409
        body = response.json()
        assert body["code"] == "SCENE_EMPTY"
        assert body["stage"] == "scene"
        _assert_no_metrics(body)


def test_unknown_scene_detection_is_404() -> None:
    client = _client(signed_in=True)
    for method, path in (
        ("get", "/api/scenes/steel/detection"),
        ("post", "/api/scenes/unknown/detection/tasks"),
    ):
        response = getattr(client, method)(path)
        assert response.status_code == 404
        assert response.json()["code"] == "SCENE_NOT_FOUND"
