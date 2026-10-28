from __future__ import annotations

from infer.spec import NEU_CLASS_MAP, builtin_sort_key
from sqlalchemy.orm import Session, selectinload

from app.db.models import Model, ModelVersion, PreprocessSpecRow, User
from app.errors import AppError
from app.services.import_model import model_dir, read_report

VIZ_KINDS = ["origin", "pred_color", "overlay", "boundary", "cam", "montage"]


def is_classification_version(db: Session, version: ModelVersion) -> bool:
    spec = db.get(PreprocessSpecRow, version.preprocess_id)
    return bool(spec and spec.dataset == "neu_cls")


def can_view_version(user: User, model: Model, version: ModelVersion) -> bool:
    if model.source == "builtin":
        return True
    if user.role == "advisor":
        return True
    if model.owner_id == user.id:
        return True
    return version.visibility == "shared"


def can_use_version(user: User, model: Model, version: ModelVersion) -> bool:
    """Execution permission; advisor visibility is not permission to run private code."""
    if model.source == "builtin":
        return True
    return model.source == "student" and (
        model.owner_id == user.id or version.visibility == "shared"
    )


def assert_model_role_access(
    user: User, model: Model | None, version: ModelVersion, role: str,
) -> None:
    expected = {"baseline": "builtin", "student_under_test": "student"}
    if role not in expected:
        raise AppError("模型任务角色无效", code="MODEL_ROLE_INVALID", stage="protocol")
    if model is None or model.source != expected[role]:
        code = "NOT_BASELINE" if role == "baseline" else "NOT_STUDENT_MODEL"
        raise AppError("模型来源与任务角色不一致", code=code, stage="protocol")
    if not can_use_version(user, model, version):
        raise AppError("当前无权使用该模型", code="FORBIDDEN", stage="auth", status_code=403)


def assert_model_content_access(user: User, model: Model, version: ModelVersion) -> None:
    """Source advice / check logs only; does not grant source downloads or edits."""
    allowed = model.source == "builtin" or (
        model.source == "student"
        and (model.owner_id == user.id or version.visibility == "shared")
    )
    if not allowed:
        raise AppError("模型不存在", code="NOT_FOUND", stage="auth", status_code=404)


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
        "perf": None,
    }
    from app.services.perf import serialize_perf

    payload["perf"] = serialize_perf(db, version, model)
    if payload["perf"]["param_count"] is not None:
        payload["param_count"] = payload["perf"]["param_count"]
    payload["fps_per_image"] = payload["perf"].get("fps_per_image")
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
        # Classification has its own validated catalog and Bx6 executor.
        # The default model catalog feeds segmentation forms and assistant tools.
        if is_classification_version(db, version):
            continue
        model = version.model
        if can_view_version(user, model, version):
            items.append(serialize_version(db, version, model))
    items.sort(
        key=lambda row: (
            0 if row["source"] == "builtin" else 1,
            builtin_sort_key(row["slug"]) if row["source"] == "builtin" else 0,
            row["name"],
        )
    )
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
