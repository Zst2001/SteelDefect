from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

from sqlalchemy import exists, or_
from sqlalchemy.orm import Session, selectinload

from app.config import Settings, get_settings
from app.db.models import (
    AssistantSession,
    AssistantTurn,
    AuditLog,
    CatalogModel,
    Dataset,
    DatasetVersion,
    Model,
    ModelVersion,
    Sample,
    Task,
    User,
)
from app.errors import AppError
from app.services.assistant_kb import retrieve_kb
from app.services.llm_client import (
    analyze_messages,
    code_messages,
    draft_analyze_copy,
    draft_code_advice,
    draft_kb_copy,
    iter_chat_completion,
    kb_messages,
)
from app.services.models import assert_model_content_access, can_view_version
from app.services.perf import request_measure, serialize_perf
from app.services.records import serialize_record
from app.services.tasks import (
    DEMO_CATALOG_KIND,
    TASK_TYPE_LABELS,
    _resolve_runnable_models,
    create_compare_task,
    serialize_metrics,
    serialize_task,
)
from app.util_time import new_id, utcnow

DONE = {"success", "partial_success"}
LAB_TYPES = {"compare", "eval"}
OPEN_SPECIALTIES = frozenset({"academic", "segment", "model"})
TOOLS_BY_SPECIALTY = {
    "academic": frozenset({"kb.retrieve", "kb.answer"}),
    "segment": frozenset({"task.analyze", "infer.run"}),
    "model": frozenset({"perf.measure", "code.advise"}),
}
VIZ_KINDS = ("montage", "overlay", "pred", "pred_color", "error", "cam", "boundary")
FPS_DISCLAIMER = "本机 CPU、batch=1、dummy 随机输入的前向。FPS = 1000 / ms/图。不是 CUDA 论文测速，也不是测试集指标。"
SOURCE_LIMIT = 6000
FOLLOW_HINTS = ("刚才", "展开", "上面", "那条", "继续", "再说", "详细")
_ANAPHORA = ("它", "这篇", "这个", "那个", "上述")
_CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
_HIT_INDEX = re.compile(r"第\s*([0-9]{1,2}|[一二三四五六七八九十])\s*条")


