from __future__ import annotations

from fastapi import APIRouter, Depends

from app.authz import get_current_user
from app.db.models import User
from app.services.scenes import detection_status, list_scenes, reject_detection_task

router = APIRouter(prefix="/scenes", tags=["scenes"])


@router.get("")
def get_scenes(_user: User = Depends(get_current_user)) -> dict:
    return list_scenes()


@router.get("/{scene}/detection")
def get_scene_detection(scene: str, _user: User = Depends(get_current_user)) -> dict:
    return detection_status(scene)


@router.post("/{scene}/detection/tasks")
def create_scene_detection_task(scene: str, _user: User = Depends(get_current_user)) -> dict:
    reject_detection_task(scene)
    return {}
