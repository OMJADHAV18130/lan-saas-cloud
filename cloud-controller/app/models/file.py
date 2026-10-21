"""File metadata model.

The row describes a file whose BYTES live in HDFS at `hdfs_path`.
`original_name` is metadata only and is never used to build a storage path.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import BigInteger, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.user import utcnow


def _uuid() -> str:
    return uuid.uuid4().hex


class FileRecord(Base):
    __tablename__ = "file_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    owner_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="CASCADE"),
        index=True, nullable=False)

    original_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hdfs_path: Mapped[str] = mapped_column(String(1024), unique=True,
                                           nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str] = mapped_column(String(128),
                                              default="application/octet-stream",
                                              nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    owner = relationship("User", back_populates="files")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<FileRecord {self.original_name} ({self.size_bytes} bytes)>"
