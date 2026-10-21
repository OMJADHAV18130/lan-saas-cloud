"""File business logic: validation, ownership, HDFS + SQLite consistency."""
from __future__ import annotations

import logging
import os
import re
import tempfile
import uuid
from typing import IO

from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app.core.config import Settings
from app.core.errors import (
    Conflict,
    NotFound,
    PayloadTooLarge,
    PermissionDenied,
    StorageUnavailable,
    ValidationError,
)
from app.models.file import FileRecord
from app.models.user import User
from app.services import audit_service
from app.services.hdfs_service import HdfsStorage, sha256_file

logger = logging.getLogger("cloud_controller.files")

_SPOOL_IN_MEMORY = 8 * 1024 * 1024   # larger uploads spill to a temp file
_READ_CHUNK = 1024 * 1024
_UNSAFE_CHARS = re.compile(r"[\x00-\x1f\x7f]")


# ---------------------------------------------------------------------------
# Filename handling (metadata only - never used as a storage path)
# ---------------------------------------------------------------------------
def sanitize_filename(raw: str | None) -> str:
    """Return a safe *display* filename.

    Strips directory components from both Windows and POSIX clients, removes
    control characters, and caps the length. The result is stored as metadata
    and used for Content-Disposition on download; storage paths are generated
    from UUIDs instead.
    """
    if not raw:
        raise ValidationError("A filename is required.")
    name = raw.replace("\\", "/").split("/")[-1].strip()
    name = _UNSAFE_CHARS.sub("", name)
    name = name.lstrip(".").strip()
    if not name or name in {".", ".."}:
        raise ValidationError("The filename is not valid.")
    if len(name) > 200:
        stem, ext = os.path.splitext(name)
        name = stem[: 200 - len(ext)] + ext[:32]
    return name


def validate_content_type(content_type: str | None) -> str:
    if not content_type or len(content_type) > 128:
        return "application/octet-stream"
    if not re.match(r"^[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+$", content_type):
        return "application/octet-stream"
    return content_type


async def spool_upload(upload: UploadFile, max_bytes: int) -> tuple[IO[bytes], int]:
    """Copy the multipart stream to a spooled temp file with a hard size cap.

    Memory stays bounded (8 MiB) even for large uploads; the hard limit is
    enforced while reading, so oversized requests never reach HDFS.
    """
    spool = tempfile.SpooledTemporaryFile(max_size=_SPOOL_IN_MEMORY, mode="w+b")
    total = 0
    try:
        while True:
            chunk = await upload.read(_READ_CHUNK)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise PayloadTooLarge(
                    f"File exceeds the maximum upload size of "
                    f"{max_bytes // (1024 * 1024)} MiB."
                )
            spool.write(chunk)
        if total == 0:
            raise ValidationError("Empty files are not accepted.")
        spool.seek(0)
        return spool, total
    except Exception:
        spool.close()
        raise


# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
def get_owned_file(db: Session, user: User, file_id: str) -> FileRecord:
    """Fetch a file ONLY if the authenticated user owns it.

    The caller never supplies an owner id; ownership always comes from the JWT.
    """
    record = db.get(FileRecord, file_id)
    if record is None:
        raise NotFound("File not found.")
    if record.owner_id != user.id:
        # Same response as a missing file: do not confirm that an id exists.
        raise NotFound("File not found.")
    return record


def storage_used(db: Session, user_id: str) -> int:
    return int(db.scalar(
        select(func.coalesce(func.sum(FileRecord.size_bytes), 0))
        .where(FileRecord.owner_id == user_id)
    ) or 0)


def count_files(db: Session, user_id: str) -> int:
    return int(db.scalar(
        select(func.count(FileRecord.id)).where(FileRecord.owner_id == user_id)
    ) or 0)


