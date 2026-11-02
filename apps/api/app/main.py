from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.bootstrap import ROOT  # noqa: F401  # path bootstrap
from app.config import get_settings
from app.errors import AppError, app_error_handler, error_payload
from app.routers import admin, assistant, auth, catalog, classification, datasets, demo, health, me, models, records, scenes, tasks, uploads
from app.routers import pcb_segmentation
from app.routers import pcb_classification


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings = get_settings()
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    if settings.seed_on_start:
        from app.db.session import SessionLocal
        from app.services.seed import seed_all

        db = SessionLocal()
        try:
            seed_all(db, settings)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    yield


app = FastAPI(title="Steel Lab API", version="0.1.0", lifespan=lifespan)
settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_exception_handler(AppError, app_error_handler)


@app.exception_handler(RequestValidationError)
async def validation_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content=error_payload(str(exc.errors()), code="VALIDATION", stage="file"),
    )


app.include_router(health.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(admin.router, prefix="/api")
app.include_router(catalog.router, prefix="/api")
app.include_router(classification.router, prefix="/api")
app.include_router(pcb_segmentation.router, prefix="/api")
app.include_router(pcb_classification.router, prefix="/api")
app.include_router(demo.router, prefix="/api")
app.include_router(me.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(datasets.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(records.router, prefix="/api")
app.include_router(scenes.router, prefix="/api")
app.include_router(assistant.router, prefix="/api")
