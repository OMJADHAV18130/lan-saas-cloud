"""Audit trail model.

Rules enforced by the audit service:
  * never store passwords, password hashes or tokens;
  * never store file contents;
  * store who / what / when / from where, plus small non-sensitive details.
"""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.user import utcnow


def _uuid() -> str:
    return uuid.uuid4().hex


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    event_type: Mapped[str] = mapped_column(String(48), index=True,
                                            nullable=False)
    # Intentionally NOT a FK: audit rows must survive user deletion.
    actor_id: Mapped[str | None] = mapped_column(String(32), index=True)
    actor_username: Mapped[str | None] = mapped_column(String(64))
    source_ip: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditEvent {self.event_type} ok={self.success}>"
