from __future__ import annotations

import hashlib
import json
from pathlib import Path

from admit.ckpt import extract_whitelisted_state, load_checkpoint_file
from admit.scan import format_static_failure, scan_student_source
from sqlalchemy.orm import Session

from app.cache import invalidate_after_write
from app.config import Settings, get_settings
from app.db.models import AuditLog, Model, ModelVersion, User
from app.errors import AppError
from app.services.adapt_ast import (
    LAB_BUILD_NAME,
    PREVIEW_FIRST,
    SourceAnalysis,
    analyze_source,
    apply_patch,
    class_source_unchanged,
    render_adapter_patch,
    source_outside_adapt_unchanged,
)
from app.services.import_model import enqueue_admit, finish_admit_dispatch, model_dir, write_report
from app.services.llm_client import draft_adapt_copy
from app.services.storage import sha256_file
from app.services.submission import lock_user
from app.util_time import new_id, utcnow

KIND_LABELS = {
    "missing_entry": "缺少站点入口",
    "ctor_kwargs": "构造参数与站点契约不一致",
    "multi_output": "多路输出",
    "wrong_variant": "消融变体与权重不一致",
    "opinion_only": "仅意见、不自动改",
    "already_adapted": "已追加过适配层",
}


def _owned_student_version(user: User, version: ModelVersion, model: Model) -> None:
    if model.source != "student" or model.owner_id != user.id:
        raise AppError("模型不存在", code="NOT_FOUND", stage="auth", status_code=404)


def _source_path(settings: Settings, version_id: str) -> Path:
    return model_dir(settings, version_id) / "model.py"


def _read_source(settings: Settings, version: ModelVersion) -> str:
    path = _source_path(settings, version.id)
    if not path.is_file():
        raise AppError("缺少模型源码", code="SOURCE_MISSING", stage="file", status_code=404)
    return path.read_text(encoding="utf-8")


def _checkpoint_model_name(settings: Settings, version: ModelVersion) -> str | None:
    path = model_dir(settings, version.id) / "weights.pth"
    if not path.is_file():
        return None
    try:
        ckpt = load_checkpoint_file(path)
        _, name = extract_whitelisted_state(ckpt)
    except (OSError, ValueError, TypeError, RuntimeError, KeyError):
        return None
    return str(name).strip() if name else None


def _rule_points(analysis: SourceAnalysis, fail_stage: str | None, fail_message: str | None) -> list[str]:
    points: list[str] = []
    if "missing_entry" in analysis.kinds and analysis.target:
        points.append(
            f"源码没有站点入口 `{LAB_BUILD_NAME}` / `build_model`。将在文件末尾追加包装函数，"
            f"内部调用 `{analysis.target.name}`，不改原 class。"
            "若权重里带有 model_name 且源码有注册表，优先包那一个变体，而不是体量最大的统一类。"
        )
    if "ctor_kwargs" in analysis.kinds and analysis.target:
        points.append(
            f"`{analysis.target.name}` 的构造不接收 `in_channels`。"
            "包装函数会接收该参数但丢弃，只传入原类认识的参数（如 num_classes）。"
        )
    if "multi_output" in analysis.kinds:
        points.append(PREVIEW_FIRST + "与检查器同一规则；不删原类辅助头。")
    if "wrong_variant" in analysis.kinds and analysis.target:
        wrapped = analysis.wrapped_class or "当前类"
        hint = analysis.hint_model_name or "未知"
        points.append(
            f"适配层当前实例化 `{wrapped}`，权重 `model_name={hint}` 对应源码里的 `{analysis.target.name}`。"
            "将只替换适配块内的构造目标，不改原 class，不去掉 `module.`，也不改成 strict=False。"
        )
        if fail_message:
            points.append(f"检查器原文：{fail_message[:240]}")
    elif fail_stage == "load":
        points.append(
            "权重加载失败时，不会去掉 `module.` 前缀，也不会改成 strict=False。"
        )
        if fail_message:
            points.append(f"检查器原文：{fail_message[:240]}")
        if fail_message and "module." in fail_message:
            points.append(
                "失败信息里出现 `module.` 前缀，常见于 DataParallel。"
                "不要无条件去掉前缀；若去掉后键集合能完全对齐，可作为后续增强项。"
            )
        if fail_message and ("Unexpected key" in fail_message or "Missing key" in fail_message):
            points.append(
                "若一份源码里有多个消融变体（如 TSFNet / TSFNetBase），"
                "键对不上通常是包错了类，而不是权重损坏。请对照 checkpoint 的 model_name 选对应变体。"
            )
    if fail_stage in {"static", "import", "resource", "file"}:
        if fail_message:
            points.append(f"检查器原文：{fail_message[:400]}")
        if fail_stage == "static":
            points.append(
                "静态扫描失败时不会自动改源码，也不会把被禁模块加入白名单。"
                "请把训练脚本里的外部依赖（例如 compare.*）改成这一份 .py 内的网络结构与 forward，去掉网络/子进程/磁盘/动态执行。"
            )
        else:
            points.append("该阶段失败不在自动追加白名单。请按检查原文自行修改后再传。")
    if fail_stage == "shape":
        points.append("输出形状与声明类别数不一致，可能涉及网络结构，助手不会自动改分类头。")
    if analysis.apply_blocked_reason and not analysis.can_apply and not points:
        points.append(analysis.apply_blocked_reason)
    if not points:
        points.append("当前失败不在自动追加范围，源码不会被改写。")
    return points


