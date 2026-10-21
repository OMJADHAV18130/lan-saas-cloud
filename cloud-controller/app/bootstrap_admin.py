"""Safe first-admin bootstrap.

Two supported paths, both requiring an explicit secret (there is no default
password anywhere in the code):

  1. Interactive (recommended):
         python -m app.bootstrap_admin

  2. Environment driven, only used when the users table is EMPTY:
         ADMIN_BOOTSTRAP_USERNAME=... ADMIN_BOOTSTRAP_PASSWORD=...
     Remove those variables after the first start.
"""
from __future__ import annotations

import getpass
import logging
import sys

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import func, select

from app.core.config import Settings, get_settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.schemas.auth import RegisterRequest

logger = logging.getLogger("cloud_controller.bootstrap")


def _validated_credentials(username: str, password: str) -> RegisterRequest:
    return RegisterRequest(username=username, password=password)


def create_admin(username: str, password: str) -> User:
    payload = _validated_credentials(username, password)
    with SessionLocal() as db:
        exists = db.scalar(
            select(User).where(func.lower(User.username) == payload.username.lower())
        )
        if exists:
            raise SystemExit(f"User '{payload.username}' already exists.")
        admin = User(
            username=payload.username,
            password_hash=hash_password(payload.password),
            role="admin",
        )
        db.add(admin)
        db.commit()
        db.refresh(admin)
        return admin


def bootstrap_from_env(settings: Settings | None = None) -> None:
    """Create the first admin only on an empty database and with env secrets."""
    s = settings or get_settings()
    if not s.admin_bootstrap_username or not s.admin_bootstrap_password:
        return
    with SessionLocal() as db:
        user_count = int(db.scalar(select(func.count(User.id))) or 0)
    if user_count > 0:
        logger.info("Admin bootstrap skipped: users already exist.")
        return
    try:
        admin = create_admin(s.admin_bootstrap_username,
                             s.admin_bootstrap_password)
        logger.warning("Bootstrap administrator '%s' created. "
                       "Remove ADMIN_BOOTSTRAP_* from the environment now.",
                       admin.username)
    except (SystemExit, PydanticValidationError) as exc:
        logger.error("Admin bootstrap failed: %s", exc)


def main() -> int:
    print("Create the first administrator account.")
    username = input("Admin username: ").strip()
    password = getpass.getpass("Password (min 8 chars, letter+digit): ")
    confirm = getpass.getpass("Confirm password: ")
    if password != confirm:
        print("Passwords do not match.", file=sys.stderr)
        return 1
    try:
        admin = create_admin(username, password)
    except (SystemExit, PydanticValidationError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"Administrator '{admin.username}' created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
