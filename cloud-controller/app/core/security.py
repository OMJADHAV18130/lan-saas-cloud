"""Password hashing (Argon2id) and JWT access tokens.

Passwords are never stored, logged or echoed. Argon2 is used through
`argon2-cffi`; a bcrypt fallback exists so the project still runs in lab
environments where building argon2 is impossible.
"""
from __future__ import annotations

import datetime as dt
import logging
from typing import Any

import jwt

from app.core.config import get_settings
from app.core.errors import AuthenticationError

logger = logging.getLogger("cloud_controller.security")

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
try:  # pragma: no cover - environment dependent
    from argon2 import PasswordHasher
    from argon2.exceptions import (
        InvalidHashError,
        VerificationError,
        VerifyMismatchError,
    )

    _ph = PasswordHasher(time_cost=3, memory_cost=64 * 1024, parallelism=2)

    HASH_ALGORITHM = "argon2id"

    def hash_password(password: str) -> str:
        return _ph.hash(password)

    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return _ph.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
        except Exception:  # pragma: no cover - defensive
            logger.warning("Password verification failed for an unexpected "
                           "reason; treating as mismatch.")
            return False

except ImportError:  # pragma: no cover - fallback path
    import bcrypt

    HASH_ALGORITHM = "bcrypt"

    def hash_password(password: str) -> str:
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12)).decode()

    def verify_password(password: str, password_hash: str) -> bool:
        try:
            return bcrypt.checkpw(password.encode(), password_hash.encode())
        except Exception:
            return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------
def create_access_token(subject: str, *, extra: dict[str, Any] | None = None) -> tuple[str, int]:
    """Create a signed access token. Returns (token, expires_in_seconds)."""
    settings = get_settings()
    now = dt.datetime.now(dt.timezone.utc)
    expires = now + dt.timedelta(minutes=settings.jwt_expires_minutes)
    payload: dict[str, Any] = {
        "sub": str(subject),
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "iss": "lan-saas-cloud-controller",
    }
    if extra:
        payload.update(extra)
    token = jwt.encode(payload, settings.jwt_secret,
                       algorithm=settings.jwt_algorithm)
    return token, settings.jwt_expires_minutes * 60


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    try:
        return jwt.decode(token, settings.jwt_secret,
                          algorithms=[settings.jwt_algorithm],
                          options={"require": ["exp", "sub"]})
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Access token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Access token is invalid.") from exc
