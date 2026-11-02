from fastapi import APIRouter, Depends, File, Header, UploadFile, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.pcb_segmentation import MAX_IMAGE_BYTES, catalog_payload, create_batch, create_pcb_task, serialize_pcb_task

router = APIRouter(prefix="/scenes/pcb/segmentation", tags=["pcb-segmentation"])


class TaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str = Field(min_length=1, max_length=36)
    model_id: str = Field(min_length=1, max_length=32)
    include_cam: StrictBool = False


@router.get("/models")
def models(_user: User = Depends(get_current_user)):
    return catalog_payload()


@router.post("/uploads")
async def upload(request: Request, file: UploadFile = File(...), gt: UploadFile | None = File(None),
                 db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    try:
        form = await request.form()
        if len(form.getlist("file")) != 1 or len(form.getlist("gt")) > 1 or set(form) - {"file", "gt"}:
            raise AppError("仅支持一张 PCB 图片及至多一张 GT", code="PCB_IMAGE_COUNT", stage="file", status_code=400)
        content = (file.filename or "image", await file.read(MAX_IMAGE_BYTES + 1))
        mask = (gt.filename or "gt", await gt.read(MAX_IMAGE_BYTES + 1)) if gt else None
        return create_batch(db, user, content, mask)
    finally:
        await file.close()
        if gt:
            await gt.close()


@router.post("/tasks")
def create(body: TaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
           idempotency_key: str | None = Header(default=None, alias="Idempotency-Key")):
    task = create_pcb_task(db, user, batch_id=body.batch_id, model_id=body.model_id,
                           include_cam=body.include_cam, idempotency_key=idempotency_key)
    return serialize_pcb_task(db, task)
