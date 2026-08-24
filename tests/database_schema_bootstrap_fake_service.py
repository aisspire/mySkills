from __future__ import annotations

import hmac
import json
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


TOKEN_HEADER = "X-Database-Schema-Bootstrap-Token"
MAX_REQUEST_BYTES = 64 * 1024


class FakeGatewayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        *,
        installation_id: str,
        instance_token: str,
        process_identity: str,
        routes: dict[tuple[str, str], str],
    ) -> None:
        super().__init__(("127.0.0.1", 0), FakeGatewayHandler)
        self.installation_id = installation_id
        self.instance_token = instance_token
        self.process_identity = process_identity
        self.routes = routes


class FakeGatewayHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _write(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _authorized(self) -> bool:
        received = self.headers.get(TOKEN_HEADER, "")
        expected = self.server.instance_token  # type: ignore[attr-defined]
        if hmac.compare_digest(received, expected):
            return True
        self._write(HTTPStatus.FORBIDDEN, {"ok": False, "error": "invalid token"})
        return False

    def do_GET(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        if self.path != "/v2/health":
            self._write(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        self._write(
            HTTPStatus.OK,
            {
                "ok": True,
                "version": 2,
                "protocol_version": 2,
                "installation_id": self.server.installation_id,  # type: ignore[attr-defined]
                "pid": os.getpid(),
                "process_identity": self.server.process_identity,  # type: ignore[attr-defined]
            },
        )

    def do_POST(self) -> None:  # noqa: N802
        if not self._authorized():
            return
        if self.path == "/v2/control/shutdown":
            self._write(HTTPStatus.OK, {"ok": True, "stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if self.path != "/v2/metadata":
            self._write(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid size"})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(payload, dict):
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "invalid request"})
            return
        marker = self.server.routes.get(  # type: ignore[attr-defined]
            (payload.get("project_id"), payload.get("connection_id"))
        )
        operation = payload.get("operation")
        if marker is None:
            self._write(
                HTTPStatus.FORBIDDEN,
                {"ok": False, "error": "Current project connection is unavailable."},
            )
            return
        if operation == "list_databases":
            result: Any = [
                {"connection_id": payload["connection_id"], "database": f"{marker}_database"}
            ]
        elif operation == "list_tables":
            result = [
                {
                    "connection_id": payload["connection_id"],
                    "schema": "public",
                    "table": marker,
                }
            ]
        elif operation == "describe_table" and payload.get("table") == marker:
            result = {
                "connection_id": payload["connection_id"],
                "engine": "postgres",
                "schema": "public",
                "table": marker,
                "columns": [{"name": "id", "type": "bigint", "nullable": "NO"}],
                "constraints": [],
                "indexes": [],
            }
        else:
            self._write(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "unsupported"})
            return
        self._write(HTTPStatus.OK, {"ok": True, "result": result})

    def log_message(self, format: str, *args: object) -> None:
        return
