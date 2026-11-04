import json

from fastapi import APIRouter, Depends, File, Header, UploadFile, Request, Query
from starlette.datastructures import UploadFile as StarletteUploadFile
from starlette.formparsers import MultiPartException
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy.orm import Session

from app.authz import get_current_user
from app.db.models import User
from app.deps import get_db
from app.errors import AppError
from app.services.pcb_segmentation import MAX_IMAGE_BYTES, catalog_payload, create_batch, create_pcb_task, serialize_pcb_task
from app.services import pcb_batch

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


class BatchTaskIn(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    batch_id: str = Field(min_length=1,max_length=36)
    model_ids: list[str] = Field(min_length=1,max_length=3)
    include_cam: bool = False
    accept_unsupported_cam: bool = False


@router.post("/uploads/batch")
async def upload_batch(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    # Bound multipart parser independently of the client Content-Length header.
    wire_limit=pcb_batch.limits()['max_batch_bytes']+1024*1024
    declared=request.headers.get('content-length')
    if declared:
        try:declared_size=int(declared)
        except ValueError as exc:raise pcb_batch.bad('Content-Length 无效') from exc
        if declared_size<0 or declared_size>wire_limit:raise pcb_batch.bad('上传请求超过整批上限','PCB_BATCH_SIZE',413)
    original_stream=request.stream
    async def bounded_stream():
        received=0
        async for chunk in original_stream():
            received+=len(chunk)
            if received>wire_limit:
                # Starlette closes already-spooled files when this exception propagates.
                raise MultiPartException('PCB multipart request exceeds batch byte limit')
            yield chunk
    request.stream=bounded_stream
    async with request.form(max_files=20,max_fields=1,max_part_size=65536) as form:
        values=form.getlist('manifest')
        if len(values)!=1 or not isinstance(values[0],str) or len(values[0])>65536:
            raise pcb_batch.bad('缺少唯一的 manifest JSON')
        try:manifest=json.loads(values[0])
        except (ValueError,TypeError) as exc:raise pcb_batch.bad('manifest JSON 格式无效') from exc
        _,fields=pcb_batch.validate_manifest(manifest)
        if set(form)!={'manifest',*fields}:raise pcb_batch.bad('文件字段与 manifest 不一致')
        files={};total=0
        for field in fields:
            entries=form.getlist(field)
            if len(entries)!=1 or not isinstance(entries[0],StarletteUploadFile):raise pcb_batch.bad('每个文件字段须恰好一份上传')
            uploaded=entries[0]
            data=await uploaded.read(pcb_batch.MAX_FILE_BYTES+1)
            total+=len(data)
            if len(data)>pcb_batch.MAX_FILE_BYTES:raise pcb_batch.bad('单文件不得超过 10 MiB','PCB_IMAGE_SIZE')
            if total>pcb_batch.limits()['max_batch_bytes']:raise pcb_batch.bad('整批不得超过 50 MiB','PCB_BATCH_SIZE')
            files[field]=(uploaded.filename or '',data,uploaded.content_type)
        return pcb_batch.create_group(db,user,manifest,files)


@router.post("/tasks/batch")
def create_tasks_batch(body: BatchTaskIn, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                       idempotency_key: str = Header(alias='Idempotency-Key',min_length=1,max_length=128)):
    return pcb_batch.submit_group(db,user,**body.model_dump(),idempotency_key=idempotency_key)


@router.get("/batches/{batch_id}")
def batch_detail(batch_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user),
                 page: int = Query(default=1,ge=1), page_size: int = Query(default=50,ge=1,le=100)):
    return pcb_batch.get_group(db,user,batch_id,page=page,page_size=page_size)
