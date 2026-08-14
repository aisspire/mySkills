from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


class MetadataServiceError(RuntimeError):
    """A safe, non-secret error from the independent metadata service."""


_OPERATIONS = {"list_databases", "list_tables", "describe_table"}
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_TOKEN_HEADER = "X-Database-Schema-Bootstrap-Token"


def validate_loopback_endpoint(endpoint: str) -> str:
    if not isinstance(endpoint, str) or not endpoint.strip():
        raise MetadataServiceError("Metadata service endpoint is required.")
    endpoint = endpoint.strip().rstrip("/")
    try:
        parsed = urlsplit(endpoint)
    except ValueError as exc:
        raise MetadataServiceError("Metadata service endpoint is invalid.") from exc
    if (
        parsed.scheme != "http"
        or not parsed.netloc
        or parsed.hostname != "127.0.0.1"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise MetadataServiceError("Metadata service endpoint is invalid.")
    try:
        port = parsed.port
    except ValueError as exc:
        raise MetadataServiceError("Metadata service endpoint is invalid.") from exc
    if port is None or not 1 <= port <= 65535:
        raise MetadataServiceError("Metadata service endpoint is invalid.")
    return f"http://127.0.0.1:{port}"


def _metadata_url(endpoint: str) -> str:
    return f"{validate_loopback_endpoint(endpoint)}/v1/metadata"


class MetadataServiceClient:
    """AI-side RPC client; it has no PostgreSQL driver or credential access."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 10.0,
        instance_token: str | None = None,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
        ):
            raise MetadataServiceError("Metadata service timeout must be a finite positive value.")
        if instance_token is not None and (
            not isinstance(instance_token, str) or not instance_token
        ):
            raise MetadataServiceError("Metadata service instance token is invalid.")
        self._endpoint = validate_loopback_endpoint(endpoint)
        self._url = f"{self._endpoint}/v1/metadata"
        self._health_url = f"{self._endpoint}/v1/health"
        self._timeout = float(timeout)
        self._instance_token = instance_token

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._instance_token is not None:
            headers[_TOKEN_HEADER] = self._instance_token
        return headers

    def _call(self, operation: str, **fields: Any) -> Any:
        if operation not in _OPERATIONS:
            raise MetadataServiceError("Unsupported metadata operation.")
        payload: dict[str, Any] = {"operation": operation, **fields}
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=self._headers(),
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

    def health(self, expected_project_id: str) -> dict[str, object]:
        if not isinstance(expected_project_id, str) or not expected_project_id:
            raise MetadataServiceError("Expected project identity is invalid.")
        request = urllib.request.Request(
            self._health_url,
            headers=self._headers(),
            method="GET",
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
        if (
            not isinstance(response_data, dict)
            or response_data.get("ok") is not True
            or response_data.get("project_id") != expected_project_id
        ):
            raise MetadataServiceError("Metadata service health check did not match the project.")
        return response_data

    def list_databases(self) -> list[dict[str, str]]:
        return self._call("list_databases")

    def list_tables(self) -> list[dict[str, str]]:
        return self._call("list_tables")

    def describe_table(self, table: str) -> dict[str, object]:
        return self._call("describe_table", table=table)
