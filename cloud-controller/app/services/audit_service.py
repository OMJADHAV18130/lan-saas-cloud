"""Audit trail writer.

Security rule: this module only ever receives an explicit, caller-built
detail string. Passwords, password hashes, JWTs and file contents must never
be passed in. Details are truncated to keep the table small.
"""
from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.models.audit import AuditEvent
from app.models.user import User

logger = logging.getLogger("cloud_controller.audit")

_MAX_DETAIL = 500


def record(
    db: Session,
    event_type: str,
    *,
    actor: User | None = None,
    actor_username: str | None = None,
    source_ip: str | None = None,
    detail: str | None = None,
    success: bool = True,
) -> None:
    """Append an audit event in its own transaction (best effort)."""
    try:
        event = AuditEvent(
            event_type=event_type[:48],
            actor_id=actor.id if actor else None,
            actor_username=actor.username if actor else (
                actor_username[:64] if actor_username else None),
            source_ip=(source_ip or "")[:64] or None,
            detail=(detail or "")[:_MAX_DETAIL] or None,
            success=success,
        )
        db.add(event)
        db.commit()
    except Exception:  # noqa: BLE001 - auditing must not break the request
        db.rollback()
        logger.exception("Failed to write audit event %s", event_type)
