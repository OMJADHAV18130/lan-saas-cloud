"""Admin endpoints must be protected by a server-side role check."""
from __future__ import annotations

import io


def test_admin_routes_reject_regular_user(client, user_a):
    for path in ("/api/admin/stats", "/api/admin/users",
                 "/api/admin/hdfs-status", "/api/admin/audit"):
        response = client.get(path, headers=user_a["headers"])
        assert response.status_code == 403, path
        assert response.json()["error"]["code"] == "forbidden"


def test_admin_routes_reject_anonymous(client):
    for path in ("/api/admin/stats", "/api/admin/users",
                 "/api/admin/hdfs-status", "/api/admin/audit"):
        assert client.get(path).status_code == 401, path


def test_admin_role_cannot_be_self_assigned_via_registration(client):
    resp = client.post("/api/auth/register",
                       json={"username": "sneaky",
                             "password": "Passw0rd!",
                             "role": "admin"})
    assert resp.status_code == 201
    assert resp.json()["user"]["role"] == "user"


def test_admin_stats_report_real_numbers(client, admin_user, user_a):
    files = {"file": ("a.txt", io.BytesIO(b"12345"), "text/plain")}
    assert client.post("/api/files/upload", headers=user_a["headers"],
                       files=files).status_code == 201

    stats = client.get("/api/admin/stats", headers=admin_user["headers"])
    assert stats.status_code == 200
    body = stats.json()
    assert body["user_count"] == 2          # admin + alice
    assert body["admin_count"] == 1
    assert body["file_count"] == 1
    assert body["storage_used_bytes"] == 5
    assert body["hdfs"]["adapter"] == "mock"   # honest about the adapter
    assert body["generated_at"]


def test_admin_users_list_contains_real_usage(client, admin_user, user_a):
    files = {"file": ("b.txt", io.BytesIO(b"1234567890"), "text/plain")}
    client.post("/api/files/upload", headers=user_a["headers"], files=files)

    response = client.get("/api/admin/users", headers=admin_user["headers"])
    assert response.status_code == 200
    items = {u["username"]: u for u in response.json()["items"]}
    assert set(items) == {"rootadmin", "alice"}
    assert items["alice"]["file_count"] == 1
    assert items["alice"]["storage_used_bytes"] == 10
    # password material must never be serialised
    assert "password" not in response.text.lower()


def test_admin_hdfs_status_is_honest_in_mock_mode(client, admin_user):
    response = client.get("/api/admin/hdfs-status",
                          headers=admin_user["headers"])
    assert response.status_code == 200
    body = response.json()
    assert body["adapter"] == "mock"
    assert body["healthy"] is None            # never claimed healthy
    assert "Mock" in body["message"]
    assert body["datanodes"]["live"] is None


def test_audit_events_are_recorded_without_secrets(client, user_a, admin_user):
    client.post("/api/files/upload", headers=user_a["headers"],
                files={"file": ("log.txt", io.BytesIO(b"data"), "text/plain")})
    events = client.get("/api/admin/audit", headers=admin_user["headers"])
    assert events.status_code == 200
    types = {e["event_type"] for e in events.json()["items"]}
    assert {"user_register", "login", "file_upload"} <= types
    text = events.text.lower()
    for secret in ("passw0rd", "bearer", "argon2", "$argon"):
        assert secret not in text


def test_role_change_is_protected(client, admin_user, user_a, user_b):
    target_id = user_a["user"]["id"]
    promoted = client.patch(f"/api/admin/users/{target_id}/role",
                            json={"role": "admin"},
                            headers=admin_user["headers"])
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    # a normal user cannot promote anyone
    denied = client.patch(f"/api/admin/users/{target_id}/role",
                          json={"role": "admin"},
                          headers=user_b["headers"])
    assert denied.status_code == 403

    # the promoted account really is an admin now (role comes from the DB,
    # never from the token or the request body)
    allowed = client.get("/api/admin/stats", headers=user_a["headers"])
    assert allowed.status_code == 200


def test_admin_cannot_demote_self(client, admin_user):
    response = client.patch(
        f"/api/admin/users/{admin_user['user']['id']}/role",
        json={"role": "user"}, headers=admin_user["headers"])
    assert response.status_code == 409


def test_health_endpoint_is_public_and_reports_components(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["database"] == "ok"
    assert body["storage"]["adapter"] == "mock"
    assert body["status"] in {"ok", "degraded", "error"}


def test_public_storage_status_hides_internal_paths(client):
    response = client.get("/api/storage/status")
    assert response.status_code == 200
    body = response.json()
    assert body["namenode_url"] is None
    assert body["root"] == ""
    assert "/saas-cloud" not in response.text