def llm_ready(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return bool(settings.resolved_llm_api_key)


def _iso(value) -> str | None:
    return value.isoformat() + "Z" if value else None


def _kb_audit_reason(
    query: str,
    hits: list[dict[str, Any]],
    *,
    via: str,
    elapsed_ms: int,
    rewritten: bool = False,
) -> str:
    file_ids: list[str] = []
    for item in hits:
        file_id = str(item.get("file_id") or item.get("slug") or "").strip()
        if file_id and file_id not in file_ids:
            file_ids.append(file_id)
    files = ",".join(file_ids) if file_ids else "-"
    via_text = (via or "none").strip() or "none"
    ms = max(int(elapsed_ms or 0), 0)
    mark = " rewritten=1" if rewritten else ""
    tail = f" hit={len(hits)} via={via_text} files={files} ms={ms}{mark}"
    asked = " ".join((query or "").split())
    room = 255 - len("q=") - len(tail)
    if room < 1:
        files = (files[:60] + "…") if len(files) > 60 else files
        tail = f" hit={len(hits)} via={via_text} files={files} ms={ms}{mark}"
        room = max(255 - len("q=") - len(tail), 0)
    if len(asked) > room:
        asked = (asked[: max(room - 1, 0)] + "…") if room else ""
    return f"q={asked}{tail}"[:255]


def _write_audit(db: Session, *, actor_id: str, action: str, target_id: str, reason: str) -> None:
    db.add(
        AuditLog(
            id=new_id(),
            actor_id=actor_id,
            action=action,
            target_type="assistant",
            target_id=target_id,
            reason=reason,
            created_at=utcnow(),
        )
    )


def can_analyze_task(task: Task, user: User) -> bool:
    if task.type not in LAB_TYPES:
        return False
    if task.creator_id == user.id:
        return True
    if user.role == "advisor" and task.submitted_to_advisor_at is not None:
        return True
    return False


def _load_task(db: Session, task_id: str) -> Task | None:
    return (
        db.query(Task)
        .options(
            selectinload(Task.models),
            selectinload(Task.samples),
            selectinload(Task.artifacts),
            selectinload(Task.metric_set),
        )
        .filter(Task.id == task_id)
        .one_or_none()
    )


def get_analyzable_task(db: Session, task_id: str, user: User) -> Task:
    task = _load_task(db, task_id)
    if task is None:
        raise AppError("任务不存在", code="NOT_FOUND", stage="auth", status_code=404)
    if task.type == "demo":
        raise AppError("公开演示不能作为正式分析", code="DEMO_NO_ANALYZE", stage="protocol", status_code=400)
    if task.type not in LAB_TYPES:
        raise AppError("只能分析对比或正式评测", code="BAD_TYPE", stage="protocol", status_code=400)
    if not can_analyze_task(task, user):
        raise AppError("任务不存在", code="NOT_FOUND", stage="auth", status_code=404)
    if task.status not in DONE:
        raise AppError("请等待任务成功或部分成功后再分析", code="NOT_READY", stage="protocol", status_code=400)
    return task


def list_analyzable_tasks(db: Session, user: User) -> dict:
    query = db.query(Task).options(selectinload(Task.samples), selectinload(Task.models)).filter(
        Task.type.in_(tuple(LAB_TYPES)),
        Task.status.in_(tuple(DONE)),
    )
    if user.role == "advisor":
        query = query.filter(or_(Task.creator_id == user.id, Task.submitted_to_advisor_at.isnot(None)))
    else:
        query = query.filter(Task.creator_id == user.id)
    rows = query.order_by(Task.created_at.desc()).limit(100).all()
    return {
        "llm_ready": llm_ready(),
        "open_specialties": sorted(OPEN_SPECIALTIES),
        "items": [serialize_record(db, row, user) for row in rows],
    }


def _viz_links(artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    links = []
    for item in artifacts:
        if item.get("kind") in VIZ_KINDS:
            links.append(
                {
                    "kind": item.get("kind"),
                    "sample_key": item.get("sample_key"),
                    "model_version_id": item.get("model_version_id"),
                    "url": item.get("url"),
                    "grade": "measurement",
                }
            )
    return links


def build_evidence_pack(db: Session, task: Task) -> dict[str, Any]:
    raw = serialize_task(db, task)
    metrics = serialize_metrics(task)
    judgements: list[dict[str, str]] = [
        {
            "grade": "measurement",
            "text": (
                f"任务类型 {raw.get('type_label')}，状态 {raw.get('status')}，"
                f"样本量 n={raw.get('n')}，预处理 {raw.get('preprocess', {}).get('name')} "
                f"{raw.get('preprocess', {}).get('width')}×{raw.get('preprocess', {}).get('height')}。"
            ),
        }
    ]
    if not task.has_gt or not metrics.get("available"):
        judgements.append({"grade": "rule", "text": "无配对 GT 或指标不可用，无法谈精度。"})
        metrics_out: dict[str, Any] = {"available": False}
    else:
        metrics_out = metrics
        if metrics.get("disclaimer"):
            judgements.append({"grade": "rule", "text": str(metrics["disclaimer"])})
    return {
        "task": {
            "id": raw["id"],
            "type": raw["type"],
            "type_label": raw.get("type_label") or TASK_TYPE_LABELS.get(task.type, task.type),
            "status": raw["status"],
            "has_gt": raw["has_gt"],
            "n": raw.get("n"),
            "created_at": raw.get("created_at"),
            "dataset": raw.get("dataset"),
            "preprocess": raw.get("preprocess"),
            "models": raw.get("models"),
            "samples": raw.get("samples"),
            "preview_sample_keys": raw.get("preview_sample_keys"),
            "cam_disclaimer": raw.get("cam_disclaimer"),
            "bundle_ready": raw.get("bundle_ready"),
            "open_path": f"/eval/{task.id}" if task.type == "eval" else f"/compare/{task.id}",
        },
        "metrics": metrics_out,
        "visualizations": _viz_links(raw.get("artifacts") or []),
        "judgements": judgements,
    }


def _assert_pack_has_no_accuracy(pack: dict[str, Any]) -> None:
    metrics = pack.get("metrics") or {}
    if metrics.get("available"):
        return
    blob = json.dumps(metrics, ensure_ascii=False).lower()
    for token in ("miou", "mdice", "acc"):
        if token in blob:
            raise AppError("无 GT 证据包不得含精度字段", code="METRIC_LEAK", stage="protocol", status_code=500)


def create_session(db: Session, user: User, *, specialty: str = "segment") -> AssistantSession:
    if specialty not in OPEN_SPECIALTIES:
        raise AppError("该专科尚未开放", code="SPECIALTY_CLOSED", stage="protocol", status_code=400)
    row = AssistantSession(
        id=new_id(),
        user_id=user.id,
        specialty=specialty,
        created_at=utcnow(),
        updated_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def get_session(db: Session, session_id: str, user: User) -> AssistantSession:
    row = (
        db.query(AssistantSession)
        .options(selectinload(AssistantSession.turns))
        .filter(AssistantSession.id == session_id)
        .one_or_none()
    )
    if row is None or row.user_id != user.id:
        raise AppError("会话不存在", code="NOT_FOUND", stage="auth", status_code=404)
    return row


def _require_tool(session: AssistantSession, tool: str) -> None:
    allowed = TOOLS_BY_SPECIALTY.get(session.specialty, frozenset())
    if tool not in allowed:
        raise AppError("当前专科不能使用该工具", code="TOOL_FORBIDDEN", stage="protocol", status_code=400)


def serialize_turn(turn: AssistantTurn) -> dict[str, Any]:
    return {
        "id": turn.id,
        "role": turn.role or "assistant",
        "content": turn.content,
        "intent": turn.intent,
        "tool_name": turn.tool_name,
        "task_id": turn.task_id,
        "llm_status": turn.llm_status,
        "llm_model": turn.llm_model,
        "writing": turn.writing,
        "evidence_pack": turn.evidence_json,
        "params_summary": json.loads(turn.params_summary) if turn.params_summary else None,
        "created_at": _iso(turn.created_at),
    }


def serialize_session_card(row: AssistantSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "specialty": row.specialty,
        "title": row.title or "新对话",
        "updated_at": _iso(row.updated_at),
        "working": row.working_json,
    }


def serialize_session(row: AssistantSession) -> dict[str, Any]:
    turns = sorted(row.turns, key=lambda item: item.created_at)
    return {
        "id": row.id,
        "specialty": row.specialty,
        "title": row.title or "新对话",
        "working": row.working_json,
        "llm_ready": llm_ready(),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
        "turns": [serialize_turn(turn) for turn in turns],
    }


def list_sessions(db: Session, user: User, specialty: str | None = None) -> dict[str, Any]:
    query = db.query(AssistantSession).filter(
        AssistantSession.user_id == user.id,
        exists().where(AssistantTurn.session_id == AssistantSession.id),
    )
    if specialty:
        if specialty not in OPEN_SPECIALTIES:
            raise AppError("该专科尚未开放", code="SPECIALTY_CLOSED", stage="protocol", status_code=400)
        query = query.filter(AssistantSession.specialty == specialty)
    rows = query.order_by(AssistantSession.updated_at.desc()).limit(50).all()
    return {
        "llm_ready": llm_ready(),
        "open_specialties": sorted(OPEN_SPECIALTIES),
        "items": [serialize_session_card(row) for row in rows],
    }


def conversation_history(session: AssistantSession) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for turn in sorted(session.turns, key=lambda item: item.created_at):
        role = turn.role or "assistant"
        if role == "user":
            text = (turn.content or "").strip()
        else:
            text = (turn.writing or "").strip()
        if not text:
            continue
        items.append({"role": "user" if role == "user" else "assistant", "content": text[:2000]})
    if items and items[-1]["role"] == "user":
        items = items[:-1]
    return items[-12:]


def _set_working(session: AssistantSession, **fields: Any) -> None:
    data = dict(session.working_json or {})
    for key, value in fields.items():
        if value is None:
            continue
        data[key] = value
    session.working_json = data


def _title_from(text: str) -> str:
    return text.replace("\n", " ").strip()[:40] or "新对话"


def _persist_user_turn(db: Session, session: AssistantSession, content: str) -> AssistantTurn:
    if not session.title:
        session.title = _title_from(content)
    turn = AssistantTurn(
        id=new_id(),
        session_id=session.id,
        role="user",
        content=content,
        intent="user_message",
        tool_name="chat",
        llm_status="skipped",
        created_at=utcnow(),
    )
    session.updated_at = utcnow()
    db.add(session)
    db.add(turn)
    db.commit()
    db.refresh(session)
    db.expire(session, ["turns"])
    return turn


def _persist_turn(
    db: Session,
    user: User,
    session: AssistantSession,
    *,
    intent: str,
    tool_name: str,
    params: dict[str, Any],
    summary: dict[str, Any],
    evidence: dict[str, Any],
    writing: str | None,
    llm_status: str,
    llm_model: str | None,
    task_id: str | None,
    audit_action: str,
    audit_target: str,
    audit_reason: str,
) -> AssistantTurn:
    turn = AssistantTurn(
        id=new_id(),
        session_id=session.id,
        role="assistant",
        content=None,
        intent=intent,
        tool_name=tool_name,
        params_summary=json.dumps(params, ensure_ascii=False),
        result_summary=json.dumps(summary, ensure_ascii=False),
        task_id=task_id,
        llm_status=llm_status,
        llm_model=llm_model,
        writing=writing,
        evidence_json=evidence,
        created_at=utcnow(),
    )
    session.updated_at = utcnow()
    db.add(session)
    db.add(turn)
    _write_audit(
        db,
        actor_id=user.id,
        action=audit_action,
        target_id=audit_target,
        reason=audit_reason,
    )
    db.commit()
    db.refresh(turn)
    return turn


def _maybe_write(
    settings: Settings,
    draft_fn,
    *args,
    **kwargs,
) -> tuple[str, str | None, str | None]:
    if not llm_ready(settings):
        return "skipped", None, None
    drafted = draft_fn(*args, settings=settings, **kwargs)
    if drafted:
        return "ok", settings.llm_model, drafted
    return "error", None, None


def _iter_writing(settings: Settings, messages: list[dict[str, str]]) -> Iterator[dict[str, Any]]:
    if not llm_ready(settings):
        yield {"type": "result", "llm_status": "skipped", "llm_model": None, "writing": None}
        return
    parts: list[str] = []
    for delta in iter_chat_completion(messages, settings=settings):
        if not delta:
            continue
        parts.append(delta)
        yield {"type": "delta", "text": delta}
    writing = "".join(parts).strip() or None
    yield {
        "type": "result",
        "llm_status": "ok" if writing else "error",
        "llm_model": settings.llm_model if writing else None,
        "writing": writing,
    }


def add_analyze_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    task_id: str,
    question: str | None = None,
    settings: Settings | None = None,
) -> AssistantTurn:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    _require_tool(session, "task.analyze")
    task = get_analyzable_task(db, task_id, user)
    pack = build_evidence_pack(db, task)
    _assert_pack_has_no_accuracy(pack)
    asked = (question or "").strip()[:2000] or None
    history = conversation_history(session)
    llm_status, llm_model, writing = _maybe_write(
        settings, draft_analyze_copy, pack, question=asked, history=history
    )
    _set_working(session, task_id=task.id)
    summary = {
        "task_id": task.id,
        "type": task.type,
        "has_gt": bool(task.has_gt),
        "metrics_available": bool((pack.get("metrics") or {}).get("available")),
        "n": pack.get("task", {}).get("n"),
        "question": asked,
    }
    return _persist_turn(
        db,
        user,
        session,
        intent="analyze_task",
        tool_name="task.analyze",
        params={"task_id": task.id, "question": asked},
        summary=summary,
        evidence=pack,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=task.id,
        audit_action="assistant.task.analyze",
        audit_target=task.id,
        audit_reason="科研助手分析对比/评测",
    )


def _reject_catalog_id(db: Session, version_id: str) -> None:
    if db.get(CatalogModel, version_id) is not None:
        raise AppError("首页文献卡片不是可运行模型", code="CATALOG_NOT_RUNNABLE", stage="protocol", status_code=400)


def _visible_version(db: Session, version_id: str, user: User) -> ModelVersion:
    _reject_catalog_id(db, version_id)
    version = (
        db.query(ModelVersion)
        .options(selectinload(ModelVersion.model), selectinload(ModelVersion.weights))
        .filter(ModelVersion.id == version_id)
        .one_or_none()
    )
    if version is None:
        model = db.get(Model, version_id)
        if model is not None:
            version = (
                db.query(ModelVersion)
                .options(selectinload(ModelVersion.model), selectinload(ModelVersion.weights))
                .filter(ModelVersion.model_id == model.id)
                .order_by(ModelVersion.created_at.desc())
                .first()
            )
    if version is None or not can_view_version(user, version.model, version):
        raise AppError("模型不存在", code="NOT_FOUND", stage="auth", status_code=404)
    from app.services.models import is_classification_version
    if is_classification_version(db, version):
        raise AppError("科研助手尚未开放分类模型工具，请使用钢铁缺陷分类页", code="UNAVAILABLE", stage="protocol", status_code=400)
    return version


def preview_infer_run(
    db: Session,
    user: User,
    *,
    batch_id: str,
    baseline_version_ids: list[str],
    student_version_id: str | None,
) -> dict[str, Any]:
    version = db.get(DatasetVersion, batch_id)
    if version is None:
        raise AppError("上传批次不存在", code="BATCH_NOT_FOUND", stage="file", status_code=404)
    dataset = db.get(Dataset, version.dataset_id)
    if dataset is None:
        raise AppError("数据集不存在", code="NOT_FOUND", stage="file", status_code=404)
    if version.kind == DEMO_CATALOG_KIND or version.kind == "demo":
        raise AppError("公开演示不能经科研助手入队", code="DEMO_NO_INFER", stage="protocol", status_code=400)
    if version.kind != "upload_batch" or version.is_fixed_test:
        raise AppError(
            "助手代跑只能用本次上传的对比批次，不能用正式评测固定集或演示样例",
            code="INFER_BATCH_FORBIDDEN",
            stage="protocol",
            status_code=400,
        )
    if dataset.visibility == "private" and dataset.owner_id != user.id and user.role != "advisor":
        raise AppError("无权使用该批次", code="FORBIDDEN", stage="auth", status_code=403)
    samples = db.query(Sample).filter(Sample.version_id == version.id).order_by(Sample.sample_key.asc()).all()
    if not samples:
        raise AppError("该批次没有图片", code="NO_SAMPLES", stage="file", status_code=400)
    for vid in list(baseline_version_ids) + ([student_version_id] if student_version_id else []):
        _reject_catalog_id(db, vid)
    resolved_baselines, resolved_student = _resolve_runnable_models(
        db, user, baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id, version=version,
    )
    baselines = [
        {"id": mv.id, "name": mv.model.name, "slug": mv.slug, "status": mv.status}
        for mv in resolved_baselines
    ]
    student = None
    if resolved_student is not None:
        sv = resolved_student
        student = {"id": sv.id, "name": sv.model.name, "status": sv.status}
    has_gt = bool(samples) and all(s.mask_uri for s in samples)
    return {
        "needs_confirm": True,
        "task_type": "segmentation",
        "will_call": "create_compare_task",
        "forbidden": ["demo", "eval"],
        "batch_id": version.id,
        "n": len(samples),
        "has_gt": has_gt,
        "baselines": baselines,
        "student": student,
        "note": "无配对 GT 时只出可视化，不计算精度。确认后才会入队快速对比。",
    }


def add_infer_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    batch_id: str,
    baseline_version_ids: list[str],
    student_version_id: str | None = None,
    confirm: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any] | AssistantTurn:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    _require_tool(session, "infer.run")
    preview = preview_infer_run(
        db,
        user,
        batch_id=batch_id,
        baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id,
    )
    if not confirm:
        return {"needs_confirm": True, "preview": preview, "llm_ready": llm_ready(settings)}
    task = create_compare_task(
        db,
        user,
        batch_id=batch_id,
        baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id or None,
        settings=settings,
    )
    evidence = {
        "queued": True,
        "preview": preview,
        "task": {
            "id": task.id,
            "type": task.type,
            "status": task.status,
            "has_gt": bool(task.has_gt),
            "open_path": f"/compare/{task.id}",
        },
        "judgements": [
            {"grade": "rule", "text": "已封装现有快速对比入队，未调用公开演示或正式评测。"},
            {"grade": "rule", "text": "无 GT 不得谈精度。完成后可在本会话追问分析。"},
        ],
    }
    _set_working(session, task_id=task.id)
    turn = _persist_turn(
        db,
        user,
        session,
        intent="infer_run",
        tool_name="infer.run",
        params={
            "batch_id": batch_id,
            "baseline_version_ids": baseline_version_ids,
            "student_version_id": student_version_id,
            "confirm": True,
        },
        summary={"task_id": task.id, "type": "compare", "has_gt": bool(task.has_gt), "n": preview["n"]},
        evidence=evidence,
        writing=None,
        llm_status="skipped",
        llm_model=None,
        task_id=task.id,
        audit_action="assistant.infer.run",
        audit_target=task.id,
        audit_reason="科研助手封装快速对比",
    )
    return turn


def _perf_complete(perf: dict[str, Any]) -> bool:
    return (
        perf.get("status") == "success"
        and perf.get("latency_ms_per_image") is not None
        and perf.get("param_count") is not None
    )


def add_perf_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    version_id: str,
    enqueue: bool = False,
    settings: Settings | None = None,
) -> dict[str, Any] | AssistantTurn:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    _require_tool(session, "perf.measure")
    version = _visible_version(db, version_id, user)
    model = version.model
    if version.status != "runnable":
        raise AppError(
            "导入未通过检查，不能测速。请到模型卡使用模型适配助手。",
            code="NOT_RUNNABLE",
            stage="auth",
            status_code=400,
        )
    if version.requires_cuda:
        raise AppError(
            "当前环境为 CPU，该模型标明需要 CUDA，不可测量。",
            code="CUDA_REQUIRED",
            stage="resource",
            status_code=400,
        )
    perf = serialize_perf(db, version, model, settings=settings)
    card = {
        "id": version.id,
        "name": model.name,
        "source": model.source,
        "status": version.status,
        "open_path": f"/models/{version.id}",
    }
    if _perf_complete(perf) and not enqueue:
        evidence = {
            "version": card,
            "perf": perf,
            "disclaimer": FPS_DISCLAIMER,
            "queued": False,
        }
        _set_working(session, version_id=version.id)
        return _persist_turn(
            db,
            user,
            session,
            intent="perf_measure",
            tool_name="perf.measure",
            params={"version_id": version.id, "enqueue": False},
            summary={"version_id": version.id, "status": perf.get("status"), "read_only": True},
            evidence=evidence,
            writing=None,
            llm_status="skipped",
            llm_model=None,
            task_id=None,
            audit_action="assistant.perf.measure",
            audit_target=version.id,
            audit_reason="科研助手只读测参档案",
        )
    if not enqueue:
        return {
            "needs_confirm": True,
            "preview": {
                "version": card,
                "perf": perf,
                "protocol": {
                    "device": "cpu",
                    "batch": 1,
                    "input_kind": "dummy",
                    "input": f"{version.input_h}×{version.input_w}",
                    "warmup_runs": 3,
                    "timed_runs": 10,
                },
                "disclaimer": FPS_DISCLAIMER,
            },
            "llm_ready": llm_ready(settings),
        }
    profile = request_measure(db, version, model)
    perf = serialize_perf(db, version, model, settings=settings)
    evidence = {
        "version": card,
        "perf": perf,
        "queued": profile.status in {"queued", "measuring"},
        "disclaimer": FPS_DISCLAIMER,
    }
    _set_working(session, version_id=version.id)
    return _persist_turn(
        db,
        user,
        session,
        intent="perf_measure",
        tool_name="perf.measure",
        params={"version_id": version.id, "enqueue": True},
        summary={"version_id": version.id, "status": perf.get("status")},
        evidence=evidence,
        writing=None,
        llm_status="skipped",
        llm_model=None,
        task_id=None,
        audit_action="assistant.perf.measure",
        audit_target=version.id,
        audit_reason="科研助手调用实验室测参入队",
    )


