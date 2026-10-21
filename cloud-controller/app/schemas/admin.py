from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminStatsResponse(BaseModel):
    user_count: int
    admin_count: int
    file_count: int
    storage_used_bytes: int
    hdfs: "HdfsSummary"
    generated_at: datetime


class HdfsSummary(BaseModel):
    adapter: str
    healthy: bool | None
    message: str


class AdminUserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    is_active: bool
    created_at: datetime
    file_count: int = 0
    storage_used_bytes: int = 0


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int


class RoleUpdateRequest(BaseModel):
    role: str = Field(pattern="^(user|admin)$")


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    event_type: str
    actor_id: str | None
    actor_username: str | None
    source_ip: str | None
    detail: str | None
    success: bool
    created_at: datetime


class AuditEventListResponse(BaseModel):
    items: list[AuditEventResponse]
    total: int


AdminStatsResponse.model_rebuild()
