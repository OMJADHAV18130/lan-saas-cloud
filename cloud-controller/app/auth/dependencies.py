"""Authentication dependencies: JWT -> User, and the admin role check."""
from __future__ import annotations

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.errors import AuthenticationError, PermissionDenied
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.user import User
from app.services.hdfs_service import HdfsStorage

# auto_error=False lets us return the project's consistent JSON error shape.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login",
                                    auto_error=False)


def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    if not token:
        raise AuthenticationError("Authentication required.")
    payload = decode_access_token(token)
    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Invalid access token.")
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account is not available.")
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    """Server-side role check - never trust a client supplied role."""
    if not user.is_admin:
        raise PermissionDenied("Administrator privileges are required.")
    return user


def get_hdfs(request: Request) -> HdfsStorage:
    service = getattr(request.app.state, "hdfs", None)
    if service is None:
        from app.core.errors import StorageUnavailable

        raise StorageUnavailable("Storage service is not initialised.")
    return service
