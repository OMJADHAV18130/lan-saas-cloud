"""Authentication routes: register, login, profile."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user
from app.core.errors import AuthenticationError, Conflict, PermissionDenied
from app.core.rate_limit import auth_rate_limit, client_ip
from app.core.security import create_access_token, hash_password, verify_password
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services import audit_service

logger = logging.getLogger("cloud_controller.auth")
router = APIRouter(prefix="/api/auth", tags=["auth"])


def _token_response(user: User) -> TokenResponse:
    token, expires_in = create_access_token(user.id, extra={"role": user.role})
    return TokenResponse(
        access_token=token,
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post("/register", response_model=TokenResponse,
             status_code=status.HTTP_201_CREATED,
             dependencies=[Depends(auth_rate_limit("register"))])
def register(payload: RegisterRequest, request: Request,
             db: Session = Depends(get_db)) -> TokenResponse:
    existing = db.scalar(
        select(User).where(func.lower(User.username) == payload.username.lower())
    )
    if existing:
        raise Conflict("That username is already taken.")

    user = User(
        username=payload.username,
        password_hash=hash_password(payload.password),
        role="user",  # roles are never accepted from the client
    )
    db.add(user)
    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Registration transaction failed")
        raise Conflict("That username is already taken.")
    db.refresh(user)

    audit_service.record(db, "user_register", actor=user,
                         source_ip=client_ip(request),
                         detail="self-service registration")
    return _token_response(user)


@router.post("/login", response_model=TokenResponse,
             dependencies=[Depends(auth_rate_limit("login"))])
def login(payload: LoginRequest, request: Request,
          db: Session = Depends(get_db)) -> TokenResponse:
    ip = client_ip(request)
    user = db.scalar(
        select(User).where(func.lower(User.username) == payload.username.lower())
    )
    if user is None or not verify_password(payload.password, user.password_hash):
        audit_service.record(
            db, "login_failed",
            actor_username=payload.username, source_ip=ip,
            detail="invalid credentials", success=False,
        )
        raise AuthenticationError("Invalid username or password.")

    if not user.is_active:
        audit_service.record(db, "login_blocked", actor=user, source_ip=ip,
                             detail="inactive account", success=False)
        raise PermissionDenied("This account is disabled.")

    audit_service.record(db, "login", actor=user, source_ip=ip,
                         detail="password login")
    return _token_response(user)


@router.get("/me", response_model=UserResponse)
def me(user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(user)
