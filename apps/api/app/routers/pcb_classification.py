from fastapi import APIRouter, Depends, File, Header, Request, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.pcb_classification import MAX_BYTES, catalog_payload, create_batch, create_task, serialize_task

router = APIRouter(prefix="/scenes/pcb/classification", tags=["pcb-classification"])


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: str = Field(min_length=1, max_length=36)
    model_id: str = Field(min_length=1, max_length=32)


@router.get("/models")
def models(_user: User = Depends(get_current_user)):
    return catalog_payload()


@router.post("/uploads")
async def upload(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)):
    try:
        form = await request.form()
        if set(form) != {"file"} or len(form.getlist("file")) != 1:
            raise AppError("仅支持一张已裁剪 ROI，不接受 GT、脚本或批量输入", code="PCB_CLS_IMAGE_COUNT", stage="file", status_code=400)
        return create_batch(db, user, file.filename or "", await file.read(MAX_BYTES + 1), file.content_type)
    finally:
        await file.close()


@router.post("/tasks")
def create(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    task = create_task(db, user, batch_id=body.batch_id, model_id=body.model_id, idempotency_key=idempotency_key)
    return serialize_task(db, task)
