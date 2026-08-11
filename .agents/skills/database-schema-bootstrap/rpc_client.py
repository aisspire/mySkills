from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


class MetadataServiceError(RuntimeError):
    """A safe, non-secret error from the independent metadata service."""


_OPERATIONS = {"list_databases", "list_tables", "describe_table"}
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024


def _metadata_url(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise MetadataServiceError("Metadata service endpoint is required.")
    endpoint = endpoint.strip().rstrip("/")
    try:
        parsed = urlsplit(endpoint)
    except ValueError as exc:
        raise MetadataServiceError("Metadata service endpoint is invalid.") from exc
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise MetadataServiceError("Metadata service endpoint is invalid.")
    return f"{endpoint}/v1/metadata"


class MetadataServiceClient:
    """AI-side RPC client; it has no PostgreSQL driver or credential access."""

    def __init__(self, endpoint: str, *, timeout: float = 10.0) -> None:
        if timeout <= 0:
            raise MetadataServiceError("Metadata service timeout must be positive.")
        self._url = _metadata_url(endpoint)
        self._timeout = timeout

    def _call(self, operation: str, **fields: Any) -> Any:
        if operation not in _OPERATIONS:
            raise MetadataServiceError("Unsupported metadata operation.")
        payload: dict[str, Any] = {"operation": operation, **fields}
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = response.read(_MAX_RESPONSE_BYTES + 1)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            raise MetadataServiceError(
                "Independent metadata service is unavailable or rejected the request."
            ) from None

        if len(body) > _MAX_RESPONSE_BYTES:
            raise MetadataServiceError("Metadata service response is too large.")
        try:
            response_data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise MetadataServiceError("Metadata service returned invalid JSON.") from None
        if not isinstance(response_data, dict) or response_data.get("ok") is not True:
            raise MetadataServiceError("Metadata service rejected the request.")
        if "result" not in response_data:
            raise MetadataServiceError("Metadata service returned an incomplete response.")
        return response_data["result"]

    def list_databases(self) -> list[dict[str, str]]:
        return self._call("list_databases")

    def list_tables(self) -> list[dict[str, str]]:
        return self._call("list_tables")

    def describe_table(self, table: str) -> dict[str, object]:
        return self._call("describe_table", table=table)

