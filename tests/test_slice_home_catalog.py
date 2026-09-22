from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "packages"), str(ROOT / "third_party"), str(ROOT / "apps" / "api")]

import pytest
from app.db.session import Base
from app.errors import AppError
from app.services.catalog import (
    GROUP_WORK_NAMES,
    create_fund,
    create_model,
    create_work,
    delete_fund,
    delete_model,
    delete_work,
    get_home_payload,
    seed_catalog,
    update_stats,
)
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool


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


def test_seed_catalog_starts_stats_at_zero_and_marks_group_works(db: Session) -> None:
    seed_catalog(db)
    db.commit()
    payload = get_home_payload(db)
    assert payload["stats"]["research_models"] == 0
    assert payload["stats"]["papers"] == 0
    names = {row["name"] for row in payload["models"]}
    assert GROUP_WORK_NAMES <= names
    group = [row for row in payload["models"] if row["is_group_work"]]
    assert {row["name"] for row in group} == GROUP_WORK_NAMES
    eami = next(row for row in payload["models"] if row["name"] == "EAMINet")
    assert eami["year"] == 2021
    assert eami["task_type"] == "segmentation"
    assert eami["paper_url"] is None
    assert eami["code_url"].startswith("https://github.com/")
    datasets = payload["datasets"]
    assert any(row["name"] == "NEU-CLS" and row["task_type"] == "classification" for row in datasets)
    assert any(row["name"] == "NEU-DET" and row["image_count"] == 1800 for row in datasets)
    neu_seg = next(row for row in datasets if row["name"] == "NEU_Seg")
    assert neu_seg["class_count"] == 3
    assert neu_seg["defect_types"] is None
    assert payload["works"] == []
    assert payload["funds"] == []


def test_stats_and_model_crud_do_not_invent_empty_fields(db: Session) -> None:
    seed_catalog(db)
    db.commit()
    stats = update_stats(db, research_models=5, papers=5)
    assert stats.research_models == 5
    created = create_model(
        db,
        name="LabNet",
        year=2026,
        task_type="segmentation",
        backbone="ResNet-34",
        keywords="edge",
        paper_url=None,
        code_url="https://github.com/example/labnet",
        dataset=None,
        detail=None,
        is_group_work=True,
    )
    assert created.paper_url is None
    assert created.dataset is None
    payload = get_home_payload(db)
    assert payload["stats"]["papers"] == 5
    assert any(row["name"] == "LabNet" and row["is_group_work"] for row in payload["models"])
    delete_model(db, created.id)
    payload = get_home_payload(db)
    assert all(row["name"] != "LabNet" for row in payload["models"])


def test_invalid_task_type_rejected(db: Session) -> None:
    with pytest.raises(AppError) as exc:
        create_model(
            db,
            name="Bad",
            year=2020,
            task_type="ocr",
            backbone=None,
            keywords=None,
            paper_url=None,
            code_url=None,
            dataset=None,
            detail=None,
            is_group_work=False,
        )
    assert exc.value.code == "BAD_TASK_TYPE"


def test_works_and_funds_show_facts_without_code_or_invented_fields(db: Session) -> None:
    seed_catalog(db)
    db.commit()
    work = create_work(
        db,
        name="钢铁表面缺陷分割方法",
        kind="paper",
        year=2024,
        venue="某期刊",
        authors="张三, 李四",
        summary="面向热轧带钢缺陷的分割方法。",
        link_url=None,
    )
    assert work.link_url is None
    fund = create_fund(
        db,
        name="工业视觉检测关键技术研究",
        source="nsfc",
        number="12345678",
        role="pi",
        start_year=2023,
        end_year=2026,
        status="ongoing",
        amount_text=None,
        detail="导师主持的在研项目。",
    )
    assert fund.amount_text is None
    payload = get_home_payload(db)
    shown_work = next(row for row in payload["works"] if row["name"] == "钢铁表面缺陷分割方法")
    assert shown_work["kind"] == "paper"
    assert shown_work["link_url"] is None
    assert "code_url" not in shown_work
    shown_fund = next(row for row in payload["funds"] if row["name"] == "工业视觉检测关键技术研究")
    assert shown_fund["source"] == "nsfc"
    assert shown_fund["role"] == "pi"
    assert shown_fund["amount_text"] is None
    delete_work(db, work.id)
    delete_fund(db, fund.id)
    payload = get_home_payload(db)
    assert payload["works"] == []
    assert payload["funds"] == []


def test_homepage_research_section_has_no_code_and_shows_funds() -> None:
    page = (ROOT / "apps" / "web" / "src" / "views" / "HomeView.vue").read_text(encoding="utf-8")
    assert "课题组研究成果" in page
    assert "导师科研基金" in page
    assert "不提供代码仓库" in page
    assert "openCreateModel(true)" not in page
    assert 'code_url' not in page.split("id=\"research-works\"")[1].split("id=\"defect-models\"")[0]
    assert "智能感知与精密工业检测实验室" in page
    assert "IPPI Lab" in page
    assert "详细介绍" in page
    assert "62202211" in page
    assert "20242BCC32021" in page
