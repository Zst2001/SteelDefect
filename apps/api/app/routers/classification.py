from fastapi import APIRouter, Depends, File, Form, Header, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.classification import (MAX_IMAGE_BYTES, MAX_IMAGES, catalog_payload, create_batch,
                                         create_classification_task, serialize_classification_task)

router = APIRouter(prefix="/classification", tags=["classification"])


class ClassificationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str = Field(min_length=1, max_length=36)
    model_slugs: list[str] = Field(min_length=1, max_length=3)


@router.get("/models")
def models(user: User = Depends(get_current_user)):
    return catalog_payload()


@router.post("/uploads")
async def upload(files: list[UploadFile] = File(...), labels_json: str | None = Form(None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        if not 1 <= len(files) <= MAX_IMAGES:
            raise AppError("请上传 1–50 张分类图片", code="CLASSIFICATION_IMAGE_COUNT", stage="file", status_code=400)
        contents = []
        for file in files:
            content = await file.read(MAX_IMAGE_BYTES + 1)
            if len(content) > MAX_IMAGE_BYTES:
                raise AppError("单张图片不能超过 10 MiB", code="CLASSIFICATION_IMAGE_SIZE", stage="file", status_code=400)
            contents.append((file.filename or "image", content))
        return create_batch(db, user, contents, labels_json)
    finally:
        for file in files:
            await file.close()


@router.post("/tasks")
def create(body: ClassificationIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    task = create_classification_task(db, user, batch_id=body.batch_id, model_slugs=body.model_slugs,
                                      idempotency_key=idempotency_key)
    return serialize_classification_task(db, task)