def _read_student_source(version: ModelVersion) -> str | None:
    from app.services.adapt import _read_source

    try:
        return _read_source(get_settings(), version)
    except AppError:
        return None


def add_code_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    version_id: str,
    snippet: str | None = None,
    question: str | None = None,
    settings: Settings | None = None,
) -> AssistantTurn:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    _require_tool(session, "code.advise")
    version = _visible_version(db, version_id, user)
    model = version.model
    assert_model_content_access(user, model, version)
    source_text = (snippet or "").strip() or None
    if not source_text and model.source == "student":
        source_text = _read_student_source(version)
    excerpt = (source_text or "")[:SOURCE_LIMIT]
    rule_notes = [
        "科研助手不写盘、不改哈希、不改 runnable。落地改适配层请到模型卡使用模型适配助手。",
        "禁止 strict=False，禁止去掉 module. 前缀，禁止把被禁 import 加入站点白名单。",
        FPS_DISCLAIMER,
    ]
    if model.source == "builtin":
        writing = (
            "内置 baseline 不提供改源码建议。参数量与本机 FPS 请用本专科的测参或实验室「模型测评」。"
            "学生导入失败请到该版本模型卡使用模型适配助手。"
        )
        llm_status, llm_model = "skipped", None
    else:
        summary = {
            "name": model.name,
            "status": version.status,
            "fail_stage": version.fail_stage,
            "fail_message": (version.fail_message or "")[:400],
            "entry_symbol": version.entry_symbol,
            "question": (question or "").strip()[:2000] or None,
            "source_excerpt": excerpt[:4000] if excerpt else None,
            "rule_notes": rule_notes,
        }
        history = conversation_history(session)
        llm_status, llm_model, writing = _maybe_write(settings, draft_code_advice, summary, history=history)
        if llm_status == "skipped":
            writing = "未配置大模型。以下为规则摘要，不是已写入的补丁。\n" + "\n".join(rule_notes)
            if version.fail_message:
                writing += f"\n检查失败：{version.fail_stage} / {version.fail_message}"
    evidence = {
        "version": {
            "id": version.id,
            "name": model.name,
            "source": model.source,
            "status": version.status,
            "fail_stage": version.fail_stage,
            "open_path": f"/models/{version.id}",
        },
        "wrote_disk": False,
        "rule_notes": rule_notes,
        "source_excerpt": excerpt[:1200] if excerpt else None,
    }
    _set_working(session, version_id=version.id)
    return _persist_turn(
        db,
        user,
        session,
        intent="code_advise",
        tool_name="code.advise",
        params={"version_id": version.id, "has_snippet": bool((snippet or "").strip())},
        summary={"version_id": version.id, "wrote_disk": False},
        evidence=evidence,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=None,
        audit_action="assistant.code.advise",
        audit_target=version.id,
        audit_reason="科研助手源码建议文本",
    )


