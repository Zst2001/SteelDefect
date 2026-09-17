from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        stage: str,
        status_code: int = 400,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.stage = stage
        self.status_code = status_code

    def as_dict(self) -> dict:
        return {"stage": self.stage, "code": self.code, "message": self.message}


def error_payload(message: str, *, code: str, stage: str) -> dict:
    return {"stage": stage, "code": code, "message": message}


async def app_error_handler(_request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.as_dict())


def http_error(status_code: int, message: str, *, code: str, stage: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail=error_payload(message, code=code, stage=stage))
