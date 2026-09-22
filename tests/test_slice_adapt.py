from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from admit.scan import scan_student_source
from app.config import Settings
from app.db.models import AuditLog, Model, ModelVersion, PreprocessSpecRow, User
from app.db.session import Base
from app.errors import AppError
from app.services.adapt import apply_adapt, build_proposal
from app.services.adapt_ast import (
    LAB_ADAPT_BEGIN,
    PREVIEW_FIRST,
    analyze_source,
    append_patch,
    apply_patch,
    class_source_unchanged,
    render_adapter_patch,
    source_outside_adapt_unchanged,
)
from app.util_time import utcnow
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

FIXTURE = ROOT / "tests" / "fixtures" / "student" / "missing_entry_tuple.py"


def _source() -> str:
    return FIXTURE.read_text(encoding="utf-8")


def test_missing_entry_tuple_is_whitelisted() -> None:
    analysis = analyze_source(
        _source(),
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="构建失败：找不到入口 build_model",
        status="cannot_start",
    )
    assert analysis.target is not None
    assert analysis.target.name == "DemoNet"
    assert analysis.can_apply is True
    assert "missing_entry" in analysis.kinds
    assert "ctor_kwargs" in analysis.kinds
    assert "multi_output" in analysis.kinds
    patch = render_adapter_patch(analysis)
    assert "def lab_build_model(" in patch
    assert "DemoNet(num_classes=num_classes, pretrained_backbone=False)" in patch
    assert "in_channels=" not in patch.split("DemoNet(", 1)[1].split(")", 1)[0]
    assert "module." not in patch
    assert "strict" not in patch
    assert PREVIEW_FIRST.split("。", 1)[0] in patch
    updated = append_patch(_source(), patch)
    assert class_source_unchanged(_source(), updated, "DemoNet")
    assert not scan_student_source(updated)


