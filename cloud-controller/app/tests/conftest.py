"""Test configuration.

Environment is prepared BEFORE importing the application so that the cached
settings, the SQLite engine and the storage adapter all use test values.
"""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TEST_DIR = Path(tempfile.mkdtemp(prefix="lansaas-test-")).resolve()
_MOCK_DIR = _TEST_DIR / "hdfs"

os.environ.update({
    "ENVIRONMENT": "test",
    "DATABASE_URL": f"sqlite:///{(_TEST_DIR / 'test.db').as_posix()}",
    "JWT_SECRET": "test-only-secret-not-used-in-production-0123456789",
    "JWT_EXPIRES_MINUTES": "30",
    "HDFS_ADAPTER": "mock",
    "HDFS_MOCK_DIR": str(_MOCK_DIR),
    "HDFS_ROOT": "/saas-cloud",
    "MAX_UPLOAD_BYTES": "2048",
    "MAX_FILES_PER_USER": "20",
    "CORS_ORIGINS": "http://localhost:5173",
    "STATIC_DIR": "",
    "ADMIN_BOOTSTRAP_USERNAME": "",
    "ADMIN_BOOTSTRAP_PASSWORD": "",
})

from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models.user import User  # noqa: E402


@pytest.fixture(autouse=True)
def clean_state():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    shutil.rmtree(_MOCK_DIR, ignore_errors=True)
    _MOCK_DIR.mkdir(parents=True, exist_ok=True)
    from app.core.rate_limit import limiter

    limiter.reset()
    yield


@pytest.fixture()
def client():
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


def register(client: TestClient, username: str,
             password: str = "Passw0rd!") -> dict:
    response = client.post("/api/auth/register",
                           json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def user_a(client):
    data = register(client, "alice")
    return {"token": data["access_token"], "user": data["user"],
            "headers": auth_headers(data["access_token"])}


@pytest.fixture()
def user_b(client):
    data = register(client, "bob")
    return {"token": data["access_token"], "user": data["user"],
            "headers": auth_headers(data["access_token"])}


def promote_to_admin(username: str) -> None:
    with SessionLocal() as db:
        from sqlalchemy import select

        user = db.scalar(select(User).where(User.username == username))
        assert user is not None
        user.role = "admin"
        db.commit()


@pytest.fixture()
def admin_user(client):
    data = register(client, "rootadmin", "Adm1nPass!")
    promote_to_admin("rootadmin")
    # Re-login so the token belongs to the promoted account (role is checked
    # server-side from the DB, so either token works - this mirrors real use).
    login = client.post("/api/auth/login",
                        json={"username": "rootadmin",
                              "password": "Adm1nPass!"})
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    return {"token": token, "user": login.json()["user"],
            "headers": auth_headers(token)}


def make_user(username: str, password: str, role: str = "admin") -> None:
    """Direct DB creation helper (e.g. for inactive accounts)."""
    with SessionLocal() as db:
        db.add(User(username=username, password_hash=hash_password(password),
                    role=role))
        db.commit()
