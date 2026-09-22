from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
import torch
import torch.nn as nn
from admit.perf import WARMUP_RUNS, TIMED_RUNS, count_all_parameters, fps_from_latency_ms, measure_cpu_forward
from admit.runner import main as admit_main
from app.db.models import Model, ModelPerfProfile, ModelVersion, PreprocessSpecRow, User, Weight
from app.db.session import Base
from app.errors import AppError
from app.services.models import serialize_version
from app.services.perf import apply_measure_result, get_or_create_profile, request_measure, serialize_perf
from app.util_time import new_id, utcnow
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

TINY_PY = """
import torch.nn as nn

class Tiny(nn.Module):
    def __init__(self, num_classes=4, in_channels=3):
        super().__init__()
        self.conv = nn.Conv2d(in_channels, num_classes, 1)

    def forward(self, x):
        return self.conv(x)

def build_model(num_classes=4, in_channels=3):
    return Tiny(num_classes=num_classes, in_channels=in_channels)
"""


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


def _seed_version(
    db: Session,
    *,
    status: str = "runnable",
    source: str = "builtin",
    requires_cuda: bool = False,
    param_count: int | None = None,
) -> tuple[Model, ModelVersion]:
    user = User(
        id=new_id(),
        username="advisor",
        password_hash="x",
        role="advisor",
        status="active",
        created_at=utcnow(),
    )
    preprocess = PreprocessSpecRow(
        id=new_id(),
        name="neu_200",
        height=200,
        width=200,
        apply_clahe=True,
        sp_threshold=0.02,
        dataset="neu",
        created_at=utcnow(),
    )
    model = Model(
        id=new_id(),
        name="U-Net",
        owner_id=user.id if source == "student" else None,
        source=source,
        created_at=utcnow(),
    )
    version = ModelVersion(
        id=new_id(),
        model_id=model.id,
        slug="unet" if source == "builtin" else "student",
        entry_symbol="build_model",
        num_classes=4,
        in_channels=3,
        input_h=200,
        input_w=200,
        preprocess_id=preprocess.id,
        requires_cuda=requires_cuda,
        status=status,
        visibility="public" if source == "builtin" else "private",
        created_at=utcnow(),
    )
    weight = Weight(
        id=new_id(),
        version_id=version.id,
        file_uri="asset:baselines/neu/best_unet.pth",
        sha256="abc",
        param_count=param_count,
    )
    db.add_all([user, preprocess, model, version, weight])
    db.commit()
    db.refresh(version)
    return model, version


def test_count_includes_frozen_parameters() -> None:
    model = nn.Conv2d(3, 4, 1)
    model.weight.requires_grad = False
    trainable = int(sum(p.numel() for p in model.parameters() if p.requires_grad))
    total = count_all_parameters(model)
    assert total == int(sum(p.numel() for p in model.parameters()))
    assert total > trainable


def test_cpu_forward_protocol_shape() -> None:
    model = nn.Conv2d(3, 4, 1)
    stats = measure_cpu_forward(model, in_channels=3, height=16, width=16)
    assert stats["device"] == "cpu"
    assert stats["input_kind"] == "dummy"
    assert stats["batch"] == 1
    assert stats["warmup_runs"] == WARMUP_RUNS
    assert stats["timed_runs"] == TIMED_RUNS
    assert stats["input_h"] == 16
    assert stats["input_w"] == 16
    assert stats["latency_ms_per_image"] > 0
    assert len(stats["timings_ms"]) == TIMED_RUNS
    assert "fps" not in stats


def test_fps_is_inverse_of_latency() -> None:
    assert fps_from_latency_ms(250.0) == 4.0
    assert fps_from_latency_ms(None) is None
    assert fps_from_latency_ms(0) is None


