"""User account model. Password material is only ever stored as an Argon2 hash."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def _uuid() -> str:
    return uuid.uuid4().hex


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True,
                                          nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), default="user", nullable=False)
    storage_quota_bytes: Mapped[int] = mapped_column(Integer,
                                                     default=100 * 1024 * 1024,
                                                     nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, nullable=False)

    files = relationship("FileRecord", back_populates="owner",
                         cascade="all, delete-orphan")

    # -- helpers ---------------------------------------------------------
    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User {self.username} role={self.role}>"