def _last_kb_hits(session: AssistantSession) -> list[dict[str, Any]]:
    for turn in reversed(sorted(session.turns, key=lambda item: item.created_at)):
        pack = turn.evidence_json or {}
        hits = pack.get("hits") or []
        if hits and pack.get("hit"):
            return hits
    return []


def _hit_index(text: str) -> int | None:
    match = _HIT_INDEX.search(text or "")
    if not match:
        return None
    token = match.group(1)
    number = int(token) if token.isdigit() else _CN_NUM.get(token, 0)
    return number if number >= 1 else None


def _previous_kb_query(session: AssistantSession) -> str:
    return str((session.working_json or {}).get("kb_query") or "").strip()


def _is_followup(asked: str, previous: str) -> bool:
    if not previous or previous == asked:
        return False
    if any(hint in asked for hint in FOLLOW_HINTS) or any(token in asked for token in _ANAPHORA):
        return True
    compact = re.sub(r"\s+", "", asked)
    return len(compact) <= 12 and compact.endswith(("呢", "吗"))


def _resolve_kb(
    db: Session,
    session: AssistantSession,
    asked: str,
    *,
    settings: Settings,
) -> dict[str, Any]:
    """Pick a saved hit, rewrite a follow-up, or search the question as asked."""
    index = _hit_index(asked)
    if index is not None:
        prior = _last_kb_hits(session)
        if 1 <= index <= len(prior):
            return {
                "hits": [prior[index - 1]],
                "via": "session",
                "reused": True,
                "rewritten": False,
                "elapsed_ms": 0,
            }
        return {"hits": [], "via": "none", "reused": False, "rewritten": False, "elapsed_ms": 0}
    previous = _previous_kb_query(session)
    follow = _is_followup(asked, previous)
    search_text = f"{previous}\n{asked}" if follow else asked
    rewritten = follow
    retrieved = retrieve_kb(db, search_text, settings=settings)
    hits = list(retrieved.get("hits") or [])
    reused = False
    via = str(retrieved.get("via") or "none")
    if not hits and follow:
        prior = _last_kb_hits(session)
        if prior:
            hits = prior
            reused = True
            via = "session"
            rewritten = False
    return {
        "hits": hits,
        "via": via,
        "reused": reused,
        "rewritten": rewritten and bool(hits),
        "elapsed_ms": int(retrieved.get("elapsed_ms") or 0),
    }