def test_runner_perf_mode(tmp_path: Path) -> None:
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    (in_dir / "model.py").write_text(TINY_PY, encoding="utf-8")
    ns: dict = {}
    exec(TINY_PY, ns)
    built = ns["build_model"]()
    torch.save({"model_state": built.state_dict()}, in_dir / "weights.pth")
    (in_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_name": "model.py",
                "weight_name": "weights.pth",
                "entry_symbol": "build_model",
                "num_classes": 4,
                "in_channels": 3,
                "input_h": 8,
                "input_w": 8,
            }
        ),
        encoding="utf-8",
    )
    code = admit_main(["perf", "--in", str(in_dir), "--out", str(out_dir)])
    assert code == 0
    payload = json.loads((out_dir / "result.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["param_count"] == count_all_parameters(built)
    assert payload["latency_ms_per_image"] > 0
    assert payload["device"] == "cpu"
    assert payload["flops"] is None


def test_serialize_unmeasured_has_no_fps(db: Session) -> None:
    model, version = _seed_version(db)
    payload = serialize_version(db, version, model)
    assert payload["perf"]["status"] == "unmeasured"
    assert payload["perf"]["can_measure"] is True
    assert payload["perf"]["latency_ms_per_image"] is None
    assert payload["perf"]["fps_per_image"] is None
    assert payload["fps_per_image"] is None
    assert payload["flops"] == "未测量"
    assert "本机 CPU" in payload["perf"]["disclaimer"]


def test_request_measure_rejects_not_runnable(db: Session) -> None:
    model, version = _seed_version(db, status="cannot_start")
    with pytest.raises(AppError) as exc:
        request_measure(db, version, model)
    assert exc.value.code == "NOT_RUNNABLE"


def test_request_measure_rejects_cuda(db: Session) -> None:
    model, version = _seed_version(db, requires_cuda=True)
    with pytest.raises(AppError) as exc:
        request_measure(db, version, model)
    assert exc.value.code == "CUDA_REQUIRED"


def test_request_measure_enqueues(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    model, version = _seed_version(db)
    queued: list[str] = []
    monkeypatch.setattr(
        "app.services.perf.enqueue_perf",
        lambda version_id, settings=None: queued.append(version_id) or "job-1",
    )
    profile = request_measure(db, version, model)
    assert queued == [version.id]
    assert profile.status == "queued"
    assert profile.job_id == "job-1"
    again = request_measure(db, version, model)
    assert again.status == "queued"
    assert queued == [version.id]


def test_get_or_create_recovers_from_unique_conflict(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    _model, version = _seed_version(db)
    first = get_or_create_profile(db, version)
    db.commit()
    first_id = first.id
    version_id = version.id
    hits = {"n": 0}

    def load(_db, vid):
        hits["n"] += 1
        if hits["n"] == 1:
            return None
        return (
            _db.query(ModelPerfProfile)
            .filter(ModelPerfProfile.version_id == vid)
            .one_or_none()
        )

    monkeypatch.setattr("app.services.perf._load_profile", load)
    db.expunge_all()
    recovered = get_or_create_profile(db, db.get(ModelVersion, version_id))
    assert recovered.id == first_id
    assert recovered.version_id == version_id


def test_apply_result_fills_empty_weight_params_only(db: Session) -> None:
    model, version = _seed_version(db, param_count=99)
    apply_measure_result(
        db,
        version,
        model,
        {
            "param_count": 16,
            "weight_bytes": 128,
            "latency_ms_per_image": 12.5,
            "flops": None,
            "warmup_runs": 3,
            "timed_runs": 10,
            "batch": 1,
            "input_h": 200,
            "input_w": 200,
            "input_kind": "dummy",
            "device": "cpu",
            "env": {"device": "cpu", "torch": "2.0"},
        },
    )
    db.commit()
    weight = db.query(Weight).filter(Weight.version_id == version.id).one()
    assert weight.param_count == 99
    perf = serialize_perf(db, version, model)
    assert perf["status"] == "success"
    assert perf["param_count"] == 16
    assert perf["latency_ms_per_image"] == 12.5
    assert perf["fps_per_image"] == 80.0
    assert perf["weight_bytes"] == 128
    card = serialize_version(db, version, model)
    assert card["param_count"] == 16
    assert card["fps_per_image"] == 80.0
    assert card["flops"] == "未测量"
