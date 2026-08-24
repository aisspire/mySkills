from __future__ import annotations

import hmac
import json
import logging
import os
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Protocol

from .errors import (
    ConfigError,
    ConnectionUnavailableError,
    GatewayError,
    PolicyError,
)


logger = logging.getLogger(__name__)
METADATA_PATH = "/v2/metadata"
HEALTH_PATH = "/v2/health"
SHUTDOWN_PATH = "/v2/control/shutdown"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
TOKEN_HEADER = "X-Database-Schema-Bootstrap-Token"


class Gateway(Protocol):
    def execute(self, payload: object) -> Any: ...


class MetadataHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        address: tuple[str, int],
        gateway: Gateway,
        *,
        instance_token: str,
        installation_id: str,
        process_identity: str,
    ) -> None:
        if address[0] != "127.0.0.1":
            raise ValueError("Metadata gateway must bind to 127.0.0.1.")
        if not instance_token or not installation_id or not process_identity:
            raise ValueError("Metadata gateway identity is incomplete.")
        super().__init__(address, MetadataRequestHandler)
        self.metadata_gateway = gateway
        self.instance_token = instance_token
        self.installation_id = installation_id
        self.process_identity = process_identity


class MetadataRequestHandler(BaseHTTPRequestHandler):
    server_version = "DatabaseSchemaBootstrap/2.0"
    protocol_version = "HTTP/1.1"

    @property
    def gateway(self) -> Gateway:
        return self.server.metadata_gateway  # type: ignore[attr-defined]

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
            "utf-8"
        )
        if len(body) > MAX_RESPONSE_BYTES:
            body = b'{"ok":false,"error":"Metadata response is too large."}'
            status = HTTPStatus.SERVICE_UNAVAILABLE
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _error(self, status: HTTPStatus, message: str) -> None:
        self._write_json(status, {"ok": False, "error": message})

    def _require_token(self) -> bool:
        expected = self.server.instance_token  # type: ignore[attr-defined]
        received = self.headers.get(TOKEN_HEADER, "")
        if hmac.compare_digest(received, expected):
            return True
        self._error(HTTPStatus.FORBIDDEN, "Metadata service token is invalid.")
        return False

    def _read_payload(self) -> object | None:
        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "-1")
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._error(HTTPStatus.BAD_REQUEST, "Invalid request size.")
            return None
        try:
            return json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "Request must be valid UTF-8 JSON.")
            return None

    def do_GET(self) -> None:  # noqa: N802
        if not self._require_token():
            return
        if self.path != HEALTH_PATH:
            self._error(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return
        self._write_json(
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
        if not self._require_token():
            return
        if self.path not in {METADATA_PATH, SHUTDOWN_PATH}:
            self._error(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return
        payload = self._read_payload()
        if payload is None:
            return
        if self.path == SHUTDOWN_PATH:
            if payload != {"version": 2}:
                self._error(HTTPStatus.BAD_REQUEST, "Shutdown request is invalid.")
                return
            self._write_json(HTTPStatus.OK, {"ok": True, "stopping": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        try:
            result = self.gateway.execute(payload)
        except PolicyError as exc:
            logger.warning("Rejected metadata request: %s", type(exc).__name__)
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except ConnectionUnavailableError:
            self._error(
                HTTPStatus.FORBIDDEN,
                "Current project connection is unavailable.",
            )
            return
        except ConfigError:
            logger.warning("Runtime metadata configuration is invalid.")
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Metadata service configuration is unavailable.",
            )
            return
        except GatewayError:
            logger.warning("Metadata operation failed.")
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Metadata service operation failed.",
            )
            return
        except Exception:
            logger.error("Unexpected metadata service failure.")
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Metadata service operation failed.",
            )
            return
        self._write_json(HTTPStatus.OK, {"ok": True, "result": result})

    def do_PUT(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def do_DELETE(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def do_HEAD(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def do_PATCH(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def do_OPTIONS(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def do_TRACE(self) -> None:  # noqa: N802
        if self._require_token():
            self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Method not allowed.")

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)