def add_kb_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    question: str,
    want_answer: bool = True,
    settings: Settings | None = None,
) -> AssistantTurn:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    _require_tool(session, "kb.retrieve")
    asked = (question or "").strip()[:2000]
    if not asked:
        raise AppError("请输入问题", code="EMPTY_QUERY", stage="protocol", status_code=400)
    resolved = _resolve_kb(db, session, asked, settings=settings)
    hits = resolved["hits"]
    reused = bool(resolved["reused"])
    rewritten = bool(resolved["rewritten"])
    via = str(resolved["via"] or "none")
    elapsed_ms = int(resolved["elapsed_ms"] or 0)
    if not hits:
        evidence = {
            "query": asked,
            "hit": False,
            "hits": [],
            "refused": True,
            "reason": "审定语料未命中，不能自由发挥。",
        }
        return _persist_turn(
            db,
            user,
            session,
            intent="kb_retrieve",
            tool_name="kb.retrieve",
            params={"question": asked},
            summary={"hit": False},
            evidence=evidence,
            writing="语料未覆盖该问题，学术专科拒绝作答。请换一个与课题组方向、学习路线或本站协议有关的问题。",
            llm_status="skipped",
            llm_model=None,
            task_id=None,
            audit_action="assistant.kb.retrieve",
            audit_target=session.id,
            audit_reason=_kb_audit_reason(
                asked,
                [],
                via=via,
                elapsed_ms=elapsed_ms,
                rewritten=rewritten,
            ),
        )
    writing = None
    llm_status, llm_model = "skipped", None
    tool_name = "kb.retrieve"
    intent = "kb_retrieve"
    history = conversation_history(session)
    if want_answer:
        tool_name = "kb.answer"
        intent = "kb_answer"
        llm_status, llm_model, writing = _maybe_write(
            settings, draft_kb_copy, asked, hits, history=history
        )
        if llm_status == "skipped":
            writing = None
    evidence = {
        "query": asked,
        "hit": True,
        "via": via,
        "hits": hits,
        "refused": False,
        "reused": reused,
        "rewritten": rewritten,
    }
    working_fields: dict[str, Any] = {
        "kb_titles": [item.get("title") for item in hits[:8] if item.get("title")],
    }
    if not reused and not rewritten:
        working_fields["kb_query"] = asked
    _set_working(session, **working_fields)
    return _persist_turn(
        db,
        user,
        session,
        intent=intent,
        tool_name=tool_name,
        params={"question": asked},
        summary={"hit": True, "n": len(hits), "via": evidence.get("via"), "reused": reused},
        evidence=evidence,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=None,
        audit_action=f"assistant.{tool_name}",
        audit_target=session.id,
        audit_reason=_kb_audit_reason(
            asked,
            hits,
            via=via,
            elapsed_ms=elapsed_ms,
            rewritten=rewritten,
        ),
    )


