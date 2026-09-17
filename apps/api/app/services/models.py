from __future__ import annotations

from sqlalchemy.orm import Session, selectinload

from app.db.models import Model, ModelVersion, PreprocessSpecRow, User
from app.services.import_model import model_dir, read_report
from infer.spec import NEU_CLASS_MAP

VIZ_KINDS = ["origin", "pred_color", "overlay", "boundary", "montage"]


def can_view_version(user: User, model: Model, version: ModelVersion) -> bool:
    if model.source == "builtin":
        return True
    if user.role == "advisor":
        return True
    if model.owner_id == user.id:
        return True
    return version.visibility == "shared"


def serialize_version(db: Session, version: ModelVersion, model: Model, *, include_report: bool = False) -> dict:
    weight = version.weights[0] if version.weights else None
    spec = db.get(PreprocessSpecRow, version.preprocess_id)
    class_map = NEU_CLASS_MAP if spec and spec.dataset == "neu" else {}
    runnable_here = version.status == "runnable" and not version.requires_cuda
    payload = {
        "id": version.id,
        "model_id": model.id,
        "name": model.name,
        "source": model.source,
        "slug": version.slug,
        "status": version.status,
        "fail_stage": version.fail_stage,
        "fail_message": version.fail_message,
        "task_type": "语义分割",
        "num_classes": version.num_classes,
        "in_channels": version.in_channels,
        "input_size": [version.input_h, version.input_w],
        "class_map": class_map,
        "preprocess_id": version.preprocess_id,
        "preprocess": (
            {
                "id": spec.id,
                "name": spec.name,
                "height": spec.height,
                "width": spec.width,
                "apply_clahe": spec.apply_clahe,
                "sp_threshold": spec.sp_threshold,
                "dataset": spec.dataset,
            }
            if spec
            else None
        ),
        "requires_cuda": version.requires_cuda,
        "runnable_here": runnable_here,
        "visibility": version.visibility,
        "weight_sha256": weight.sha256 if weight else None,
        "param_count": weight.param_count if weight else None,
        "flops": "未测量",
        "metrics_source": "未写入完整测试集指标，不把公开榜单当作本次对照结果",
        "visualizations": VIZ_KINDS,
        "owner_id": model.owner_id,
        "entry_symbol": version.entry_symbol,
        "log_available": False,
        "admit_report": None,
    }
    if include_report and model.source == "student":
        from app.config import get_settings

        settings = get_settings()
        payload["admit_report"] = read_report(settings, version.id)
        payload["log_available"] = (model_dir(settings, version.id) / "admit.log").is_file()
    return payload


def list_visible_versions(db: Session, user: User) -> list[dict]:
    rows = (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model), selectinload(ModelVersion.weights))
        .all()
    )
    items: list[dict] = []
    for version in rows:
        model = version.model
        if can_view_version(user, model, version):
            items.append(serialize_version(db, version, model))
    items.sort(key=lambda row: (0 if row["source"] == "builtin" else 1, row["name"]))
    return items


def group_model_items(items: list[dict], user_id: str) -> dict:
    builtins = [row for row in items if row["source"] == "builtin"]
    mine = [row for row in items if row["source"] == "student" and row.get("owner_id") == user_id]
    shared = [
        row
        for row in items
        if row["source"] == "student" and row.get("visibility") == "shared" and row.get("owner_id") != user_id
    ]
    return {"items": items, "builtins": builtins, "mine": mine, "shared": shared}
