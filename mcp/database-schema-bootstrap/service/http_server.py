from __future__ import annotations

import json
import logging
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .errors import GatewayError, PolicyError
from .protocol import MetadataOperations, dispatch_metadata


logger = logging.getLogger(__name__)
METADATA_PATH = "/v1/metadata"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 8 * 1024 * 1024


class MetadataHttpServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service: MetadataOperations):
        super().__init__(address, MetadataRequestHandler)
        self.metadata_service = service


class MetadataRequestHandler(BaseHTTPRequestHandler):
    server_version = "DatabaseSchemaBootstrap/1.0"
    protocol_version = "HTTP/1.1"

    @property
    def metadata_service(self) -> MetadataOperations:
        return self.server.metadata_service  # type: ignore[attr-defined]

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

    def do_POST(self) -> None:  # noqa: N802
        if self.path != METADATA_PATH:
            self._error(HTTPStatus.NOT_FOUND, "Endpoint not found.")
            return

        raw_length = self.headers.get("Content-Length")
        try:
            length = int(raw_length or "-1")
        except ValueError:
            length = -1
        if length < 0 or length > MAX_REQUEST_BYTES:
            self._error(HTTPStatus.BAD_REQUEST, "Invalid request size.")
            return

        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._error(HTTPStatus.BAD_REQUEST, "Request must be valid UTF-8 JSON.")
            return

        try:
            result = dispatch_metadata(self.metadata_service, payload)
        except PolicyError as exc:
            logger.warning("Rejected metadata request: %s", exc)
            self._error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        except GatewayError as exc:
            logger.warning("Metadata operation failed: %s", exc)
            self._error(HTTPStatus.SERVICE_UNAVAILABLE, str(exc))
            return
        except Exception:
            logger.exception("Unexpected metadata service failure")
            self._error(
                HTTPStatus.SERVICE_UNAVAILABLE,
                "Metadata service operation failed.",
            )
            return

        self._write_json(HTTPStatus.OK, {"ok": True, "result": result})

    def do_GET(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Only the metadata operation is available.")

    def do_PUT(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Only the metadata operation is available.")

    def do_DELETE(self) -> None:  # noqa: N802
        self._error(HTTPStatus.METHOD_NOT_ALLOWED, "Only the metadata operation is available.")

    def log_message(self, format: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), format % args)

