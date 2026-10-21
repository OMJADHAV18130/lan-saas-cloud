"""HDFS storage service.

Two adapters implement the same small interface:

  * ``WebHdfsService``  - real Apache Hadoop over the WebHDFS REST API.
                          This is the DEFAULT. File bytes go to HDFS.
  * ``MockHdfsService`` - LOCAL DISK stand-in for frontend development when
                          no Hadoop cluster exists. It is DISABLED by default
                          and must be selected explicitly with
                          ``HDFS_ADAPTER=mock``. It never pretends to be HDFS:
                          the status endpoint reports ``adapter=mock`` and a
                          visible warning.

WebHDFS protocol notes (implemented here, not assumed away):

  * A write starts with ``PUT /webhdfs/v1<path>?op=CREATE`` to the NameNode.
    The NameNode answers ``307 Temporary Redirect`` with a ``Location`` header
    pointing at a DataNode. The *actual bytes* must then be PUT to that
    Location. We therefore do NOT enable automatic redirect following for
    writes: we follow the redirect ourselves and only send the body once.
  * A read starts with ``GET ...?op=OPEN`` on the NameNode and is likewise
    redirected to a DataNode; the DataNode response is streamed in chunks.
  * WebHDFS errors are JSON ``RemoteException`` bodies. They are translated
    into safe application errors; internal details are logged server-side.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import time
from contextlib import contextmanager
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import IO, Iterator, Protocol
from urllib.parse import quote, urlparse

import httpx

from app.core.config import Settings, get_settings
from app.core.errors import Conflict, NotFound, StorageUnavailable

logger = logging.getLogger("cloud_controller.hdfs")

_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_UPLOAD_CHUNK = 1024 * 1024  # 1 MiB
_MAX_REDIRECTS = 4


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class HdfsStorage(Protocol):
    adapter_name: str

    def ensure_dir(self, path: str) -> None: ...
    def ensure_user_dir(self, user_id: str) -> str: ...
    def upload(self, path: str, fileobj: IO[bytes], length: int) -> None: ...
    def open_stream(self, path: str) -> object: ...
    def exists(self, path: str) -> bool: ...
    def delete(self, path: str, *, recursive: bool = False) -> bool: ...
    def list_status(self, path: str) -> list[dict]: ...
    def status(self) -> dict: ...


# ---------------------------------------------------------------------------
# Path safety
# ---------------------------------------------------------------------------
def validate_id(value: str, label: str = "identifier") -> str:
    """Only server-generated 32-char hex ids may appear in HDFS paths."""
    if not isinstance(value, str) or not _ID_RE.match(value):
        raise ValueError(f"Unsafe {label} used for a storage path.")
    return value


@dataclass(frozen=True)
class HdfsLayout:
    root: str

    def user_dir(self, user_id: str) -> str:
        validate_id(user_id, "user id")
        return f"{self.root}/users/{user_id}"

    def object_path(self, user_id: str, file_id: str) -> str:
        validate_id(user_id, "user id")
        validate_id(file_id, "file id")
        return f"{self.user_dir(user_id)}/{file_id}"


# ---------------------------------------------------------------------------
# Real WebHDFS adapter
# ---------------------------------------------------------------------------
class WebHdfsService:
    adapter_name = "webhdfs"

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self.settings = s
        self.layout = HdfsLayout(s.hdfs_root)
        self.base_url = s.hdfs_base_url.rstrip("/")
        parsed = urlparse(self.base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                "HDFS_BASE_URL must be an absolute http(s) URL, e.g. "
                "http://namenode-host:9870"
            )
        self._client = httpx.Client(
            timeout=httpx.Timeout(s.hdfs_timeout_seconds),
            follow_redirects=False,  # redirects are protocol steps here
            headers={"User-Agent": "lan-saas-cloud-controller/1.0"},
        )

    # -- low level -------------------------------------------------------
    def _url(self, path: str, op: str, **params: str | bool | int) -> str:
        if not path.startswith("/"):
            raise ValueError("HDFS paths must be absolute")
        query = {"op": op}
        if self.settings.hdfs_auth == "simple":
            query["user.name"] = self.settings.hdfs_service_user
        query.update({k: str(v).lower() if isinstance(v, bool) else str(v)
                      for k, v in params.items()})
        qs = "&".join(f"{quote(str(k))}={quote(str(v))}" for k, v in query.items())
        return f"{self.base_url}/webhdfs/v1{quote(path)}?{qs}"

    def _remote_message(self, response: httpx.Response) -> str:
        """Extract Hadoop's safe RemoteException message (never leaks creds)."""
        try:
            payload = response.json()
            if isinstance(payload, dict):
                err = payload.get("RemoteException", {})
                message = err.get("message") or err.get("exception") or ""
                return str(message)[:300]
        except Exception:  # noqa: BLE001 - non JSON body
            pass
        return ""

    def _raise_hdfs_error(self, response: httpx.Response, action: str) -> None:
        msg = self._remote_message(response)
        logger.error("WebHDFS %s failed: HTTP %s %s", action,
                     response.status_code, msg)
        if response.status_code in (401, 403):
            raise StorageUnavailable(
                "The storage service identity is not permitted to perform "
                "this operation. Contact the administrator.")
        if response.status_code == HTTPStatus.NOT_FOUND:
            raise NotFound("The requested object does not exist in storage.")
        if response.status_code >= 500:
            raise StorageUnavailable(
                "The HDFS cluster reported an internal error.")
        raise StorageUnavailable(
            f"Storage backend rejected the {action} operation "
            f"(HTTP {response.status_code}).")

    def _request(self, method: str, url: str, *, action: str,
                 **kwargs) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.TimeoutException as exc:
            logger.error("WebHDFS %s timed out: %s", action, exc)
            raise StorageUnavailable(
                "The HDFS NameNode did not respond in time.") from exc
        except httpx.HTTPError as exc:
            logger.error("WebHDFS %s connection error: %s", action, exc)
            raise StorageUnavailable(
                "The HDFS NameNode is unreachable. Check the cluster and the "
                "configured HDFS_BASE_URL.") from exc

    def _open(self, url: str, action: str) -> httpx.Response:
        """Start a streaming GET without consuming the body.

        httpx needs `send(..., stream=True)` for a lazily read response; that
        is what makes chunked download of large HDFS objects possible.
        """
        request = self._client.build_request("GET", url)
        try:
            return self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            logger.error("WebHDFS %s timed out: %s", action, exc)
            raise StorageUnavailable(
                "The HDFS NameNode did not respond in time.") from exc
        except httpx.HTTPError as exc:
            logger.error("WebHDFS %s connection error: %s", action, exc)
            raise StorageUnavailable(
                "The HDFS NameNode is unreachable. Check the cluster and the "
                "configured HDFS_BASE_URL.") from exc

    @staticmethod
    def _location(response: httpx.Response) -> str | None:
        if response.is_redirect:
            loc = response.headers.get("location")
            if loc:
                return loc
        return None

    # -- directories -----------------------------------------------------
    def ensure_dir(self, path: str) -> None:
        url = self._url(path, "MKDIRS", permission=self.settings.hdfs_dir_permission)
        resp = self._request("PUT", url, action="MKDIRS")
        if resp.status_code == HTTPStatus.OK:
            try:
                if resp.json().get("boolean") is False:
                    self._raise_hdfs_error(resp, "MKDIRS")
            except ValueError:
                pass
            return
        self._raise_hdfs_error(resp, "MKDIRS")

    def ensure_user_dir(self, user_id: str) -> str:
        path = self.layout.user_dir(user_id)
        self.ensure_dir(path)
        return path

    # -- write -----------------------------------------------------------
    def upload(self, path: str, fileobj: IO[bytes], length: int) -> None:
        """Create `path` in HDFS, following the NameNode -> DataNode redirect."""
        if length < 0:
            raise ValueError("length must be non-negative")

        create_url = self._url(
            path, "CREATE", overwrite="true",
            permission=self.settings.hdfs_file_permission,
        )
        first = self._request("PUT", create_url, action="CREATE",
                              content=b"", headers={"Content-Length": "0"})

        if first.status_code in (HTTPStatus.CREATED, HTTPStatus.OK):
            # Some gateways (e.g. HttpFS) complete the write directly.
            first.close()
            return

        location = self._location(first)
        if not location:
            self._raise_hdfs_error(first, "CREATE")

        hops = 0
        while location and hops < _MAX_REDIRECTS:
            hops += 1
            fileobj.seek(0)
            try:
                resp = self._client.put(
                    location,
                    content=_iter_file(fileobj),
                    headers={"Content-Length": str(length),
                             "Content-Type": "application/octet-stream"},
                )
            except httpx.TimeoutException as exc:
                raise StorageUnavailable(
                    "The HDFS DataNode did not accept the upload in time."
                ) from exc
            except httpx.HTTPError as exc:
                raise StorageUnavailable(
                    "The HDFS DataNode could not be reached for the upload."
                ) from exc

            if resp.status_code in (HTTPStatus.CREATED, HTTPStatus.OK):
                resp.close()
                return
            next_location = self._location(resp)
            if next_location:
                location = next_location
                resp.close()
                continue
            self._raise_hdfs_error(resp, "CREATE (DataNode)")

        raise StorageUnavailable("Too many redirects while writing to HDFS.")

    # -- read ------------------------------------------------------------
    @contextmanager
    def open_stream(self, path: str) -> Iterator[Iterator[bytes]]:
        """Stream an HDFS object, following the NameNode redirect.

        Yields an iterator of bytes. The caller must consume it inside the
        context manager; the underlying connection is closed afterwards.
        """
        open_url = self._url(path, "OPEN")
        resp = self._open(open_url, "OPEN")
        hops = 0
        while True:
            location = self._location(resp)
            if not location:
                break
            hops += 1
            if hops > _MAX_REDIRECTS:
                resp.close()
                raise StorageUnavailable("Too many redirects while reading "
                                         "from HDFS.")
            resp.close()
            resp = self._open(location, "OPEN (DataNode)")

        if resp.status_code >= 400:
            try:
                resp.read()
                self._raise_hdfs_error(resp, "OPEN")
            finally:
                resp.close()

        try:
            yield resp.iter_bytes(_UPLOAD_CHUNK)
        finally:
            resp.close()

    def read_all(self, path: str, limit: int = 1024 * 1024) -> bytes:
        """Read a small object fully (used for diagnostics in tests)."""
        chunks: list[bytes] = []
        total = 0
        with self.open_stream(path) as stream:
            for chunk in stream:
                total += len(chunk)
                if total > limit:
                    raise StorageUnavailable("Object exceeds read limit.")
                chunks.append(chunk)
        return b"".join(chunks)

    # -- misc -------------------------------------------------------------
    def exists(self, path: str) -> bool:
        url = self._url(path, "GETFILESTATUS")
        resp = self._request("GET", url, action="GETFILESTATUS")
        try:
            if resp.status_code == HTTPStatus.OK:
                return True
            if resp.status_code == HTTPStatus.NOT_FOUND:
                return False
            self._raise_hdfs_error(resp, "GETFILESTATUS")
            return False
        finally:
            resp.close()

    def delete(self, path: str, *, recursive: bool = False) -> bool:
        url = self._url(path, "DELETE", recursive="true" if recursive else "false")
        resp = self._request("DELETE", url, action="DELETE")
        try:
            if resp.status_code == HTTPStatus.NOT_FOUND:
                return False
            if resp.status_code != HTTPStatus.OK:
                self._raise_hdfs_error(resp, "DELETE")
            payload = resp.json()
            return bool(payload.get("boolean", False))
        finally:
            resp.close()

    def list_status(self, path: str) -> list[dict]:
        url = self._url(path, "LISTSTATUS")
        resp = self._request("GET", url, action="LISTSTATUS")
        try:
            if resp.status_code == HTTPStatus.NOT_FOUND:
                raise NotFound("Storage directory does not exist.")
            if resp.status_code != HTTPStatus.OK:
                self._raise_hdfs_error(resp, "LISTSTATUS")
            entries = resp.json().get("FileStatuses", {}).get("FileStatus", [])
            return [
                {
                    "path": f"{path.rstrip('/')}/{e.get('pathSuffix', '')}",
                    "type": e.get("type"),
                    "size": int(e.get("length", 0)),
                    "replication": int(e.get("replication", 0)),
                    "owner": e.get("owner"),
                    "permission": e.get("permission"),
                    "modification_time": e.get("modificationTime"),
                }
                for e in entries
            ]
        finally:
            resp.close()

    # -- health ------------------------------------------------------------
    def status(self) -> dict:
        """Honest health report. Never invents DataNode information."""
        started = time.perf_counter()
        base = {
            "adapter": self.adapter_name,
            "mode_label": "Apache Hadoop HDFS (WebHDFS)",
            "namenode_url": self.base_url,
            "root": self.settings.hdfs_root,
            "latency_ms": None,
            "datanodes": None,
            "healthy": None,
            "message": "",
        }
        try:
            url = self._url(self.settings.hdfs_root, "GETFILESTATUS")
            resp = self._client.get(url)
            latency = round((time.perf_counter() - started) * 1000, 1)
            base["latency_ms"] = latency
            if resp.status_code == HTTPStatus.NOT_FOUND:
                base["healthy"] = False
                base["message"] = (
                    f"NameNode reachable, but the configured root "
                    f"{self.settings.hdfs_root} does not exist. "
                    "Run the HDFS bootstrap commands from the README."
                )
            elif resp.status_code == HTTPStatus.OK:
                base["healthy"] = True
                base["message"] = "NameNode reachable; configured root exists."
            else:
                base["healthy"] = False
                base["message"] = (
                    f"NameNode reachable but returned HTTP {resp.status_code}."
                )
            resp.close()
        except httpx.TimeoutException:
            base["healthy"] = False
            base["message"] = "NameNode request timed out."
            return base
        except httpx.HTTPError as exc:
            logger.warning("HDFS status check failed: %s", exc)
            base["healthy"] = False
            base["message"] = "NameNode is unreachable."
            return base

        base["datanodes"] = self._datanode_info()
        return base

    def _datanode_info(self) -> dict:
        """DataNode liveness via NameNode JMX, only if explicitly configured."""
        jmx_url = self.settings.hdfs_jmx_url.strip()
        if not jmx_url:
            return {
                "available": None,
                "live": None,
                "dead": None,
                "reason": "HDFS_JMX_URL is not configured; DataNode liveness "
                          "is not exposed by the WebHDFS REST API.",
            }
        try:
            resp = self._client.get(jmx_url, params={
                "qry": "Hadoop:service=NameNode,name=NameNodeInfo"})
            resp.raise_for_status()
            beans = resp.json().get("beans", [])
            bean = beans[0] if beans else {}
            live = bean.get("LiveNodes")
            dead = bean.get("DeadNodes")
            return {
                "available": True,
                "live": len(live) if isinstance(live, list) else live,
                "dead": len(dead) if isinstance(dead, list) else dead,
                "reason": None,
            }
        except Exception as exc:  # noqa: BLE001 - diagnostic only
            logger.warning("JMX DataNode query failed: %s", exc)
            return {
                "available": False,
                "live": None,
                "dead": None,
                "reason": "JMX endpoint could not be queried.",
            }

    def close(self) -> None:
        self._client.close()


