from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlsplit


class MetadataServiceError(RuntimeError):
    """A safe, non-secret error from the local metadata gateway."""


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


class MetadataServiceClient:
    """HTTP client used only by the stdio adapter and control program."""

    def __init__(
        self,
        endpoint: str,
        *,
        timeout: float = 10.0,
        instance_token: str,
    ) -> None:
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(float(timeout))
            or timeout <= 0
        ):
            raise MetadataServiceError(
                "Metadata service timeout must be a finite positive value."
            )
        if not isinstance(instance_token, str) or not instance_token:
            raise MetadataServiceError("Metadata service instance token is invalid.")
        self.endpoint = validate_loopback_endpoint(endpoint)
        self.timeout = float(timeout)
        self.instance_token = instance_token

    def _headers(self, *, json_body: bool = False) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            _TOKEN_HEADER: self.instance_token,
        }
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, request: urllib.request.Request) -> dict[str, Any]:
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
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
        return response_data

    def health(
        self,
        *,
        expected_installation_id: str,
        expected_process_identity: str,
        expected_pid: int,
    ) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.endpoint}/v2/health",
            headers=self._headers(),
            method="GET",
        )
        response = self._request(request)
        if (
            response.get("version") != 2
            or response.get("protocol_version") != 2
            or response.get("installation_id") != expected_installation_id
            or response.get("process_identity") != expected_process_identity
            or response.get("pid") != expected_pid
        ):
            raise MetadataServiceError("Metadata service health identity did not match state.")
        return response

    def metadata(self, payload: dict[str, Any]) -> Any:
        request = urllib.request.Request(
            f"{self.endpoint}/v2/metadata",
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=self._headers(json_body=True),
            method="POST",
        )
        response = self._request(request)
        if "result" not in response:
            raise MetadataServiceError("Metadata service returned an incomplete response.")
        return response["result"]

    def shutdown(self) -> None:
        request = urllib.request.Request(
            f"{self.endpoint}/v2/control/shutdown",
            data=b'{"version":2}',
            headers=self._headers(json_body=True),
            method="POST",
        )
        response = self._request(request)
        if response.get("stopping") is not True:
            raise MetadataServiceError("Metadata service did not accept shutdown.")
