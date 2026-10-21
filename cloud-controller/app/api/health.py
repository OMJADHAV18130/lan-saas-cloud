"""Health and HDFS status.

`/api/health` is intentionally public (useful for the LAN operator) but leaks
nothing sensitive: it reports component states, not paths or credentials.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import get_hdfs
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.common import HealthResponse
from app.schemas.file import HdfsStatusResponse
from app.services.hdfs_service import HdfsStorage

router = APIRouter(tags=["health"])


@router.get("/api/health", response_model=HealthResponse)
def health(request: Request, db: Session = Depends(get_db),
           hdfs: HdfsStorage = Depends(get_hdfs)) -> HealthResponse:
    settings = get_settings()
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:  # noqa: BLE001
        database = "error"

    storage = hdfs.status()
    if database != "ok":
        overall = "error"
    elif storage["adapter"] == "mock":
        overall = "degraded"
    elif storage["healthy"] is True:
        overall = "ok"
    else:
        overall = "degraded"

    return HealthResponse(
        status=overall,
        app=settings.app_name,
        environment=settings.environment,
        database=database,
        storage={
            "adapter": storage["adapter"],
            "mode_label": storage["mode_label"],
            "healthy": storage["healthy"],
            "message": storage["message"],
        },
        max_upload_bytes=settings.max_upload_bytes,
        version="1.0.0",
    )


@router.get("/api/storage/status", response_model=HdfsStatusResponse)
def storage_status(hdfs: HdfsStorage = Depends(get_hdfs)) -> HdfsStatusResponse:
    """Public, non-sensitive storage indicator for the UI badge.

    Deliberately excludes internal HDFS paths. Administrators get the fuller
    view (NameNode URL, DataNode liveness) from /api/admin/hdfs-status.
    """
    status = hdfs.status()
    return HdfsStatusResponse(
        adapter=status["adapter"],
        mode_label=status["mode_label"],
        healthy=status["healthy"],
        namenode_url=None,
        root="",
        latency_ms=status["latency_ms"],
        datanodes=None,
        message=status["message"],
    )
