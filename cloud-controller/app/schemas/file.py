from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class FileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    original_name: str
    size_bytes: int
    content_type: str
    sha256: str
    created_at: datetime


class FileListResponse(BaseModel):
    items: list[FileResponse]
    total: int
    storage_used_bytes: int
    storage_quota_bytes: int
    sort_by: str
    order: str
    search: str | None = None


class UserStatsResponse(BaseModel):
    total_files: int
    storage_used_bytes: int
    storage_quota_bytes: int
    recent_files: list[FileResponse]


class SortField(str):
    pass


SortBy = Literal["name", "size", "date"]
SortOrder = Literal["asc", "desc"]


class UploadResponse(BaseModel):
    file: FileResponse
    message: str = "File uploaded successfully."


class DeleteResponse(BaseModel):
    message: str
    file_id: str


class HdfsStatusResponse(BaseModel):
    adapter: Literal["webhdfs", "mock"]
    mode_label: str
    healthy: bool | None
    namenode_url: str | None
    root: str
    latency_ms: float | None
    datanodes: dict | None
    message: str