def dispatch_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    tool: str,
    task_id: str | None = None,
    question: str | None = None,
    confirm: bool = False,
    batch_id: str | None = None,
    baseline_version_ids: list[str] | None = None,
    student_version_id: str | None = None,
    version_id: str | None = None,
    enqueue: bool = False,
    snippet: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    if tool in {"infer.detect", "infer.classify", "run_detect", "run_classify"}:
        raise AppError("检测 / 分类管道尚未开放，不能用分割工具冒充", code="UNAVAILABLE", stage="protocol", status_code=400)
    session = get_session(db, session_id, user)
    _require_tool(session, tool)
    if tool == "task.analyze":
        if not task_id:
            raise AppError("请选择要分析的任务", code="TASK_REQUIRED", stage="protocol", status_code=400)
        turn = add_analyze_turn(db, user, session_id, task_id=task_id, question=question, settings=settings)
        return serialize_turn(turn)
    if tool == "infer.run":
        if not batch_id:
            raise AppError("请先上传图片批次", code="BATCH_REQUIRED", stage="file", status_code=400)
        result = add_infer_turn(
            db,
            user,
            session_id,
            batch_id=batch_id,
            baseline_version_ids=baseline_version_ids or [],
            student_version_id=student_version_id,
            confirm=confirm,
            settings=settings,
        )
        if isinstance(result, AssistantTurn):
            return serialize_turn(result)
        return result
    if tool == "perf.measure":
        if not version_id:
            raise AppError("请选择模型版本", code="MODEL_REQUIRED", stage="protocol", status_code=400)
        result = add_perf_turn(
            db,
            user,
            session_id,
            version_id=version_id,
            enqueue=enqueue,
            settings=settings,
        )
        if isinstance(result, AssistantTurn):
            return serialize_turn(result)
        return result
    if tool == "code.advise":
        if not version_id:
            raise AppError("请选择模型版本", code="MODEL_REQUIRED", stage="protocol", status_code=400)
        turn = add_code_turn(
            db,
            user,
            session_id,
            version_id=version_id,
            snippet=snippet,
            question=question,
            settings=settings,
        )
        return serialize_turn(turn)
    if tool in {"kb.retrieve", "kb.answer"}:
        turn = add_kb_turn(
            db,
            user,
            session_id,
            question=question or "",
            want_answer=tool == "kb.answer",
            settings=settings,
        )
        return serialize_turn(turn)
    raise AppError("未知工具", code="UNKNOWN_TOOL", stage="protocol", status_code=400)


def _session_payload(db: Session, user: User, session_id: str, pending: dict[str, Any] | None = None) -> dict[str, Any]:
    data = serialize_session(get_session(db, session_id, user))
    if pending is not None:
        data["pending"] = pending
    return data


def _persist_pending(
    db: Session,
    user: User,
    session: AssistantSession,
    *,
    tool_name: str,
    preview: dict[str, Any],
    writing: str,
) -> AssistantTurn:
    return _persist_turn(
        db,
        user,
        session,
        intent="needs_confirm",
        tool_name=tool_name,
        params={"confirm": False},
        summary={"needs_confirm": True},
        evidence={"needs_confirm": True, "preview": preview},
        writing=writing,
        llm_status="skipped",
        llm_model=None,
        task_id=None,
        audit_action=f"assistant.{tool_name}.preview",
        audit_target=session.id,
        audit_reason="科研助手待确认",
    )


def _persist_clarify(db: Session, user: User, session: AssistantSession, writing: str) -> AssistantTurn:
    return _persist_turn(
        db,
        user,
        session,
        intent="clarify",
        tool_name="chat",
        params={},
        summary={"clarify": True},
        evidence={"clarify": True},
        writing=writing,
        llm_status="skipped",
        llm_model=None,
        task_id=None,
        audit_action="assistant.clarify",
        audit_target=session.id,
        audit_reason="科研助手追问槽位",
    )


def _iter_analyze_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    task_id: str,
    question: str | None = None,
    settings: Settings,
) -> Iterator[dict[str, Any]]:
    session = get_session(db, session_id, user)
    _require_tool(session, "task.analyze")
    task = get_analyzable_task(db, task_id, user)
    pack = build_evidence_pack(db, task)
    _assert_pack_has_no_accuracy(pack)
    asked = (question or "").strip()[:2000] or None
    history = conversation_history(session)
    llm_status, llm_model, writing = "skipped", None, None
    for event in _iter_writing(settings, analyze_messages(pack, question=asked, history=history)):
        if event["type"] == "delta":
            yield event
        else:
            llm_status = event["llm_status"]
            llm_model = event["llm_model"]
            writing = event["writing"]
    _set_working(session, task_id=task.id)
    _persist_turn(
        db,
        user,
        session,
        intent="analyze_task",
        tool_name="task.analyze",
        params={"task_id": task.id, "question": asked},
        summary={
            "task_id": task.id,
            "type": task.type,
            "has_gt": bool(task.has_gt),
            "metrics_available": bool((pack.get("metrics") or {}).get("available")),
            "n": pack.get("task", {}).get("n"),
            "question": asked,
        },
        evidence=pack,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=task.id,
        audit_action="assistant.task.analyze",
        audit_target=task.id,
        audit_reason="科研助手分析对比/评测",
    )


