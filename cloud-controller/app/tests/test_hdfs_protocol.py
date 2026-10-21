"""WebHDFS protocol tests against a fake NameNode/DataNode.

These tests prove that the controller implements the redirect protocol rather
than assuming requests finish at the NameNode:

  * write:  PUT op=CREATE -> 307 -> PUT bytes to the DataNode -> 201
  * read:   GET op=OPEN   -> 307 -> GET bytes from the DataNode (streamed)
  * errors: 404 RemoteException -> NotFound; unreachable host -> StorageUnavailable
"""
from __future__ import annotations

import io

import pytest

from app.core.config import Settings
from app.core.errors import NotFound, StorageUnavailable
from app.services.hdfs_service import WebHdfsService, sha256_file
from app.tests.fake_webhdfs import FakeWebHdfsServer

ROOT = "/saas-cloud"
USER_ID = "a" * 32
FILE_ID = "b" * 32


def _settings(base_url: str, **overrides) -> Settings:
    values = dict(
        hdfs_adapter="webhdfs",
        hdfs_base_url=base_url,
        hdfs_service_user="saascloud",
        hdfs_auth="simple",
        hdfs_root=ROOT,
        hdfs_timeout_seconds=3.0,
        hdfs_jmx_url="",
    )
    values.update(overrides)
    return Settings(**values)


@pytest.fixture()
def fake_hdfs():
    server = FakeWebHdfsServer().start()
    try:
        yield server
    finally:
        server.stop()


@pytest.fixture()
def service(fake_hdfs):
    svc = WebHdfsService(_settings(fake_hdfs.base_url))
    try:
        yield svc
    finally:
        svc.close()


def test_upload_follows_namenode_to_datanode_redirect(fake_hdfs, service):
    payload = b"x" * 300_000
    path = service.layout.object_path(USER_ID, FILE_ID)

    service.upload(path, io.BytesIO(payload), len(payload))

    assert fake_hdfs.redirects_served == 1, "exactly one CREATE redirect"
    assert fake_hdfs.received_body_lengths == [len(payload)]
    assert fake_hdfs.objects[path] == payload


def test_upload_retries_redirect_hop_and_preserves_bytes(fake_hdfs, service):
    payload = bytes(range(256)) * 400  # 102400 bytes
    path = f"{ROOT}/users/{USER_ID}/{FILE_ID}"
    service.upload(path, io.BytesIO(payload), len(payload))
    assert fake_hdfs.objects[path] == payload


def test_download_streams_from_datanode(fake_hdfs, service):
    payload = b"streaming-test-" * 200_000  # ~3 MiB
    path = f"{ROOT}/users/{USER_ID}/{FILE_ID}"
    service.upload(path, io.BytesIO(payload), len(payload))

    collected = bytearray()
    chunks = 0
    with service.open_stream(path) as stream:
        for chunk in stream:
            chunks += 1
            collected.extend(chunk)

    assert bytes(collected) == payload
    assert chunks > 1, "content should be delivered in more than one chunk"
    assert fake_hdfs.redirects_served == 2  # one write + one read redirect


def test_download_missing_object_raises_not_found(fake_hdfs, service):
    with pytest.raises(NotFound):
        with service.open_stream(f"{ROOT}/users/{USER_ID}/{'c' * 32}") as stream:
            for _ in stream:
                pass


def test_exists_delete_and_liststatus(fake_hdfs, service):
    path = f"{ROOT}/users/{USER_ID}/{FILE_ID}"
    assert service.exists(path) is False
    service.upload(path, io.BytesIO(b"abc"), 3)
    assert service.exists(path) is True

    entries = service.list_status(f"{ROOT}/users/{USER_ID}")
    assert entries and entries[0]["path"] == path
    assert entries[0]["size"] == 3

    assert service.delete(path) is True
    assert service.exists(path) is False
    # deleting a missing object reports False, it does not explode
    assert service.delete(path) is False


def test_status_reports_unreachable_namenode_honestly():
    svc = WebHdfsService(_settings("http://127.0.0.1:9",  # discard port
                                   hdfs_timeout_seconds=1.0))
    try:
        status = svc.status()
    finally:
        svc.close()
    assert status["healthy"] is False
    assert status["adapter"] == "webhdfs"
    message = status["message"].lower()
    assert "unreachable" in message or "timed out" in message
    # No DataNode information is invented when the NameNode cannot be reached.
    assert status["datanodes"] is None


def test_status_uses_jmx_only_when_configured(fake_hdfs):
    svc = WebHdfsService(_settings(fake_hdfs.base_url))
    try:
        status = svc.status()
    finally:
        svc.close()
    assert status["healthy"] is False          # root not present in fake store
    assert "does not exist" in status["message"]
    assert status["datanodes"]["available"] is None
    assert "HDFS_JMX_URL" in status["datanodes"]["reason"]


def test_connection_error_becomes_storage_unavailable():
    svc = WebHdfsService(_settings("http://127.0.0.1:9",
                                   hdfs_timeout_seconds=1.0))
    try:
        with pytest.raises(StorageUnavailable):
            svc.upload(f"{ROOT}/users/{USER_ID}/{FILE_ID}", io.BytesIO(b"a"), 1)
        with pytest.raises(StorageUnavailable):
            svc.delete(f"{ROOT}/users/{USER_ID}/{FILE_ID}")
        with pytest.raises(StorageUnavailable):
            svc.ensure_dir(f"{ROOT}/users/{USER_ID}")
    finally:
        svc.close()


def test_unsafe_ids_cannot_build_storage_paths():
    svc = WebHdfsService(_settings("http://127.0.0.1:9"))
    try:
        for bad in ("../../etc", "abc", "", "z" * 32, "A" * 32):
            with pytest.raises(ValueError):
                svc.layout.object_path(bad, FILE_ID)
            with pytest.raises(ValueError):
                svc.layout.object_path(USER_ID, bad)
    finally:
        svc.close()


def test_sha256_helper_matches_hashlib():
    import hashlib

    payload = b"verify me" * 1000
    digest, size = sha256_file(io.BytesIO(payload))
    assert digest == hashlib.sha256(payload).hexdigest()
    assert size == len(payload)