def _points_from_llm(text: str | None, fallback: list[str]) -> list[str]:
    if not text:
        return fallback
    lines = []
    for raw in text.splitlines():
        line = raw.strip().lstrip("-*•0123456789.、) ").strip()
        if line:
            lines.append(line)
    return lines[:8] or fallback


def build_proposal(
    db: Session,
    user: User,
    version: ModelVersion,
    model: Model,
    *,
    settings: Settings | None = None,
    use_llm: bool = True,
) -> dict:
    settings = settings or get_settings()
    _owned_student_version(user, version, model)
    source = _read_source(settings, version)
    analysis = analyze_source(
        source,
        entry_symbol=version.entry_symbol or "build_model",
        fail_stage=version.fail_stage,
        fail_message=version.fail_message,
        status=version.status,
        hint_model_name=_checkpoint_model_name(settings, version),
    )
    rule_points = _rule_points(analysis, version.fail_stage, version.fail_message)
    diff = ""
    if analysis.can_apply:
        diff = render_adapter_patch(analysis)
    llm_status = "skipped"
    llm_model = None
    points = rule_points
    if use_llm:
        drafted = draft_adapt_copy(
            {
                "fail_stage": version.fail_stage,
                "fail_message": version.fail_message,
                "kinds": analysis.kinds,
                "target_class": analysis.target.name if analysis.target else None,
                "wrapped_class": analysis.wrapped_class,
                "hint_model_name": analysis.hint_model_name,
                "init_params": [item.name for item in analysis.resolved_params],
                "returns_sequence": analysis.returns_sequence,
                "entry_symbol": version.entry_symbol,
                "preview_note": PREVIEW_FIRST,
                "rule_points": rule_points,
                "can_apply": analysis.can_apply,
                "apply_blocked_reason": analysis.apply_blocked_reason,
            },
            settings=settings,
            can_apply=analysis.can_apply,
        )
        if drafted:
            llm_status = "ok"
            llm_model = settings.llm_model
            points = _points_from_llm(drafted, rule_points)
        elif settings.resolved_llm_api_key:
            llm_status = "error"
    payload = {
        "version_id": version.id,
        "status": version.status,
        "fail_stage": version.fail_stage,
        "fail_message": version.fail_message,
        "kinds": analysis.kinds,
        "kind_labels": [KIND_LABELS.get(kind, kind) for kind in analysis.kinds],
        "primary_kind": analysis.primary_kind,
        "can_apply": analysis.can_apply,
        "apply_blocked_reason": analysis.apply_blocked_reason,
        "target_class": analysis.target.name if analysis.target else None,
        "entry_after": LAB_BUILD_NAME if analysis.can_apply else version.entry_symbol,
        "points": points,
        "rule_points": rule_points,
        "preview_note": PREVIEW_FIRST if analysis.returns_sequence or analysis.can_apply else None,
        "diff": diff,
        "llm_status": llm_status,
        "llm_model": llm_model,
        "consent_hint": (
            "只改适配层，将重跑隔离检查；通过后本版本留在你的模型中心。"
            "检查结果以复检为准，助手不保证可运行。"
            if analysis.can_apply
            else "当前失败不会自动改源码。下面是修改意见；请按意见改这一份 .py 后再传。"
        ),
    }
    return payload