def _iter_kb_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    question: str,
    want_answer: bool,
    settings: Settings,
) -> Iterator[dict[str, Any]]:
    session = get_session(db, session_id, user)
    _require_tool(session, "kb.retrieve")
    asked = (question or "").strip()[:2000]
    if not asked:
        raise AppError("请输入问题", code="EMPTY_QUERY", stage="protocol", status_code=400)
    resolved = _resolve_kb(db, session, asked, settings=settings)
    hits = resolved["hits"]
    reused = bool(resolved["reused"])
    rewritten = bool(resolved["rewritten"])
    via = str(resolved["via"] or "none")
    elapsed_ms = int(resolved["elapsed_ms"] or 0)
    if not hits:
        add_kb_turn(db, user, session_id, question=asked, want_answer=want_answer, settings=settings)
        return
    if not want_answer:
        add_kb_turn(db, user, session_id, question=asked, want_answer=False, settings=settings)
        return
    history = conversation_history(session)
    llm_status, llm_model, writing = "skipped", None, None
    for event in _iter_writing(settings, kb_messages(asked, hits, history=history)):
        if event["type"] == "delta":
            yield event
        else:
            llm_status = event["llm_status"]
            llm_model = event["llm_model"]
            writing = event["writing"]
    if llm_status == "skipped":
        writing = None
    evidence = {
        "query": asked,
        "hit": True,
        "via": via,
        "hits": hits,
        "refused": False,
        "reused": reused,
        "rewritten": rewritten,
    }
    working_fields = {
        "kb_titles": [item.get("title") for item in hits[:8] if item.get("title")],
    }
    if not reused and not rewritten:
        working_fields["kb_query"] = asked
    _set_working(session, **working_fields)
    _persist_turn(
        db,
        user,
        session,
        intent="kb_answer",
        tool_name="kb.answer",
        params={"question": asked},
        summary={"hit": True, "n": len(hits), "via": evidence.get("via"), "reused": reused},
        evidence=evidence,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=None,
        audit_action="assistant.kb.answer",
        audit_target=session.id,
        audit_reason=_kb_audit_reason(
            asked,
            hits,
            via=via,
            elapsed_ms=elapsed_ms,
            rewritten=rewritten,
        ),
    )


def _iter_code_turn(
    db: Session,
    user: User,
    session_id: str,
    *,
    version_id: str,
    snippet: str | None,
    question: str | None,
    settings: Settings,
) -> Iterator[dict[str, Any]]:
    session = get_session(db, session_id, user)
    _require_tool(session, "code.advise")
    version = _visible_version(db, version_id, user)
    model = version.model
    assert_model_content_access(user, model, version)
    source_text = (snippet or "").strip() or None
    if not source_text and model.source == "student":
        source_text = _read_student_source(version)
    excerpt = (source_text or "")[:SOURCE_LIMIT]
    rule_notes = [
        "科研助手不写盘、不改哈希、不改 runnable。落地改适配层请到模型卡使用模型适配助手。",
        "禁止 strict=False，禁止去掉 module. 前缀，禁止把被禁 import 加入站点白名单。",
        FPS_DISCLAIMER,
    ]
    if model.source == "builtin":
        add_code_turn(
            db,
            user,
            session_id,
            version_id=version_id,
            snippet=snippet,
            question=question,
            settings=settings,
        )
        return
    summary = {
        "name": model.name,
        "status": version.status,
        "fail_stage": version.fail_stage,
        "fail_message": (version.fail_message or "")[:400],
        "entry_symbol": version.entry_symbol,
        "question": (question or "").strip()[:2000] or None,
        "source_excerpt": excerpt[:4000] if excerpt else None,
        "rule_notes": rule_notes,
    }
    history = conversation_history(session)
    llm_status, llm_model, writing = "skipped", None, None
    for event in _iter_writing(settings, code_messages(summary, history=history)):
        if event["type"] == "delta":
            yield event
        else:
            llm_status = event["llm_status"]
            llm_model = event["llm_model"]
            writing = event["writing"]
    if llm_status == "skipped":
        writing = "未配置大模型。以下为规则摘要，不是已写入的补丁。\n" + "\n".join(rule_notes)
        if version.fail_message:
            writing += f"\n检查失败：{version.fail_stage} / {version.fail_message}"
    evidence = {
        "version": {
            "id": version.id,
            "name": model.name,
            "source": model.source,
            "status": version.status,
            "fail_stage": version.fail_stage,
            "open_path": f"/models/{version.id}",
        },
        "wrote_disk": False,
        "rule_notes": rule_notes,
        "source_excerpt": excerpt[:1200] if excerpt else None,
    }
    _set_working(session, version_id=version.id)
    _persist_turn(
        db,
        user,
        session,
        intent="code_advise",
        tool_name="code.advise",
        params={"version_id": version.id, "has_snippet": bool((snippet or "").strip())},
        summary={"version_id": version.id, "wrote_disk": False},
        evidence=evidence,
        writing=writing,
        llm_status=llm_status,
        llm_model=llm_model,
        task_id=None,
        audit_action="assistant.code.advise",
        audit_target=version.id,
        audit_reason="科研助手源码建议文本",
    )


