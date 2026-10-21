"""Per-user dashboard statistics."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.file import FileResponse, UserStatsResponse
from app.services import file_service

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=UserStatsResponse)
def stats(user: User = Depends(get_current_user),
          db: Session = Depends(get_db)) -> UserStatsResponse:
    recent = file_service.list_files(db, user.id, sort_by="date", order="desc",
                                     limit=5)
    return UserStatsResponse(
        total_files=file_service.count_files(db, user.id),
        storage_used_bytes=file_service.storage_used(db, user.id),
        storage_quota_bytes=user.storage_quota_bytes,
        recent_files=[FileResponse.model_validate(r) for r in recent],
    )
