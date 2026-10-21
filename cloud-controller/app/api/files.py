"""File endpoints: list, upload, download, delete."""
from __future__ import annotations

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user, get_hdfs
from app.core.config import get_settings
from app.core.errors import NotFound, StorageUnavailable
from app.core.rate_limit import client_ip
from app.db.session import get_db
from app.models.user import User
from app.schemas.file import (
    DeleteResponse,
    FileListResponse,
    FileResponse,
    UploadResponse,
)
from app.services import audit_service, file_service
from app.services.hdfs_service import HdfsStorage

logger = logging.getLogger("cloud_controller.files_api")
router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("", response_model=FileListResponse)
def list_files(
    q: str | None = Query(default=None, max_length=100,
                          description="Case-insensitive filename search"),
    sort_by: str = Query(default="date", pattern="^(name|size|date)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileListResponse:
    records = file_service.list_files(
        db, user.id, search=q, sort_by=sort_by, order=order,
        limit=limit, offset=offset,
    )
    return FileListResponse(
        items=[FileResponse.model_validate(r) for r in records],
        total=file_service.count_files(db, user.id),
        storage_used_bytes=file_service.storage_used(db, user.id),
        storage_quota_bytes=user.storage_quota_bytes,
        sort_by=sort_by,
        order=order,
        search=q,
    )


@router.post("/upload", response_model=UploadResponse,
             status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(..., description="File to store in HDFS"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    hdfs: HdfsStorage = Depends(get_hdfs),
) -> UploadResponse:
    settings = get_settings()
    spool, size = await file_service.spool_upload(file, settings.max_upload_bytes)
    try:
        record = file_service.create_file(
            db, hdfs, settings, user,
            original_name=file.filename or "",
            content_type=file.content_type,
            fileobj=spool,
            size=size,
            source_ip=client_ip(request),
        )
    finally:
        spool.close()
        await file.close()
    return UploadResponse(file=FileResponse.model_validate(record))


@router.get("/{file_id}/download")
def download_file(
    file_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    hdfs: HdfsStorage = Depends(get_hdfs),
) -> StreamingResponse:
    record = file_service.get_owned_file(db, user, file_id)

    # Verify the metadata points inside *this* user's HDFS directory before
    # reading anything (defence in depth against corrupted/tampered metadata).
    expected_prefix = f"{hdfs.layout.user_dir(user.id)}/"
    if not record.hdfs_path.startswith(expected_prefix):
        logger.error("Ownership/path mismatch for file %s", record.id)
        raise NotFound("File not found.")

    if not hdfs.exists(record.hdfs_path):
        audit_service.record(
            db, "file_download_missing_hdfs", actor=user,
            source_ip=client_ip(request),
            detail=f"file_id={record.id}", success=False,
        )
        raise NotFound("The file's content is missing from storage. "
                       "Please contact the administrator.")

    def _stream():
        with hdfs.open_stream(record.hdfs_path) as chunks:
            for chunk in chunks:
                yield chunk

    audit_service.record(
        db, "file_download", actor=user, source_ip=client_ip(request),
        detail=f"file_id={record.id} size={record.size_bytes}",
    )

    safe_ascii = record.original_name.encode("ascii", "replace").decode()
    safe_ascii = safe_ascii.replace('"', "'").replace("\\", "_")
    disposition = (
        f'attachment; filename="{safe_ascii}"; '
        f"filename*=UTF-8''{quote(record.original_name)}"
    )
    return StreamingResponse(
        _stream(),
        media_type=record.content_type,
        headers={
            "Content-Disposition": disposition,
            "Content-Length": str(record.size_bytes),
            "X-Content-SHA256": record.sha256,
            "Cache-Control": "private, no-store",
        },
    )


@router.delete("/{file_id}", response_model=DeleteResponse)
def delete_file(
    file_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    hdfs: HdfsStorage = Depends(get_hdfs),
) -> DeleteResponse:
    record = file_service.get_owned_file(db, user, file_id)
    file_service.delete_file(db, hdfs, user, record,
                             source_ip=client_ip(request))
    return DeleteResponse(message="File deleted.", file_id=file_id)
