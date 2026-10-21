from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=32,
                          description="3-32 chars: letters, digits, _ . -")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("username")
    @classmethod
    def _username_charset(cls, v: str) -> str:
        v = v.strip()
        if not USERNAME_RE.match(v):
            raise ValueError(
                "Username must be 3-32 characters and contain only letters, "
                "digits, underscore, dot or hyphen."
            )
        return v

    @field_validator("password")
    @classmethod
    def _password_strength(cls, v: str) -> str:
        if not re.search(r"[A-Za-z]", v) or not re.search(r"\d", v):
            raise ValueError("Password must contain at least one letter and "
                             "one digit.")
        if v.lower() in {"password1", "qwerty123", "admin1234"}:
            raise ValueError("This password is too common.")
        return v


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    storage_quota_bytes: int
    is_active: bool
    created_at: datetime


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
