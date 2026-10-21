"""Administrator endpoints - every route requires a server-side admin role."""
from __future__ import annotations

import datetime as dt

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_hdfs, require_admin
from app.core.errors import Conflict
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models.audit import AuditEvent
from app.models.file import FileRecord
from app.models.user import User
from app.schemas.admin import (
    AdminStatsResponse,
    AdminUserListResponse,
    AdminUserResponse,
    AuditEventListResponse,
    AuditEventResponse,
    HdfsSummary,
    RoleUpdateRequest,
)
from app.schemas.file import HdfsStatusResponse
from app.services import audit_service
from app.services.hdfs_service import HdfsStorage

router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.get("/stats", response_model=AdminStatsResponse)
def admin_stats(_: User = Depends(require_admin),
                db: Session = Depends(get_db),
                hdfs: HdfsStorage = Depends(get_hdfs)) -> AdminStatsResponse:
    user_count = int(db.scalar(select(func.count(User.id))) or 0)
    admin_count = int(db.scalar(
        select(func.count(User.id)).where(User.role == "admin")) or 0)
    file_count = int(db.scalar(select(func.count(FileRecord.id))) or 0)
    used = int(db.scalar(
        select(func.coalesce(func.sum(FileRecord.size_bytes), 0))) or 0)
    storage = hdfs.status()
    return AdminStatsResponse(
        user_count=user_count,
        admin_count=admin_count,
        file_count=file_count,
        storage_used_bytes=used,
        hdfs=HdfsSummary(
            adapter=storage["adapter"],
            healthy=storage["healthy"],
            message=storage["message"],
        ),
        generated_at=dt.datetime.now(dt.timezone.utc),
    )


@router.get("/users", response_model=AdminUserListResponse)
def admin_users(_: User = Depends(require_admin),
                db: Session = Depends(get_db)) -> AdminUserListResponse:
    rows = db.execute(
        select(
            User,
            func.count(FileRecord.id),
            func.coalesce(func.sum(FileRecord.size_bytes), 0),
        )
        .outerjoin(FileRecord, FileRecord.owner_id == User.id)
        .group_by(User.id)
        .order_by(User.username.asc())
    ).all()
    items = [
        AdminUserResponse(
            id=u.id, username=u.username, role=u.role, is_active=u.is_active,
            created_at=u.created_at, file_count=int(fc),
            storage_used_bytes=int(sz),
        )
        for u, fc, sz in rows
    ]
    return AdminUserListResponse(items=items, total=len(items))


@router.get("/hdfs-status", response_model=HdfsStatusResponse)
def hdfs_status(_: User = Depends(require_admin),
                hdfs: HdfsStorage = Depends(get_hdfs)) -> HdfsStatusResponse:
    return HdfsStatusResponse(**hdfs.status())


@router.get("/audit", response_model=AuditEventListResponse)
def audit_events(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = Query(default=None, max_length=48),
) -> AuditEventListResponse:
    stmt = select(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(limit)
    if event_type:
        stmt = stmt.where(AuditEvent.event_type == event_type)
    events = list(db.scalars(stmt).all())
    total = int(db.scalar(select(func.count(AuditEvent.id))) or 0)
    return AuditEventListResponse(
        items=[AuditEventResponse.model_validate(e) for e in events],
        total=total,
    )


@router.patch("/users/{user_id}/role", response_model=AdminUserResponse)
def update_role(
    user_id: str,
    payload: RoleUpdateRequest,
    request: Request,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminUserResponse:
    target = db.get(User, user_id)
    if target is None:
        from app.core.errors import NotFound

        raise NotFound("User not found.")
    if target.id == admin.id and payload.role != "admin":
        raise Conflict("You cannot remove your own administrator role.")
    target.role = payload.role
    db.commit()
    db.refresh(target)
    audit_service.record(
        db, "admin_role_change", actor=admin, source_ip=client_ip(request),
        detail=f"target={target.username} new_role={payload.role}",
    )
    return AdminUserResponse(
        id=target.id, username=target.username, role=target.role,
        is_active=target.is_active, created_at=target.created_at,
        file_count=0, storage_used_bytes=0,
    )
