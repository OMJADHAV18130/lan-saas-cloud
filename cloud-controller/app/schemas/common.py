from __future__ import annotations

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str
    app: str
    environment: str
    database: str
    storage: dict
    max_upload_bytes: int
    version: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
