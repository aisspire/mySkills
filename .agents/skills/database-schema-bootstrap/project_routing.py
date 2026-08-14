from __future__ import annotations

import hashlib
import json
import math
import os
import pathlib
import subprocess
import time
from collections.abc import Callable
from typing import Any, Protocol

from rpc_client import (
    MetadataServiceClient,
    MetadataServiceError,
    validate_loopback_endpoint,
)


class ProjectRoutingError(MetadataServiceError):
    """The current workspace cannot safely reach a matching metadata instance."""


class MetadataClient(Protocol):
    def health(self, expected_project_id: str) -> dict[str, object]: ...

    def list_databases(self) -> list[dict[str, str]]: ...

    def list_tables(self) -> list[dict[str, str]]: ...

    def describe_table(self, table: str) -> dict[str, object]: ...


_ROUTING_TIMEOUT_MESSAGE = "Database metadata service routing timed out."


def _validate_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise MetadataServiceError("Metadata service timeout must be a finite positive value.")
    return float(timeout)


def canonical_project_root(path: str | os.PathLike[str]) -> str:
    """Return the cross-process canonical spelling used for state identity.

    Matches the PowerShell control script and metadata service normalization:
    lexical absolute path with ``.``/``..`` resolved, Windows case and
    separators normalized, and trailing separators removed. Resolving reparse
    points here would produce a different project id than the state writer uses
    when a workspace is opened through a junction or symlink.
    """

    try:
        normalized = os.path.normcase(
            os.path.normpath(os.path.abspath(os.fspath(path)))
        )
    except (OSError, TypeError, ValueError) as exc:
        raise ProjectRoutingError("Current project identity is unavailable.") from exc
    drive, tail = os.path.splitdrive(normalized)
    root = drive + os.path.sep if drive and tail.startswith(("/", "\\")) else os.path.sep
    if normalized != root:
        normalized = normalized.rstrip("\\/")
    if not normalized:
        raise ProjectRoutingError("Current project identity is unavailable.")
    return normalized


def project_id_for_root(path: str | os.PathLike[str]) -> str:
    canonical_root = canonical_project_root(path)
    return hashlib.sha256(canonical_root.encode("utf-8")).hexdigest()


def discover_git_project_root(timeout: float = 5.0) -> pathlib.Path:
    """Resolve only a Git project root; never infer an arbitrary parent directory."""

    try:
        git_timeout = min(_validate_timeout(timeout), 5.0)
    except MetadataServiceError as exc:
        raise ProjectRoutingError(_ROUTING_TIMEOUT_MESSAGE) from exc
    try:
        result = subprocess.run(
            ["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=git_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ProjectRoutingError(_ROUTING_TIMEOUT_MESSAGE) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProjectRoutingError(
            "Current workspace is not a confirmed Git project; database metadata is unavailable."
        ) from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ProjectRoutingError(
            "Current workspace is not a confirmed Git project; database metadata is unavailable."
        )
    return pathlib.Path(result.stdout.strip())


def _read_matching_state(
    state_root: pathlib.Path,
    project_root: str,
    project_id: str,
) -> tuple[str, str]:
    state_path = state_root / f"{project_id}.json"
    try:
        raw_state: Any = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise ProjectRoutingError(
            "No active database metadata service is available for the current project."
        ) from exc
    if not isinstance(raw_state, dict):
        raise ProjectRoutingError("Project metadata service state is invalid.")

    endpoint = raw_state.get("endpoint")
    token = raw_state.get("instance_token")
    port = raw_state.get("port")
    if (
        raw_state.get("version") != 1
        or raw_state.get("project_id") != project_id
        or not isinstance(raw_state.get("project_root"), str)
        or not isinstance(endpoint, str)
        or not isinstance(token, str)
        or not token
        or isinstance(port, bool)
        or not isinstance(port, int)
    ):
        raise ProjectRoutingError("Project metadata service state is invalid.")
    try:
        state_project_root = canonical_project_root(raw_state["project_root"])
        normalized_endpoint = validate_loopback_endpoint(endpoint)
        endpoint_port = int(normalized_endpoint.rsplit(":", 1)[1])
    except MetadataServiceError as exc:
        raise ProjectRoutingError("Project metadata service state is invalid.") from exc
    if state_project_root != project_root or port != endpoint_port:
        raise ProjectRoutingError(
            "Project metadata service state does not match the current workspace."
        )
    return normalized_endpoint, token


class ProjectMetadataRouter:
    """Resolve the current project and health-check its service for every tool call."""

    def __init__(
        self,
        state_root: str | os.PathLike[str],
        *,
        project_root_resolver: Callable[[], pathlib.Path] | None = None,
        client_factory: Callable[..., MetadataClient] = MetadataServiceClient,
        timeout: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._state_root = pathlib.Path(state_root)
        self._project_root_resolver = project_root_resolver or discover_git_project_root
        self._uses_default_project_root_resolver = project_root_resolver is None
        self._client_factory = client_factory
        self._timeout = _validate_timeout(timeout)
        self._clock = clock

    def _remaining_timeout(self, deadline: float) -> float:
        remaining = deadline - self._clock()
        if not math.isfinite(remaining) or remaining <= 0:
            raise ProjectRoutingError(_ROUTING_TIMEOUT_MESSAGE)
        return remaining

    def _resolve_project_root(self, deadline: float) -> pathlib.Path:
        remaining = self._remaining_timeout(deadline)
        if self._uses_default_project_root_resolver:
            project_root = discover_git_project_root(timeout=min(remaining, 5.0))
        else:
            project_root = self._project_root_resolver()
        self._remaining_timeout(deadline)
        return pathlib.Path(project_root)

    def _call_for_current_project(self, callback: Callable[[MetadataClient], Any]) -> Any:
        deadline = self._clock() + self._timeout
        try:
            project_root = canonical_project_root(self._resolve_project_root(deadline))
            project_id = project_id_for_root(project_root)
            endpoint, instance_token = _read_matching_state(
                self._state_root,
                project_root,
                project_id,
            )
            health_client = self._client_factory(
                endpoint,
                instance_token=instance_token,
                timeout=self._remaining_timeout(deadline),
            )
            health_client.health(project_id)
            metadata_client = self._client_factory(
                endpoint,
                instance_token=instance_token,
                timeout=self._remaining_timeout(deadline),
            )
            result = callback(metadata_client)
            self._remaining_timeout(deadline)
            return result
        except ProjectRoutingError:
            raise
        except MetadataServiceError as exc:
            raise ProjectRoutingError(
                "Database metadata service is unavailable for the current project."
            ) from exc
        except Exception as exc:
            raise ProjectRoutingError(
                "Database metadata service is unavailable for the current project."
            ) from exc

    def list_databases(self) -> list[dict[str, str]]:
        return self._call_for_current_project(lambda client: client.list_databases())

    def list_tables(self) -> list[dict[str, str]]:
        return self._call_for_current_project(lambda client: client.list_tables())

    def describe_table(self, table: str) -> dict[str, object]:
        return self._call_for_current_project(lambda client: client.describe_table(table))
