from __future__ import annotations

import argparse
import hmac
import json
import os
import pathlib
import re
import uuid
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


MAX_REQUEST_BYTES = 64 * 1024
TOKEN_HEADER = "X-Database-Schema-Bootstrap-Token"
MARKER_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def write_ready_state(
    path: str | pathlib.Path,
    *,
    endpoint: str,
    port: int,
    project_id: str,
    project_root: str,
    instance_token: str,
) -> None:
    """Write the same token-bound v1 shape used by the real loopback service."""

    ready_path = pathlib.Path(path)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "project_id": project_id,
        "project_root": project_root,
        "endpoint": endpoint,
        "port": port,
        "pid": os.getpid(),
        "instance_token": instance_token,
        "started_at": datetime.now(UTC).isoformat(),
    }
    temporary_path = ready_path.with_name(
        f".{ready_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary_path, ready_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def remove_ready_state_if_owned(
    path: str | pathlib.Path, *, instance_token: str
) -> None:
    """Never remove a state record created by a newer fixture instance."""

    ready_path = pathlib.Path(path)
    try:
        state = json.loads(ready_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if not isinstance(state, dict) or state.get("instance_token") != instance_token:
        return
    try:
        ready_path.unlink()
    except FileNotFoundError:
        return


class FakeMetadataHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def instance_token(self) -> str:
        return self.server.instance_token  # type: ignore[attr-defined]

    @property
    def project_id(self) -> str:
        return self.server.project_id  # type: ignore[attr-defined]

    @property
    def marker(self) -> str:
        return self.server.marker  # type: ignore[attr-defined]

    def _write_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _authorized(self) -> bool:
        received = self.headers.get(TOKEN_HEADER, "")
        return hmac.compare_digest(received, self.instance_token)

    def _require_token(self) -> bool:
        if self._authorized():
            return True
        self._write_json(
            HTTPStatus.FORBIDDEN,
            {"ok": False, "error": "Metadata service instance token is invalid."},
        )
        return False

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/v1/health":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
            return
        if not self._require_token():
            return
        self._write_json(
            HTTPStatus.OK,
            {"ok": True, "project_id": self.project_id},
        )

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/v1/metadata":
            self._write_json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found."})
            return
        if not self._require_token():
            return
        try:
            content_length = int(self.headers.get("Content-Length", "-1"))
        except ValueError:
            content_length = -1
        if content_length < 0 or content_length > MAX_REQUEST_BYTES:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Invalid request size."},
            )
            return
        try:
            request = json.loads(self.rfile.read(content_length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Request must be valid JSON."},
            )
            return
        operation = request.get("operation") if isinstance(request, dict) else None
        if operation == "list_databases":
            result: Any = [{"database": f"fake_{self.marker}_database"}]
        elif operation == "list_tables":
            result = [{"schema": "public", "table": self.marker}]
        elif operation == "describe_table" and request.get("table") == self.marker:
            result = {
                "table": self.marker,
                "columns": [{"name": "id", "type": "bigint", "nullable": False}],
                "constraints": [],
                "indexes": [],
            }
        else:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"ok": False, "error": "Unsupported fake metadata operation."},
            )
            return
        self._write_json(HTTPStatus.OK, {"ok": True, "result": result})

    def log_message(self, format: str, *args: object) -> None:
        return


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Loopback-only FakeService for the database-schema-bootstrap cwd smoke gate."
    )
    parser.add_argument("--ready-state", required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--instance-token", required=True)
    parser.add_argument("--marker", required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.instance_token.strip() or not MARKER_PATTERN.fullmatch(args.marker):
        return 2
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeMetadataHandler)
    server.instance_token = args.instance_token  # type: ignore[attr-defined]
    server.project_id = args.project_id  # type: ignore[attr-defined]
    server.marker = args.marker  # type: ignore[attr-defined]
    port = server.server_address[1]
    try:
        write_ready_state(
            args.ready_state,
            endpoint=f"http://127.0.0.1:{port}",
            port=port,
            project_id=args.project_id,
            project_root=str(pathlib.Path(args.project_root).resolve()),
            instance_token=args.instance_token,
        )
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
        remove_ready_state_if_owned(
            args.ready_state,
            instance_token=args.instance_token,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