def iter_add_message(
    db: Session,
    user: User,
    session_id: str,
    *,
    content: str | None = None,
    tool: str | None = None,
    task_id: str | None = None,
    question: str | None = None,
    confirm: bool = False,
    batch_id: str | None = None,
    baseline_version_ids: list[str] | None = None,
    student_version_id: str | None = None,
    version_id: str | None = None,
    enqueue: bool = False,
    snippet: str | None = None,
    settings: Settings | None = None,
) -> Iterator[dict[str, Any]]:
    settings = settings or get_settings()
    session = get_session(db, session_id, user)
    text = (content or question or "").strip()[:2000]
    explicit = (tool or "").strip() or None
    if explicit in {"infer.detect", "infer.classify", "run_detect", "run_classify"}:
        raise AppError("检测 / 分类管道尚未开放，不能用分割工具冒充", code="UNAVAILABLE", stage="protocol", status_code=400)
    if not text and not explicit and not confirm and not batch_id:
        raise AppError("请输入问题", code="EMPTY_QUERY", stage="protocol", status_code=400)
    if text:
        _persist_user_turn(db, session, text)
        session = get_session(db, session_id, user)
    working = dict(session.working_json or {})
    tid = task_id or working.get("task_id")
    vid = version_id or working.get("version_id")

    def finish(result: Any = None, tool_name: str | None = None) -> dict[str, Any]:
        if isinstance(result, dict) and result.get("needs_confirm"):
            current = get_session(db, session_id, user)
            _persist_pending(
                db,
                user,
                current,
                tool_name=tool_name or explicit or "chat",
                preview=result.get("preview") or result,
                writing="请确认后才会执行。未确认不会入队。",
            )
            return _session_payload(db, user, session_id, pending=result)
        return _session_payload(db, user, session_id)

    if explicit:
        _require_tool(session, explicit)
        if explicit == "task.analyze":
            if not tid:
                _persist_clarify(db, user, session, "请选择一条对比或评测后再分析。公开演示不能分析。")
                yield {"type": "done", "session": finish()}
                return
            yield from _iter_analyze_turn(
                db, user, session_id, task_id=tid, question=text or None, settings=settings
            )
            yield {"type": "done", "session": finish()}
            return
        if explicit == "infer.run":
            if not batch_id:
                raise AppError("请先上传图片批次", code="BATCH_REQUIRED", stage="file", status_code=400)
            result = add_infer_turn(
                db,
                user,
                session_id,
                batch_id=batch_id,
                baseline_version_ids=baseline_version_ids or [],
                student_version_id=student_version_id,
                confirm=confirm,
                settings=settings,
            )
            yield {"type": "done", "session": finish(result, "infer.run")}
            return
        if explicit == "perf.measure":
            if not vid:
                _persist_clarify(db, user, session, "请先选择模型版本，再查看或入队测参。")
                yield {"type": "done", "session": finish()}
                return
            result = add_perf_turn(
                db,
                user,
                session_id,
                version_id=vid,
                enqueue=enqueue or confirm,
                settings=settings,
            )
            yield {"type": "done", "session": finish(result, "perf.measure")}
            return
        if explicit == "code.advise":
            if not vid:
                _persist_clarify(db, user, session, "请先选择模型版本，再询问源码建议。")
                yield {"type": "done", "session": finish()}
                return
            yield from _iter_code_turn(
                db,
                user,
                session_id,
                version_id=vid,
                snippet=snippet,
                question=text or None,
                settings=settings,
            )
            yield {"type": "done", "session": finish()}
            return
        if explicit in {"kb.retrieve", "kb.answer"}:
            yield from _iter_kb_turn(
                db,
                user,
                session_id,
                question=text or "",
                want_answer=explicit == "kb.answer",
                settings=settings,
            )
            yield {"type": "done", "session": finish()}
            return
        raise AppError("未知工具", code="UNKNOWN_TOOL", stage="protocol", status_code=400)

    if session.specialty == "academic":
        yield from _iter_kb_turn(
            db, user, session_id, question=text or "", want_answer=True, settings=settings
        )
        yield {"type": "done", "session": finish()}
        return

    if session.specialty == "segment":
        if batch_id:
            result = add_infer_turn(
                db,
                user,
                session_id,
                batch_id=batch_id,
                baseline_version_ids=baseline_version_ids or [],
                student_version_id=student_version_id,
                confirm=confirm,
                settings=settings,
            )
            yield {"type": "done", "session": finish(result, "infer.run")}
            return
        if tid:
            yield from _iter_analyze_turn(
                db, user, session_id, task_id=tid, question=text or None, settings=settings
            )
            yield {"type": "done", "session": finish()}
            return
        _persist_clarify(
            db,
            user,
            session,
            "请选择一条对比或评测，或在附件栏上传图片做分割代跑。公开演示不能分析，也不能代跑。",
        )
        yield {"type": "done", "session": finish()}
        return

    vid = version_id or working.get("version_id")
    want_perf = enqueue or confirm or (text and any(token in text for token in ("测参", "参数量")))
    if want_perf:
        if not vid:
            _persist_clarify(db, user, session, "请先在附件栏选择模型版本，再查看或入队测参。")
            yield {"type": "done", "session": finish()}
            return
        result = add_perf_turn(
            db,
            user,
            session_id,
            version_id=vid,
            enqueue=enqueue or confirm,
            settings=settings,
        )
        yield {"type": "done", "session": finish(result, "perf.measure")}
        return
    if vid:
        yield from _iter_code_turn(
            db,
            user,
            session_id,
            version_id=vid,
            snippet=snippet,
            question=text or None,
            settings=settings,
        )
        yield {"type": "done", "session": finish()}
        return
    _persist_clarify(
        db,
        user,
        session,
        "请先选择模型版本。测参请点附件栏「测参」；源码建议直接输入问题即可。",
    )
    yield {"type": "done", "session": finish()}


def add_message(
    db: Session,
    user: User,
    session_id: str,
    *,
    content: str | None = None,
    tool: str | None = None,
    task_id: str | None = None,
    question: str | None = None,
    confirm: bool = False,
    batch_id: str | None = None,
    baseline_version_ids: list[str] | None = None,
    student_version_id: str | None = None,
    version_id: str | None = None,
    enqueue: bool = False,
    snippet: str | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] | None = None
    for event in iter_add_message(
        db,
        user,
        session_id,
        content=content,
        tool=tool,
        task_id=task_id,
        question=question,
        confirm=confirm,
        batch_id=batch_id,
        baseline_version_ids=baseline_version_ids,
        student_version_id=student_version_id,
        version_id=version_id,
        enqueue=enqueue,
        snippet=snippet,
        settings=settings,
    ):
        if event.get("type") == "done":
            payload = event.get("session")
    if payload is None:
        raise AppError("助手未返回会话", code="EMPTY_REPLY", stage="protocol", status_code=500)
    return payload

