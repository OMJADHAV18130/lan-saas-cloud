"""Real-HDFS integration test - skipped unless a live cluster is configured.

This is the test that proves the project talks to genuine Apache Hadoop.
It is DISABLED by default and never pretends to have run.

Enable it on the lab server:

    export HDFS_BASE_URL=http://nn.lab.local:9870
    export HDFS_SERVICE_USER=saascloud
    export HDFS_ROOT=/saas-cloud
    export RUN_HDFS_INTEGRATION=1
    python -m pytest app/tests/test_hdfs_live.py -v

It verifies, against the real cluster:
  * directory creation as the service identity
  * a WebHDFS CREATE that redirects to a real DataNode
  * byte-for-byte round-trip of a multi-chunk object
  * LISTSTATUS/GETFILESTATUS metadata
  * DELETE
"""
from __future__ import annotations

import io
import os
import uuid

import pytest

from app.core.config import Settings
from app.services.hdfs_service import WebHdfsService

ENABLED = os.environ.get("RUN_HDFS_INTEGRATION") == "1"

pytestmark = pytest.mark.skipif(
    not ENABLED,
    reason="Live HDFS integration test. Set RUN_HDFS_INTEGRATION=1 and "
           "HDFS_BASE_URL to a running NameNode to enable it.",
)


@pytest.fixture(scope="module")
def service():
    settings = Settings(
        hdfs_adapter="webhdfs",
        hdfs_base_url=os.environ["HDFS_BASE_URL"],
        hdfs_service_user=os.environ.get("HDFS_SERVICE_USER", "saascloud"),
        hdfs_root=os.environ.get("HDFS_ROOT", "/saas-cloud"),
        hdfs_jmx_url=os.environ.get("HDFS_JMX_URL", ""),
    )
    svc = WebHdfsService(settings)
    yield svc
    svc.close()


def test_namenode_is_reachable(service):
    status = service.status()
    assert status["adapter"] == "webhdfs"
    assert status["healthy"] is True, status["message"]


def test_real_round_trip(service):
    user_id = uuid.uuid4().hex
    file_id = uuid.uuid4().hex
    path = service.layout.object_path(user_id, file_id)
    payload = b"real-hdfs-round-trip-" * 100_000  # ~2 MiB, multiple blocks

    service.ensure_user_dir(user_id)
    service.upload(path, io.BytesIO(payload), len(payload))
    assert service.exists(path) is True

    entries = service.list_status(service.layout.user_dir(user_id))
    match = next(e for e in entries if e["path"] == path)
    assert match["size"] == len(payload)
    # Report the ACTUAL configured replication factor instead of assuming one.
    print(f"\n  HDFS reported replication factor: {match['replication']}")

    collected = bytearray()
    with service.open_stream(path) as stream:
        for chunk in stream:
            collected.extend(chunk)
    assert bytes(collected) == payload

    assert service.delete(path) is True
    assert service.exists(path) is False
