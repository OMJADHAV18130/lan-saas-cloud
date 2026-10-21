"""A tiny fake WebHDFS server used to verify protocol behaviour.

It mimics the parts of Hadoop that matter for the controller:

  * NameNode ``op=CREATE`` -> 307 redirect to a DataNode endpoint
  * DataNode PUT receives the bytes and returns ``201 Created``
  * NameNode ``op=OPEN`` -> 307 redirect to a DataNode read endpoint
  * DataNode read streams the stored bytes
  * GETFILESTATUS / LISTSTATUS / DELETE return Hadoop-shaped JSON
  * missing objects return a remote exception with HTTP 404

This is a TEST DOUBLE for unit tests. It is not shipped as a storage adapter.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse


class FakeWebHdfsServer:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.directories: set[str] = {"/"}
        self.redirects_served = 0
        self.received_body_lengths: list[int] = []
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(self))
        self.port = self._server.server_address[1]
        self.thread = threading.Thread(target=self._server.serve_forever,
                                       daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeWebHdfsServer":
        self.thread.start()
        return self

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


def _json(handler: BaseHTTPRequestHandler, status: int, payload: dict) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler: BaseHTTPRequestHandler, location: str) -> None:
    handler.send_response(307)
    handler.send_header("Location", location)
    handler.send_header("Content-Length", "0")
    handler.end_headers()


def _remote_exception(handler: BaseHTTPRequestHandler, status: int,
                      message: str) -> None:
    _json(handler, status, {"RemoteException": {
        "exception": "FileNotFoundException" if status == 404 else "IOException",
        "javaClassName": "java.io.IOException",
        "message": message,
    }})


def _make_handler(state: FakeWebHdfsServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):  # silence test output
            return

        # -- helpers -----------------------------------------------------
        def _content_length(self) -> int:
            return int(self.headers.get("Content-Length", "0") or 0)

        # -- routing -----------------------------------------------------
        def do_PUT(self):  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            if parsed.path.startswith("/datanode/write"):
                length = self._content_length()
                body = self.rfile.read(length) if length else b""
                state.received_body_lengths.append(len(body))
                state.objects[parsed.path.replace("/datanode/write", "", 1)] = body
                self.send_response(201)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            if parsed.path.startswith("/webhdfs/v1"):
                hdfs_path = parsed.path[len("/webhdfs/v1"):]
                op = (qs.get("op") or [""])[0]
                if op == "CREATE":
                    state.redirects_served += 1
                    _redirect(self, f"{state.base_url}/datanode/write{hdfs_path}")
                    return
                if op == "MKDIRS":
                    _json(self, 200, {"boolean": True})
                    return
            _remote_exception(self, 400, "Unsupported PUT")

        def do_GET(self):  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)

            if parsed.path.startswith("/datanode/read"):
                hdfs_path = parsed.path.replace("/datanode/read", "", 1)
                if hdfs_path not in state.objects:
                    _remote_exception(self, 404, f"File not found: {hdfs_path}")
                    return
                data = state.objects[hdfs_path]
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                # write in small pieces to exercise streaming
                for i in range(0, len(data), 65536):
                    self.wfile.write(data[i:i + 65536])
                return

            if parsed.path.startswith("/webhdfs/v1"):
                hdfs_path = parsed.path[len("/webhdfs/v1"):]
                op = (qs.get("op") or [""])[0]
                if op == "OPEN":
                    if hdfs_path not in state.objects:
                        _remote_exception(self, 404, f"File not found: {hdfs_path}")
                        return
                    state.redirects_served += 1
                    _redirect(self, f"{state.base_url}/datanode/read{hdfs_path}")
                    return
                if op == "GETFILESTATUS":
                    if hdfs_path in state.objects or hdfs_path in state.directories:
                        _json(self, 200, {"FileStatus": {
                            "type": "FILE" if hdfs_path in state.objects else "DIRECTORY",
                            "length": len(state.objects.get(hdfs_path, b"")),
                            "replication": 1,
                            "permission": "640",
                            "owner": "saascloud",
                            "modificationTime": 1700000000000,
                        }})
                        return
                    _remote_exception(self, 404, f"File not found: {hdfs_path}")
                    return
                if op == "LISTSTATUS":
                    prefix = hdfs_path.rstrip("/") + "/"
                    entries = [
                        p for p in state.objects
                        if p.startswith(prefix) and "/" not in p[len(prefix):]
                    ]
                    if not entries and hdfs_path not in state.directories:
                        _remote_exception(self, 404, "Directory not found")
                        return
                    _json(self, 200, {"FileStatuses": {"FileStatus": [
                        {"pathSuffix": p[len(prefix):], "type": "FILE",
                         "length": len(state.objects[p]), "replication": 1,
                         "owner": "saascloud", "permission": "640",
                         "modificationTime": 1700000000000}
                        for p in entries
                    ]}})
                    return
            _remote_exception(self, 400, "Unsupported GET")

        def do_DELETE(self):  # noqa: N802
            parsed = urlparse(self.path)
            qs = parse_qs(parsed.query)
            if parsed.path.startswith("/webhdfs/v1"):
                hdfs_path = parsed.path[len("/webhdfs/v1"):]
                op = (qs.get("op") or [""])[0]
                if op == "DELETE":
                    if hdfs_path in state.objects:
                        del state.objects[hdfs_path]
                        _json(self, 200, {"boolean": True})
                        return
                    _remote_exception(self, 404, "File not found")
                    return
            _remote_exception(self, 400, "Unsupported DELETE")

    return Handler