def test_ad03_diff_does_not_rewrite_class_body() -> None:
    original = _source()
    analysis = analyze_source(
        original,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    updated = append_patch(original, render_adapter_patch(analysis))
    assert original in updated
    assert LAB_ADAPT_BEGIN in updated
    assert updated.index("class DemoNet") < updated.index(LAB_ADAPT_BEGIN)


def test_static_and_load_are_opinion_only() -> None:
    source = _source()
    static = analyze_source(
        source,
        entry_symbol="build_model",
        fail_stage="static",
        fail_message="不允许的调用 eval()",
        status="cannot_start",
    )
    assert static.can_apply is False
    assert static.primary_kind == "opinion_only"

    load = analyze_source(
        source,
        entry_symbol="build_model",
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'module.head.weight'",
        status="cannot_start",
    )
    assert load.can_apply is False
    assert load.primary_kind == "opinion_only"


def test_already_adapted_cannot_reapply() -> None:
    original = _source()
    analysis = analyze_source(
        original,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    updated = append_patch(original, render_adapter_patch(analysis))
    again = analyze_source(
        updated,
        entry_symbol="lab_build_model",
        fail_stage="build",
        fail_message="构建失败",
        status="cannot_start",
    )
    assert again.can_apply is False
    assert again.primary_kind == "already_adapted"


@pytest.fixture
def db() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _user(db: Session, user_id: str, role: str = "student") -> User:
    row = User(
        id=user_id,
        username=user_id,
        password_hash="unused",
        role=role,
        status="active",
        quota_json={"max_upload_images": 50},
        created_at=utcnow(),
    )
    db.add(row)
    db.commit()
    return row


def _version(db: Session, tmp_path: Path, owner: User, *, fail_stage: str, fail_message: str) -> tuple[Model, ModelVersion, Settings]:
    spec = PreprocessSpecRow(
        id="neu_200",
        name="neu_200",
        height=200,
        width=200,
        apply_clahe=True,
        sp_threshold=0.02,
        dataset="neu",
        created_at=utcnow(),
    )
    model = Model(id="m1", owner_id=owner.id, name="DemoNet", source="student", created_at=utcnow())
    version = ModelVersion(
        id="v1",
        model_id=model.id,
        slug="demonet-v1",
        entry_symbol="build_model",
        num_classes=4,
        in_channels=3,
        input_h=200,
        input_w=200,
        preprocess_id=spec.id,
        requires_cuda=False,
        status="cannot_start",
        fail_stage=fail_stage,
        fail_message=fail_message,
        source_sha256="abc",
        visibility="private",
        created_at=utcnow(),
    )
    db.add_all([spec, model, version])
    db.commit()
    settings = Settings(storage_root=str(tmp_path / "storage"), llm_api_key="")
    dest = tmp_path / "storage" / "models" / version.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "model.py").write_text(_source(), encoding="utf-8")
    return model, version, settings


def test_ad02_decline_keeps_hash(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db, tmp_path, owner, fail_stage="build", fail_message="找不到入口 build_model"
    )
    before = (tmp_path / "storage" / "models" / version.id / "model.py").read_text(encoding="utf-8")
    monkeypatch.setattr("app.services.adapt.enqueue_admit", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.adapt.invalidate_after_write", lambda *args, **kwargs: None)
    result = apply_adapt(db, owner, version, model, consent=False, settings=settings)
    after = (tmp_path / "storage" / "models" / version.id / "model.py").read_text(encoding="utf-8")
    assert result["declined"] is True
    assert after == before
    logs = db.query(AuditLog).filter(AuditLog.action == "adapt.decline").all()
    assert len(logs) == 1


def test_ad01_apply_appends_and_requeues(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db, tmp_path, owner, fail_stage="build", fail_message="找不到入口 build_model"
    )
    queued: list[str] = []
    monkeypatch.setattr("app.services.adapt.enqueue_admit", lambda version_id, settings=None: queued.append(version_id))
    monkeypatch.setattr("app.services.adapt.invalidate_after_write", lambda *args, **kwargs: None)
    result = apply_adapt(db, owner, version, model, consent=True, settings=settings)
    text = (tmp_path / "storage" / "models" / version.id / "model.py").read_text(encoding="utf-8")
    assert result["applied"] is True
    assert LAB_ADAPT_BEGIN in text
    assert version.status == "checking"
    assert version.entry_symbol == "lab_build_model"
    assert version.fail_stage is None
    assert queued == [version.id]
    assert db.query(AuditLog).filter(AuditLog.action == "adapt.apply").count() == 1
    assert class_source_unchanged(_source(), text, "DemoNet")


def test_ad04_apply_does_not_mark_runnable(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db, tmp_path, owner, fail_stage="build", fail_message="找不到入口 build_model"
    )
    monkeypatch.setattr("app.services.adapt.enqueue_admit", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.adapt.invalidate_after_write", lambda *args, **kwargs: None)
    apply_adapt(db, owner, version, model, consent=True, settings=settings)
    assert version.status != "runnable"


def test_ad05_load_has_no_apply(db: Session, tmp_path: Path) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db,
        tmp_path,
        owner,
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'module.head.weight'",
    )
    proposal = build_proposal(db, owner, version, model, settings=settings, use_llm=False)
    assert proposal["can_apply"] is False
    assert proposal["diff"] == ""
    assert "module." in " ".join(proposal["points"])
    with pytest.raises(AppError) as exc:
        apply_adapt(db, owner, version, model, consent=True, settings=settings)
    assert exc.value.code == "ADAPT_NOT_WHITELISTED"


def test_ad06_cannot_adapt_others(db: Session, tmp_path: Path) -> None:
    owner = _user(db, "stu")
    other = _user(db, "adv", role="advisor")
    model, version, settings = _version(
        db, tmp_path, owner, fail_stage="build", fail_message="找不到入口 build_model"
    )
    with pytest.raises(AppError) as exc:
        build_proposal(db, other, version, model, settings=settings, use_llm=False)
    assert exc.value.status_code == 404
    assert exc.value.code == "NOT_FOUND"


def test_alias_class_like_a3net_is_preferred() -> None:
    source = '''
import torch.nn as nn

class A3Net_Res2Net50(nn.Module):
    def __init__(self, num_classes=1, pretrained_backbone=False):
        super().__init__()
        self.head = nn.Conv2d(3, num_classes, 1)
        _ = pretrained_backbone

    def forward(self, x):
        s1 = self.head(x)
        return s1, s1

class A3Net(A3Net_Res2Net50):
    """Training-pipeline name."""
    pass
'''
    analysis = analyze_source(
        source,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    assert analysis.target is not None
    assert analysis.target.name == "A3Net"
    assert analysis.returns_sequence is True
    patch = render_adapter_patch(analysis)
    assert "A3Net(num_classes=num_classes, pretrained_backbone=False)" in patch


def test_generated_wrapper_takes_first_tensor() -> None:
    torch = pytest.importorskip("torch")
    analysis = analyze_source(
        _source(),
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    updated = append_patch(_source(), render_adapter_patch(analysis))
    namespace: dict = {}
    exec(compile(updated, "model.py", "exec"), namespace)  # noqa: S102
    model = namespace["lab_build_model"](num_classes=4, in_channels=3)
    output = model(torch.zeros(1, 3, 16, 16))
    assert tuple(output.shape) == (1, 4, 16, 16)


def test_ad08_patch_has_no_load_rewrite() -> None:
    analysis = analyze_source(
        _source(),
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    patch = render_adapter_patch(analysis)
    assert "load_state_dict" not in patch
    assert "strict=False" not in patch
    assert "module." not in patch


MEGA_SOURCE = '''
import torch.nn as nn

class Mega(nn.Module):
    def __init__(self, num_classes, in_channels=3, extra=True):
        super().__init__()
        self.extra = extra
        self.head = nn.Conv2d(in_channels, num_classes, 1)

    def forward(self, x):
        return self.head(x)

class MegaBase(Mega):
    def __init__(self, num_classes, in_channels=3):
        super().__init__(num_classes, in_channels, extra=False)

MODEL_REGISTRY = {"mega_base": MegaBase, "mega": Mega}
'''


def test_registry_hint_picks_ablation_variant_not_unified_class() -> None:
    hinted = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
        hint_model_name="mega_base",
    )
    assert hinted.target is not None
    assert hinted.target.name == "MegaBase"
    patch = render_adapter_patch(hinted)
    assert "MegaBase(" in patch
    assert "Mega(" not in patch.split("model =", 1)[1]

    unhinted = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    assert unhinted.target is not None
    assert unhinted.target.name == "Mega"


def test_load_without_adapt_block_stays_opinion_even_with_hint() -> None:
    analysis = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'head.weight'",
        status="cannot_start",
        hint_model_name="mega_base",
    )
    assert analysis.can_apply is False
    assert analysis.primary_kind == "opinion_only"


def test_wrong_variant_retargets_existing_adapt_block() -> None:
    first = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    wrapped = append_patch(MEGA_SOURCE, render_adapter_patch(first))
    assert "model = Mega(" in wrapped.split(LAB_ADAPT_BEGIN, 1)[1]

    again = analyze_source(
        wrapped,
        entry_symbol="lab_build_model",
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'stage1.0.dw.weight'. Unexpected key(s): 'stage1.0.0.weight'",
        status="cannot_start",
        hint_model_name="mega_base",
    )
    assert again.primary_kind == "wrong_variant"
    assert again.can_apply is True
    assert again.wrapped_class == "Mega"
    assert again.target is not None
    assert again.target.name == "MegaBase"
    patch = render_adapter_patch(again)
    assert "MegaBase(" in patch
    assert "load_state_dict" not in patch
    assert "strict" not in patch
    updated = apply_patch(wrapped, patch)
    assert updated.count(LAB_ADAPT_BEGIN) == 1
    assert "model = MegaBase(" in updated.split(LAB_ADAPT_BEGIN, 1)[1]
    assert "model = Mega(" not in updated.split(LAB_ADAPT_BEGIN, 1)[1]
    assert source_outside_adapt_unchanged(wrapped, updated)
    assert class_source_unchanged(wrapped, updated, "Mega")
    assert class_source_unchanged(wrapped, updated, "MegaBase")


def test_already_adapted_load_without_hint_stays_blocked() -> None:
    first = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    wrapped = append_patch(MEGA_SOURCE, render_adapter_patch(first))
    again = analyze_source(
        wrapped,
        entry_symbol="lab_build_model",
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'module.head.weight'",
        status="cannot_start",
    )
    assert again.can_apply is False
    assert again.primary_kind == "already_adapted"


def test_ad10_apply_replaces_adapt_block_only(
    db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    torch = pytest.importorskip("torch")
    owner = _user(db, "stu")
    first = analyze_source(
        MEGA_SOURCE,
        entry_symbol="build_model",
        fail_stage="build",
        fail_message="找不到入口 build_model",
        status="cannot_start",
    )
    wrapped = append_patch(MEGA_SOURCE, render_adapter_patch(first))
    spec = PreprocessSpecRow(
        id="neu_200",
        name="neu_200",
        height=200,
        width=200,
        apply_clahe=True,
        sp_threshold=0.02,
        dataset="neu",
        created_at=utcnow(),
    )
    model = Model(id="m-var", owner_id=owner.id, name="Mega", source="student", created_at=utcnow())
    version = ModelVersion(
        id="v-var",
        model_id=model.id,
        slug="mega-v1",
        entry_symbol="lab_build_model",
        num_classes=4,
        in_channels=3,
        input_h=200,
        input_w=200,
        preprocess_id=spec.id,
        requires_cuda=False,
        status="cannot_start",
        fail_stage="load",
        fail_message="Missing key(s) in state_dict: 'stage1.0.dw.weight'",
        source_sha256="abc",
        visibility="private",
        created_at=utcnow(),
    )
    db.add_all([spec, model, version])
    db.commit()
    settings = Settings(storage_root=str(tmp_path / "storage"), llm_api_key="")
    dest = tmp_path / "storage" / "models" / version.id
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "model.py").write_text(wrapped, encoding="utf-8")
    torch.save({"model_state": {"ok": torch.tensor(1.0)}, "model_name": "mega_base"}, dest / "weights.pth")
    monkeypatch.setattr("app.services.adapt.enqueue_admit", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.services.adapt.invalidate_after_write", lambda *args, **kwargs: None)
    result = apply_adapt(db, owner, version, model, consent=True, settings=settings)
    text = (dest / "model.py").read_text(encoding="utf-8")
    assert result["applied"] is True
    assert result["primary_kind"] == "wrong_variant"
    assert text.count(LAB_ADAPT_BEGIN) == 1
    assert "model = MegaBase(" in text
    assert source_outside_adapt_unchanged(wrapped, text)


def test_static_fail_points_include_scanner_text(db: Session, tmp_path: Path) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db,
        tmp_path,
        owner,
        fail_stage="static",
        fail_message="不允许的导入 compare.moesteelunet_last 第 13 行。请只保留网络结构与 forward。",
    )
    proposal = build_proposal(db, owner, version, model, settings=settings, use_llm=False)
    assert proposal["can_apply"] is False
    joined = " ".join(proposal["points"])
    assert "compare.moesteelunet_last" in joined
    assert "不会自动改源码" in joined


def test_opinion_only_still_uses_llm_copy(db: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _user(db, "stu")
    model, version, settings = _version(
        db,
        tmp_path,
        owner,
        fail_stage="static",
        fail_message="不允许的导入 compare.moesteelunet_last",
    )
    settings = settings.model_copy(update={"llm_api_key": "sk-test"})
    monkeypatch.setattr(
        "app.services.adapt.draft_adapt_copy",
        lambda *args, **kwargs: "- 把 compare.moesteelunet_last 的网络类拷进这一份 py\n- 不要再从 compare 导入",
    )
    proposal = build_proposal(db, owner, version, model, settings=settings, use_llm=True)
    assert proposal["can_apply"] is False
    assert proposal["llm_status"] == "ok"
    assert any("拷进这一份 py" in item for item in proposal["points"])

