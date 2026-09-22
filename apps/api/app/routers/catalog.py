from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.authz import require_advisor
from app.db.models import User
from app.deps import get_db
from app.services.catalog import (
    create_dataset,
    create_fund,
    create_model,
    create_work,
    delete_dataset,
    delete_fund,
    delete_model,
    delete_work,
    get_home_payload,
    serialize_dataset,
    serialize_fund,
    serialize_model,
    serialize_stats,
    serialize_work,
    update_dataset,
    update_fund,
    update_model,
    update_stats,
    update_work,
)

router = APIRouter(prefix="/catalog", tags=["catalog"])


class StatsIn(BaseModel):
    research_models: int = Field(ge=0, le=99999)
    papers: int = Field(ge=0, le=99999)


class ModelIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    year: int | None = Field(default=None, ge=1990, le=2100)
    task_type: str = Field(pattern=r"^(classification|detection|segmentation)$")
    backbone: str | None = Field(default=None, max_length=128)
    keywords: str | None = Field(default=None, max_length=512)
    paper_url: str | None = Field(default=None, max_length=512)
    code_url: str | None = Field(default=None, max_length=512)
    dataset: str | None = Field(default=None, max_length=255)
    detail: str | None = Field(default=None, max_length=4000)
    is_group_work: bool = False
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class ModelPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    year: int | None = Field(default=None, ge=1990, le=2100)
    task_type: str | None = Field(default=None, pattern=r"^(classification|detection|segmentation)$")
    backbone: str | None = Field(default=None, max_length=128)
    keywords: str | None = Field(default=None, max_length=512)
    paper_url: str | None = Field(default=None, max_length=512)
    code_url: str | None = Field(default=None, max_length=512)
    dataset: str | None = Field(default=None, max_length=255)
    detail: str | None = Field(default=None, max_length=4000)
    is_group_work: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class DatasetIn(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    task_type: str = Field(pattern=r"^(classification|detection|segmentation)$")
    source_object: str | None = Field(default=None, max_length=255)
    numbers_text: str | None = Field(default=None, max_length=512)
    image_count: int | None = Field(default=None, ge=0, le=10_000_000)
    class_count: int | None = Field(default=None, ge=0, le=1000)
    defect_types: str | None = Field(default=None, max_length=512)
    size: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=512)
    access_note: str | None = Field(default=None, max_length=128)
    detail: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class DatasetPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    task_type: str | None = Field(default=None, pattern=r"^(classification|detection|segmentation)$")
    source_object: str | None = Field(default=None, max_length=255)
    numbers_text: str | None = Field(default=None, max_length=512)
    image_count: int | None = Field(default=None, ge=0, le=10_000_000)
    class_count: int | None = Field(default=None, ge=0, le=1000)
    defect_types: str | None = Field(default=None, max_length=512)
    size: str | None = Field(default=None, max_length=128)
    url: str | None = Field(default=None, max_length=512)
    access_note: str | None = Field(default=None, max_length=128)
    detail: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class WorkIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = Field(pattern=r"^(paper|patent|software|award|other)$")
    year: int | None = Field(default=None, ge=1990, le=2100)
    venue: str | None = Field(default=None, max_length=255)
    authors: str | None = Field(default=None, max_length=512)
    summary: str | None = Field(default=None, max_length=4000)
    link_url: str | None = Field(default=None, max_length=512)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class WorkPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    kind: str | None = Field(default=None, pattern=r"^(paper|patent|software|award|other)$")
    year: int | None = Field(default=None, ge=1990, le=2100)
    venue: str | None = Field(default=None, max_length=255)
    authors: str | None = Field(default=None, max_length=512)
    summary: str | None = Field(default=None, max_length=4000)
    link_url: str | None = Field(default=None, max_length=512)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class FundIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source: str = Field(pattern=r"^(nsfc|provincial|ministry|horizontal|other)$")
    number: str | None = Field(default=None, max_length=128)
    role: str = Field(default="pi", pattern=r"^(pi|participant)$")
    start_year: int | None = Field(default=None, ge=1990, le=2100)
    end_year: int | None = Field(default=None, ge=1990, le=2100)
    status: str = Field(default="ongoing", pattern=r"^(ongoing|completed)$")
    amount_text: str | None = Field(default=None, max_length=64)
    detail: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


class FundPatchIn(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    source: str | None = Field(default=None, pattern=r"^(nsfc|provincial|ministry|horizontal|other)$")
    number: str | None = Field(default=None, max_length=128)
    role: str | None = Field(default=None, pattern=r"^(pi|participant)$")
    start_year: int | None = Field(default=None, ge=1990, le=2100)
    end_year: int | None = Field(default=None, ge=1990, le=2100)
    status: str | None = Field(default=None, pattern=r"^(ongoing|completed)$")
    amount_text: str | None = Field(default=None, max_length=64)
    detail: str | None = Field(default=None, max_length=4000)
    sort_order: int | None = Field(default=None, ge=0, le=99999)


@router.get("")
def get_catalog(db: Session = Depends(get_db)) -> dict:
    return get_home_payload(db)


@router.put("/stats")
def put_stats(
    body: StatsIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_stats(update_stats(db, research_models=body.research_models, papers=body.papers))


@router.post("/models")
def post_model(
    body: ModelIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    row = create_model(db, **body.model_dump())
    return serialize_model(row)


@router.patch("/models/{model_id}")
def patch_model(
    model_id: str,
    body: ModelPatchIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_model(update_model(db, model_id, **body.model_dump(exclude_unset=True)))


@router.delete("/models/{model_id}")
def remove_model(
    model_id: str,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    delete_model(db, model_id)
    return {"ok": True}


@router.post("/datasets")
def post_dataset(
    body: DatasetIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_dataset(create_dataset(db, **body.model_dump()))


@router.patch("/datasets/{dataset_id}")
def patch_dataset(
    dataset_id: str,
    body: DatasetPatchIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    payload = body.model_dump(exclude_unset=True)
    return serialize_dataset(update_dataset(db, dataset_id, **payload))


@router.delete("/datasets/{dataset_id}")
def remove_dataset(
    dataset_id: str,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    delete_dataset(db, dataset_id)
    return {"ok": True}


@router.post("/works")
def post_work(
    body: WorkIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_work(create_work(db, **body.model_dump()))


@router.patch("/works/{work_id}")
def patch_work(
    work_id: str,
    body: WorkPatchIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_work(update_work(db, work_id, **body.model_dump(exclude_unset=True)))


@router.delete("/works/{work_id}")
def remove_work(
    work_id: str,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    delete_work(db, work_id)
    return {"ok": True}


@router.post("/funds")
def post_fund(
    body: FundIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_fund(create_fund(db, **body.model_dump()))


@router.patch("/funds/{fund_id}")
def patch_fund(
    fund_id: str,
    body: FundPatchIn,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    return serialize_fund(update_fund(db, fund_id, **body.model_dump(exclude_unset=True)))


@router.delete("/funds/{fund_id}")
def remove_fund(
    fund_id: str,
    db: Session = Depends(get_db),
    _advisor: User = Depends(require_advisor),
) -> dict:
    delete_fund(db, fund_id)
    return {"ok": True}