def apply_adapt(
    db: Session,
    user: User,
    version: ModelVersion,
    model: Model,
    *,
    consent: bool,
    settings: Settings | None = None,
) -> dict:
    settings = settings or get_settings()
    lock_user(db, user)
    version = db.query(ModelVersion).filter_by(id=version.id).populate_existing().with_for_update().one()
    _owned_student_version(user, version, model)
    if consent and version.status == "checking":
        return {"applied": False, "declined": False, "status": version.status, "message": "复检已提交，请勿重复适配"}
    proposal = build_proposal(db, user, version, model, settings=settings, use_llm=False)
    if not consent:
        _write_audit(
            db,
            actor_id=user.id,
            action="adapt.decline",
            target_id=version.id,
            reason=_audit_reason(proposal, consent=False),
        )
        db.commit()
        proposal["applied"] = False
        proposal["declined"] = True
        return proposal

    if version.status != "cannot_start":
        raise AppError("仅不能启动的版本可追加适配", code="ADAPT_NOT_ELIGIBLE", stage="build", status_code=400)
    if not proposal["can_apply"] or not proposal["diff"]:
        raise AppError(
            proposal.get("apply_blocked_reason") or "该失败不在自动追加白名单",
            code="ADAPT_NOT_WHITELISTED",
            stage=version.fail_stage or "build",
            status_code=400,
        )

    path = _source_path(settings, version.id)
    original = path.read_text(encoding="utf-8")
    updated = apply_patch(original, proposal["diff"])
    if proposal.get("target_class") and not class_source_unchanged(
        original, updated, proposal["target_class"]
    ):
        raise AppError("适配层不能改动原有 class", code="ADAPT_TOUCHED_CLASS", stage="static", status_code=400)
    if not source_outside_adapt_unchanged(original, updated):
        raise AppError("适配层不能改动标记外的源码", code="ADAPT_TOUCHED_SOURCE", stage="static", status_code=400)

    issues = scan_student_source(updated, filename="model.py")
    if issues:
        raise AppError(format_static_failure(issues), code="ADAPT_STATIC", stage="static", status_code=400)

    path.write_text(updated, encoding="utf-8")
    version.source_sha256 = sha256_file(path)
    version.entry_symbol = LAB_BUILD_NAME
    version.status = "checking"
    version.fail_stage = "queue"
    version.fail_message = "QUEUE_PENDING: 源码已适配，复检尚未确认入队"
    write_report(
        settings,
        version.id,
        {
            "version_id": version.id,
            "status": "checking",
            "fail_stage": None,
            "message": "已追加适配层，排队隔离复检",
            "stages": [{"stage": "file", "ok": True, "message": "已追加适配层并更新哈希"}],
            "adapt": {
                "kinds": proposal["kinds"],
                "target_class": proposal.get("target_class"),
                "patch_sha256": hashlib.sha256(proposal["diff"].encode("utf-8")).hexdigest(),
            },
        },
    )
    _write_json(
        model_dir(settings, version.id) / "adapt_last.json",
        {
            "consent": True,
            "kinds": proposal["kinds"],
            "target_class": proposal.get("target_class"),
            "patch_sha256": hashlib.sha256(proposal["diff"].encode("utf-8")).hexdigest(),
        },
    )
    _write_audit(
        db,
        actor_id=user.id,
        action="adapt.apply",
        target_id=version.id,
        reason=_audit_reason(proposal, consent=True),
    )
    db.commit()
    invalidate_after_write(None, user.id)
    finish_admit_dispatch(db, version, settings, enqueue_admit(version.id, settings))
    proposal["applied"] = True
    proposal["declined"] = False
    proposal["status"] = version.status
    proposal["entry_after"] = version.entry_symbol
    return proposal


def _audit_reason(proposal: dict, *, consent: bool) -> str:
    kinds = ",".join(proposal.get("kinds") or [])
    stage = proposal.get("fail_stage") or "-"
    text = f"consent={'yes' if consent else 'no'} stage={stage} kind={kinds}"
    return text[:255]


def _write_audit(db: Session, *, actor_id: str, action: str, target_id: str, reason: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            actor_id=actor_id,
            action=action,
            target_type="model_version",
            target_id=target_id,
            reason=reason,
            created_at=utcnow(),
        )
    )


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
