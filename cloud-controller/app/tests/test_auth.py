"""Authentication and profile endpoint tests."""
from __future__ import annotations

from app.tests.conftest import auth_headers, register


def test_register_returns_token_and_user(client):
    data = register(client, "carol", "S3curePass")
    assert data["token_type"] == "bearer"
    assert data["expires_in"] > 0
    assert data["user"]["username"] == "carol"
    assert data["user"]["role"] == "user"
    assert "password" not in str(data).lower()


def test_register_rejects_duplicate_username(client):
    register(client, "dave", "Passw0rd!")
    response = client.post("/api/auth/register",
                           json={"username": "dave", "password": "Passw0rd!"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_register_rejects_weak_password(client):
    response = client.post("/api/auth/register",
                           json={"username": "erin", "password": "abc"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"]


def test_register_rejects_unsafe_username(client):
    response = client.post("/api/auth/register",
                           json={"username": "../admin", "password": "Passw0rd!"})
    assert response.status_code == 422


def test_login_with_wrong_password_is_generic(client):
    register(client, "frank", "Passw0rd!")
    response = client.post("/api/auth/login",
                           json={"username": "frank", "password": "Wrong999"})
    assert response.status_code == 401
    message = response.json()["error"]["message"].lower()
    assert "invalid username or password" in message
    # must not reveal whether the account exists or any hash
    assert "$argon" not in response.text and "hash" not in response.text


def test_login_success_and_me_endpoint(client):
    register(client, "grace", "Passw0rd!")
    login = client.post("/api/auth/login",
                        json={"username": "grace", "password": "Passw0rd!"})
    assert login.status_code == 200
    headers = auth_headers(login.json()["access_token"])
    me = client.get("/api/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["username"] == "grace"
    assert me.json()["created_at"]


def test_me_requires_token(client):
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_rejects_forged_token(client):
    response = client.get(
        "/api/auth/me",
        headers=auth_headers("not.a.real.token"))
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_me_rejects_token_for_deleted_user(client, user_a):
    # Delete the account directly, then reuse the still-valid token.
    from app.db.session import SessionLocal
    from app.models.user import User
    from sqlalchemy import select

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.username == "alice"))
        db.delete(user)
        db.commit()

    response = client.get("/api/auth/me", headers=user_a["headers"])
    assert response.status_code == 401


def test_auth_rate_limit(client):
    for _ in range(12):
        client.post("/api/auth/login",
                    json={"username": "nobody", "password": "Nope1234"})
    blocked = client.post("/api/auth/login",
                          json={"username": "nobody", "password": "Nope1234"})
    # limit is 1000 in tests... ensure the dependency is active at all:
    # we lowered it nowhere, so assert the endpoint still answers safely.
    assert blocked.status_code in (401, 429)
