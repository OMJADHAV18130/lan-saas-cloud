"""File lifecycle tests: upload -> list -> download -> delete, and isolation."""
from __future__ import annotations

import io
import re

from app.db.session import SessionLocal
from app.models.file import FileRecord


def _upload(client, headers, name="notes.txt", content=b"hello hdfs",
            content_type="text/plain"):
    return client.post(
        "/api/files/upload",
        headers=headers,
        files={"file": (name, io.BytesIO(content), content_type)},
    )


def test_upload_lists_and_downloads(client, user_a):
    resp = _upload(client, user_a["headers"], "report.txt",
                   b"lab report v1", "text/plain")
    assert resp.status_code == 201, resp.text
    file_id = resp.json()["file"]["id"]
    assert resp.json()["file"]["size_bytes"] == len(b"lab report v1")
    assert resp.json()["file"]["sha256"]

    listing = client.get("/api/files", headers=user_a["headers"])
    assert listing.status_code == 200
    body = listing.json()
    assert body["total"] == 1
    assert body["items"][0]["original_name"] == "report.txt"
    assert body["storage_used_bytes"] == len(b"lab report v1")

    download = client.get(f"/api/files/{file_id}/download",
                          headers=user_a["headers"])
    assert download.status_code == 200
    assert download.content == b"lab report v1"
    assert "attachment" in download.headers["content-disposition"]
    assert download.headers["x-content-sha256"] == (
        resp.json()["file"]["sha256"])


def test_content_is_stored_in_storage_not_sqlite(client, user_a):
    """The bytes must exist in the storage adapter and never in the DB."""
    payload = b"UNIQUE_MARKER_BYTES_12345"
    resp = _upload(client, user_a["headers"], "marker.bin", payload)
    assert resp.status_code == 201
    hdfs_path = resp.json()["file"].get("hdfs_path")
    assert hdfs_path is None  # storage paths are never exposed to clients

    with SessionLocal() as db:
        record = db.query(FileRecord).one()
        assert record.original_name == "marker.bin"
        assert record.size_bytes == len(payload)

    from app.core.config import get_settings
    from pathlib import Path

    settings = get_settings()
    stored_files = [p for p in Path(settings.hdfs_mock_dir).rglob("*")
                    if p.is_file()]
    assert stored_files, "expected the mock storage to hold the object"
    # object names are server generated uuids, not the user filename
    assert all(re.fullmatch(r"[a-f0-9]{32}", p.name) for p in stored_files)


def test_cannot_download_another_users_file(client, user_a, user_b):
    file_id = _upload(client, user_a["headers"]).json()["file"]["id"]
    forbidden = client.get(f"/api/files/{file_id}/download",
                           headers=user_b["headers"])
    # 404 (not 403) so ids are not confirmed to exist
    assert forbidden.status_code == 404
    assert forbidden.json()["error"]["code"] == "not_found"


def test_cannot_delete_another_users_file(client, user_a, user_b):
    file_id = _upload(client, user_a["headers"]).json()["file"]["id"]
    response = client.delete(f"/api/files/{file_id}", headers=user_b["headers"])
    assert response.status_code == 404

    still_there = client.get("/api/files", headers=user_a["headers"])
    assert still_there.json()["total"] == 1


def test_delete_removes_metadata_and_content(client, user_a):
    file_id = _upload(client, user_a["headers"]).json()["file"]["id"]
    response = client.delete(f"/api/files/{file_id}", headers=user_a["headers"])
    assert response.status_code == 200
    assert response.json()["file_id"] == file_id

    assert client.get("/api/files",
                      headers=user_a["headers"]).json()["total"] == 0
    assert client.get(f"/api/files/{file_id}/download",
                      headers=user_a["headers"]).status_code == 404

    from app.core.config import get_settings
    from pathlib import Path

    settings = get_settings()
    remaining = [p for p in Path(settings.hdfs_mock_dir).rglob("*")
                 if p.is_file()]
    assert remaining == [], "content should be gone from storage as well"


def test_delete_twice_returns_404(client, user_a):
    file_id = _upload(client, user_a["headers"]).json()["file"]["id"]
    assert client.delete(f"/api/files/{file_id}",
                         headers=user_a["headers"]).status_code == 200
    assert client.delete(f"/api/files/{file_id}",
                         headers=user_a["headers"]).status_code == 404


def test_upload_rejects_empty_file(client, user_a):
    resp = _upload(client, user_a["headers"], "empty.txt", b"")
    assert resp.status_code == 422


def test_upload_rejects_oversized_file(client, user_a):
    resp = _upload(client, user_a["headers"], "big.bin", b"x" * 4096)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "payload_too_large"
    assert client.get("/api/files",
                      headers=user_a["headers"]).json()["total"] == 0


def test_filename_is_sanitised_not_used_as_path(client, user_a):
    resp = _upload(client, user_a["headers"],
                   "../../../etc/passwd.txt", b"sneaky")
    assert resp.status_code == 201
    assert resp.json()["file"]["original_name"] == "passwd.txt"

    from app.core.config import get_settings
    from pathlib import Path

    settings = get_settings()
    all_paths = [str(p) for p in Path(settings.hdfs_mock_dir).rglob("*")]
    assert all("passwd.txt" not in p for p in all_paths)


def test_files_requires_authentication(client):
    assert client.get("/api/files").status_code == 401
    assert client.post("/api/files/upload").status_code in (401, 422)
    assert client.delete("/api/files/someid").status_code == 401


def test_search_and_sort(client, user_a):
    for name, content in [("b_report.pdf", b"BBB"),
                          ("a_notes.txt", b"A"),
                          ("c_data.csv", b"CCCCCCCC")]:
        assert _upload(client, user_a["headers"], name, content).status_code == 201

    searched = client.get("/api/files", params={"q": "report"},
                          headers=user_a["headers"])
    assert searched.status_code == 200
    assert [f["original_name"] for f in searched.json()["items"]] == ["b_report.pdf"]

    by_name = client.get("/api/files",
                         params={"sort_by": "name", "order": "asc"},
                         headers=user_a["headers"])
    names = [f["original_name"] for f in by_name.json()["items"]]
    assert names == sorted(names)

    by_size = client.get("/api/files",
                         params={"sort_by": "size", "order": "desc"},
                         headers=user_a["headers"])
    sizes = [f["size_bytes"] for f in by_size.json()["items"]]
    assert sizes == sorted(sizes, reverse=True)

    bad_sort = client.get("/api/files", params={"sort_by": "password"},
                          headers=user_a["headers"])
    assert bad_sort.status_code == 422


def test_dashboard_stats_match_real_files(client, user_a):
    _upload(client, user_a["headers"], "one.txt", b"12345")
    _upload(client, user_a["headers"], "two.txt", b"6789012345")
    stats = client.get("/api/dashboard/stats", headers=user_a["headers"])
    assert stats.status_code == 200
    body = stats.json()
    assert body["total_files"] == 2
    assert body["storage_used_bytes"] == 15
    assert body["storage_quota_bytes"] == 100 * 1024 * 1024
    assert len(body["recent_files"]) == 2


def test_file_limit_is_enforced(client, user_a):
    # MAX_FILES_PER_USER=20 in tests
    for i in range(20):
        resp = _upload(client, user_a["headers"], f"f{i}.txt", b"x")
        assert resp.status_code == 201, resp.text
    blocked = _upload(client, user_a["headers"], "extra.txt", b"x")
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "conflict"