def list_files(
    db: Session,
    user_id: str,
    *,
    search: str | None = None,
    sort_by: str = "date",
    order: str = "desc",
    limit: int = 200,
    offset: int = 0,
) -> list[FileRecord]:
    stmt = select(FileRecord).where(FileRecord.owner_id == user_id)
    if search:
        term = f"%{search.strip()}%"
        stmt = stmt.where(FileRecord.original_name.ilike(term))
    column = {
        "name": FileRecord.original_name,
        "size": FileRecord.size_bytes,
        "date": FileRecord.created_at,
    }.get(sort_by, FileRecord.created_at)
    direction = desc if order == "desc" else asc
    stmt = stmt.order_by(direction(column), desc(FileRecord.created_at))
    stmt = stmt.limit(max(1, min(limit, 500))).offset(max(0, offset))
    return list(db.scalars(stmt).all())


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------
def create_file(
    db: Session,
    hdfs: HdfsStorage,
    settings: Settings,
    user: User,
    *,
    original_name: str,
    content_type: str | None,
    fileobj: IO[bytes],
    size: int,
    source_ip: str | None = None,
) -> FileRecord:
    safe_name = sanitize_filename(original_name)
    safe_type = validate_content_type(content_type)

    if count_files(db, user.id) >= settings.max_files_per_user:
        raise Conflict(
            f"File limit reached ({settings.max_files_per_user} files). "
            "Delete a file before uploading a new one."
        )
    used = storage_used(db, user.id)
    if used + size > user.storage_quota_bytes:
        raise PayloadTooLarge(
            "Storage quota exceeded. "
            f"Used {used} of {user.storage_quota_bytes} bytes."
        )

    digest, actual_size = sha256_file(fileobj)
    if actual_size != size:
        raise ValidationError("Uploaded file size changed during processing.")

    file_id = uuid.uuid4().hex
    hdfs_path = hdfs.layout.object_path(user.id, file_id)

    # 1) Write bytes to HDFS first.
    try:
        hdfs.ensure_user_dir(user.id)
        hdfs.upload(hdfs_path, fileobj, size)
    except StorageUnavailable:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("HDFS upload failed for user %s", user.id)
        _best_effort_delete(hdfs, hdfs_path)
        raise StorageUnavailable("The file could not be stored in HDFS.") from exc

    # 2) Persist metadata. If this fails, remove the orphan object in HDFS.
    record = FileRecord(
        id=file_id,
        owner_id=user.id,
        original_name=safe_name,
        hdfs_path=hdfs_path,
        size_bytes=size,
        content_type=safe_type,
        sha256=digest,
    )
    try:
        db.add(record)
        db.commit()
        db.refresh(record)
    except Exception:
        db.rollback()
        logger.exception("Metadata insert failed; rolling back HDFS object %s",
                         hdfs_path)
        _best_effort_delete(hdfs, hdfs_path)
        raise StorageUnavailable(
            "The upload could not be recorded. Please try again."
        )

    audit_service.record(
        db, "file_upload", actor=user, source_ip=source_ip,
        detail=f"file_id={record.id} size={size}",
    )
    return record


# ---------------------------------------------------------------------------
# Delete (with partial-failure handling)
# ---------------------------------------------------------------------------
def delete_file(
    db: Session,
    hdfs: HdfsStorage,
    user: User,
    record: FileRecord,
    *,
    source_ip: str | None = None,
) -> None:
    if record.owner_id != user.id:
        raise PermissionDenied("You do not own this file.")

    # 1) Remove bytes from HDFS. If HDFS is unreachable we KEEP the metadata,
    #    so the user still sees the file and can retry.
    try:
        hdfs.delete(record.hdfs_path, recursive=False)
    except NotFound:
        # Object already missing: continue and clean the metadata row.
        logger.warning("HDFS object already missing for file %s", record.id)
    except StorageUnavailable:
        raise StorageUnavailable(
            "The file could not be deleted from HDFS; nothing was changed. "
            "Please retry when storage is available."
        )

    # 2) Remove metadata. If this fails the HDFS object is gone but the row
    #    remains: the dashboard shows a file that cannot be downloaded and the
    #    admin can clean it up. Documented limitation.
    try:
        file_id = record.id
        db.delete(record)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("HDFS object deleted but metadata delete failed for %s",
                         record.id)
        raise StorageUnavailable(
            "Storage was updated but metadata cleanup failed. "
            "Please contact the administrator."
        )

    audit_service.record(
        db, "file_delete", actor=user, source_ip=source_ip,
        detail=f"file_id={file_id}",
    )


def _best_effort_delete(hdfs: HdfsStorage, path: str) -> None:
    try:
        hdfs.delete(path)
    except Exception:  # noqa: BLE001
        logger.error("Could not remove orphaned HDFS object %s", path)
