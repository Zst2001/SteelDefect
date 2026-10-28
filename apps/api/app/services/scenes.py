"""Scene menu status. PCB and solar detection stay empty until reviewed CPU weights exist."""

from __future__ import annotations

from copy import deepcopy

from app.errors import AppError

EMPTY_MESSAGE = "缺陷检测尚未接入权重与推理，不能提交任务。"

DETECTION_SCENES = ("pcb", "solar")

SCENES: list[dict] = [
    {
        "id": "steel",
        "name": "钢铁",
        "tasks": [
            {"kind": "segmentation", "label": "缺陷分割", "status": "open", "path": "/inspect/steel/segmentation"},
            {"kind": "eval", "label": "正式评测", "status": "open", "path": "/eval/new"},
            {"kind": "detection", "label": "目标检测", "status": "empty", "path": "/inspect/steel/detection"},
            {"kind": "classification", "label": "缺陷分类", "status": "empty", "path": "/inspect/steel/classification"},
        ],
    },
    {
        "id": "pcb",
        "name": "PCB板",
        "tasks": [
            {"kind": "detection", "label": "缺陷检测", "status": "empty", "path": "/inspect/pcb"},
        ],
    },
    {
        "id": "solar",
        "name": "太阳能电池板",
        "tasks": [
            {"kind": "detection", "label": "缺陷检测", "status": "empty", "path": "/inspect/solar"},
        ],
    },
]

_BY_ID = {row["id"]: row for row in SCENES}


def classification_ready() -> bool:
    from infer.classification import catalog
    return any(row.get("available") for row in catalog())


def list_scenes() -> dict:
    scenes = deepcopy(SCENES)
    for task in scenes[0]["tasks"]:
        if task["kind"] == "classification":
            task["status"] = "open" if classification_ready() else "empty"
    return {"scenes": scenes}


def detection_status(scene: str) -> dict:
    if scene not in DETECTION_SCENES:
        raise AppError("场景不存在", code="SCENE_NOT_FOUND", stage="scene", status_code=404)
    row = _BY_ID[scene]
    return {
        "scene": scene,
        "name": row["name"],
        "task": "detection",
        "status": "empty",
        "runnable": False,
        "message": EMPTY_MESSAGE,
    }


def reject_detection_task(scene: str) -> None:
    detection_status(scene)
    raise AppError(EMPTY_MESSAGE, code="SCENE_EMPTY", stage="scene", status_code=409)