def _iter_file(fileobj: IO[bytes], chunk_size: int = _UPLOAD_CHUNK) -> Iterator[bytes]:
    while True:
        chunk = fileobj.read(chunk_size)
        if not chunk:
            break
        yield chunk


# ---------------------------------------------------------------------------
# Mock adapter - explicitly opt-in, local disk, clearly labelled
# ---------------------------------------------------------------------------
class MockHdfsService:
    """LOCAL DISK stand-in. NOT HDFS.

    Enabled only with ``HDFS_ADAPTER=mock``. Exists so the React UI can be
    developed on a machine without Hadoop. The health endpoint and the UI
    display a visible "mock" badge, and startup logs a loud warning.
    """

    adapter_name = "mock"

    def __init__(self, settings: Settings | None = None):
        s = settings or get_settings()
        self.settings = s
        self.layout = HdfsLayout(s.hdfs_root)
        self.root_dir = Path(s.hdfs_mock_dir).resolve()
        self.root_dir.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "HDFS MOCK ADAPTER ACTIVE - files are stored on local disk at %s, "
            "NOT in HDFS. This mode is for UI development only.",
            self.root_dir,
        )

    def _fs(self, path: str) -> Path:
        if not path.startswith(self.settings.hdfs_root + "/"):
            raise ValueError("Path outside the configured HDFS root.")
        candidate = (self.root_dir / path.lstrip("/")).resolve()
        if self.root_dir not in candidate.parents and candidate != self.root_dir:
            raise ValueError("Path escapes the mock storage root.")
        return candidate

    def ensure_dir(self, path: str) -> None:
        self._fs(path).mkdir(parents=True, exist_ok=True)

    def ensure_user_dir(self, user_id: str) -> str:
        path = self.layout.user_dir(user_id)
        self.ensure_dir(path)
        return path

    def upload(self, path: str, fileobj: IO[bytes], length: int) -> None:
        target = self._fs(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".part")
        written = 0
        with open(tmp, "wb") as out:
            while True:
                chunk = fileobj.read(_UPLOAD_CHUNK)
                if not chunk:
                    break
                written += len(chunk)
                out.write(chunk)
        if written != length:
            tmp.unlink(missing_ok=True)
            raise StorageUnavailable("Mock storage received an incomplete file.")
        os.replace(tmp, target)

    @contextmanager
    def open_stream(self, path: str) -> Iterator[Iterator[bytes]]:
        target = self._fs(path)
        if not target.is_file():
            raise NotFound("The requested object does not exist in storage.")
        fh = open(target, "rb")
        try:
            yield _iter_file(fh)
        finally:
            fh.close()

    def exists(self, path: str) -> bool:
        try:
            return self._fs(path).is_file()
        except ValueError:
            return False

    def delete(self, path: str, *, recursive: bool = False) -> bool:
        target = self._fs(path)
        if target.is_dir() and recursive:
            shutil.rmtree(target, ignore_errors=True)
            return True
        if target.exists():
            target.unlink()
            return True
        return False

    def list_status(self, path: str) -> list[dict]:
        target = self._fs(path)
        if not target.is_dir():
            raise NotFound("Storage directory does not exist.")
        result = []
        for entry in sorted(target.iterdir()):
            stat = entry.stat()
            result.append({
                "path": f"{path.rstrip('/')}/{entry.name}",
                "type": "DIRECTORY" if entry.is_dir() else "FILE",
                "size": stat.st_size,
                "replication": 0,
                "owner": "mock",
                "permission": "mock",
                "modification_time": int(stat.st_mtime * 1000),
            })
        return result

    def status(self) -> dict:
        return {
            "adapter": "mock",
            "mode_label": "MOCK local-disk adapter (NOT HDFS)",
            "namenode_url": None,
            "root": self.settings.hdfs_root,
            "latency_ms": 0.0,
            "datanodes": {
                "available": None, "live": None, "dead": None,
                "reason": "Mock adapter has no DataNodes.",
            },
            "healthy": None,
            "message": "Mock storage is active. File contents are on local "
                       "disk, not in HDFS. Do not use for the lab demonstration.",
        }

    def close(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------
def build_hdfs_service(settings: Settings | None = None) -> HdfsStorage:
    s = settings or get_settings()
    if s.hdfs_adapter == "mock":
        return MockHdfsService(s)
    return WebHdfsService(s)


def sha256_file(fileobj: IO[bytes], chunk: int = _UPLOAD_CHUNK) -> tuple[str, int]:
    """Hash a spooled upload without keeping it in memory."""
    digest = hashlib.sha256()
    fileobj.seek(0)
    size = 0
    while True:
        data = fileobj.read(chunk)
        if not data:
            break
        size += len(data)
        digest.update(data)
    fileobj.seek(0)
    return digest.hexdigest(), size
