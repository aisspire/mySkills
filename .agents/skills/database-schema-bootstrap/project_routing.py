from __future__ import annotations

import json
import math
import os
import pathlib
import re
import subprocess
import sys
import time
import uuid
from collections.abc import Callable
from typing import Any, Protocol

from rpc_client import (
    MetadataServiceClient,
    MetadataServiceError,
    validate_loopback_endpoint,
)


ACCESS_RELATIVE_PATH = pathlib.Path(".agents") / "database-schema-bootstrap" / "access.json"
CONNECTION_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,63}\Z")
INSTALL_STATE_FIELDS = {
    "version",
    "installation_id",
    "runtime_root",
    "config_path",
    "config_block_hash",
    "python_path",
    "dependency_installation",
    "managed_files",
    "managed_trees",
    "installed_at",
}
SERVICE_STATE_FIELDS = {
    "version",
    "protocol_version",
    "installation_id",
    "endpoint",
    "port",
    "pid",
    "instance_token",
    "process_identity",
    "started_at",
}


class ProjectRoutingError(MetadataServiceError):
    """The current Git project cannot use a verified v2 gateway."""


class MetadataClient(Protocol):
    def health(
        self,
        *,
        expected_installation_id: str,
        expected_process_identity: str,
        expected_pid: int,
    ) -> dict[str, Any]: ...

    def metadata(self, payload: dict[str, Any]) -> Any: ...


_ROUTING_TIMEOUT_MESSAGE = "Database metadata service routing timed out."


def _validate_timeout(timeout: float) -> float:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or timeout <= 0
    ):
        raise MetadataServiceError(
            "Metadata service timeout must be a finite positive value."
        )
    return float(timeout)


def canonical_project_root(path: str | os.PathLike[str]) -> str:
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


def discover_git_project_root(timeout: float = 5.0) -> pathlib.Path:
    try:
        result = subprocess.run(
            ["git", "-C", os.getcwd(), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=min(_validate_timeout(timeout), 5.0),
        )
    except subprocess.TimeoutExpired as exc:
        raise ProjectRoutingError(_ROUTING_TIMEOUT_MESSAGE) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ProjectRoutingError(
            "Current workspace is not a confirmed Git project."
        ) from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ProjectRoutingError("Current workspace is not a confirmed Git project.")
    return pathlib.Path(result.stdout.strip())


def _read_json(path: pathlib.Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise ProjectRoutingError(f"{label} is unavailable.") from exc
    if not isinstance(data, dict):
        raise ProjectRoutingError(f"{label} is invalid.")
    return data


def _read_access(project_root: str) -> tuple[str, dict[str, bool], str | None]:
    data = _read_json(
        pathlib.Path(project_root) / ACCESS_RELATIVE_PATH,
        label="Project database access configuration",
    )
    if set(data) != {"version", "project_id", "connections", "active"}:
        raise ProjectRoutingError("Project database access configuration is invalid.")
    project_id = data.get("project_id")
    raw_connections = data.get("connections")
    active = data.get("active")
    try:
        valid_uuid = str(uuid.UUID(project_id)) if isinstance(project_id, str) else ""
    except ValueError:
        valid_uuid = ""
    if data.get("version") != 2 or project_id != valid_uuid:
        raise ProjectRoutingError("Project database access configuration is invalid.")
    if not isinstance(raw_connections, dict):
        raise ProjectRoutingError("Project database access configuration is invalid.")
    connections: dict[str, bool] = {}
    for connection_id, record in raw_connections.items():
        if (
            not isinstance(connection_id, str)
            or not CONNECTION_ID_PATTERN.fullmatch(connection_id)
            or not isinstance(record, dict)
            or set(record) != {"enabled"}
            or not isinstance(record.get("enabled"), bool)
        ):
            raise ProjectRoutingError("Project database access configuration is invalid.")
        connections[connection_id] = record["enabled"]
    if active is not None and (
        not isinstance(active, str)
        or active not in connections
        or connections[active] is not True
    ):
        raise ProjectRoutingError("Project database access configuration is invalid.")
    return project_id, connections, active


def _select_connection(
    connections: dict[str, bool], active: str | None, requested: str | None
) -> str:
    if requested is not None:
        if (
            not isinstance(requested, str)
            or not CONNECTION_ID_PATTERN.fullmatch(requested)
            or connections.get(requested) is not True
        ):
            raise ProjectRoutingError("Current project connection is unavailable.")
        return requested
    if active is None or connections.get(active) is not True:
        raise ProjectRoutingError("Current project connection is unavailable.")
    return active


class ProjectMetadataRouter:
    """Resolve access/state/health again for every MCP tool call."""

    def __init__(
        self,
        runtime_root: str | os.PathLike[str],
        *,
        project_root_resolver: Callable[[], pathlib.Path] | None = None,
        client_factory: Callable[..., MetadataClient] = MetadataServiceClient,
        timeout: float = 25.0,
        clock: Callable[[], float] = time.monotonic,
        ensure_runner: Callable[[str, float], None] | None = None,
    ) -> None:
        self.runtime_root = pathlib.Path(runtime_root)
        self._project_root_resolver = project_root_resolver or discover_git_project_root
        self._uses_default_resolver = project_root_resolver is None
        self._client_factory = client_factory
        self._timeout = _validate_timeout(timeout)
        self._clock = clock
        self._ensure_runner = ensure_runner or self._run_ensure

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self._clock()
        if not math.isfinite(remaining) or remaining <= 0:
            raise ProjectRoutingError(_ROUTING_TIMEOUT_MESSAGE)
        return remaining

    def _resolve_root(self, deadline: float) -> str:
        if self._uses_default_resolver:
            path = discover_git_project_root(timeout=min(self._remaining(deadline), 5.0))
        else:
            path = self._project_root_resolver()
        self._remaining(deadline)
        return canonical_project_root(path)

    def _installation_id(self) -> str:
        data = _read_json(
            self.runtime_root / "install-state.json",
            label="Database metadata runtime installation state",
        )
        if set(data) != INSTALL_STATE_FIELDS:
            raise ProjectRoutingError("Database metadata runtime installation state is invalid.")
        installation_id = data.get("installation_id")
        if (
            data.get("version") != 2
            or data.get("dependency_installation") != "completed"
            or not isinstance(installation_id, str)
            or not installation_id
        ):
            raise ProjectRoutingError("Database metadata runtime is incomplete.")
        return installation_id

    def _service_client(self, installation_id: str, deadline: float) -> MetadataClient:
        data = _read_json(
            self.runtime_root / "state" / "service.json",
            label="Database metadata service state",
        )
        if set(data) != SERVICE_STATE_FIELDS:
            raise ProjectRoutingError("Database metadata service state is invalid.")
        endpoint = data.get("endpoint")
        token = data.get("instance_token")
        process_identity = data.get("process_identity")
        port = data.get("port")
        pid = data.get("pid")
        if (
            data.get("version") != 2
            or data.get("protocol_version") != 2
            or data.get("installation_id") != installation_id
            or not isinstance(endpoint, str)
            or not isinstance(token, str)
            or not token
            or not isinstance(process_identity, str)
            or not process_identity
            or isinstance(port, bool)
            or not isinstance(port, int)
            or isinstance(pid, bool)
            or not isinstance(pid, int)
            or pid <= 0
        ):
            raise ProjectRoutingError("Database metadata service state is invalid.")
        normalized = validate_loopback_endpoint(endpoint)
        if int(normalized.rsplit(":", 1)[1]) != port:
            raise ProjectRoutingError("Database metadata service state is invalid.")
        client = self._client_factory(
            normalized,
            instance_token=token,
            timeout=self._remaining(deadline),
        )
        client.health(
            expected_installation_id=installation_id,
            expected_process_identity=process_identity,
            expected_pid=pid,
        )
        return client

    def _run_ensure(self, project_root: str, timeout: float) -> None:
        control = self.runtime_root / "control" / "control.py"
        try:
            result = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(control),
                    "--runtime-root",
                    str(self.runtime_root),
                    "service",
                    "ensure",
                    "--hook",
                    "--project-root",
                    project_root,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ProjectRoutingError("Database metadata service could not be started.") from exc
        if result.returncode != 0:
            raise ProjectRoutingError("Database metadata service could not be started.")

    def _client_with_ensure(
        self, installation_id: str, project_root: str, deadline: float
    ) -> MetadataClient:
        try:
            return self._service_client(installation_id, deadline)
        except (MetadataServiceError, ProjectRoutingError):
            self._ensure_runner(project_root, self._remaining(deadline))
            return self._service_client(installation_id, deadline)

    def _call(
        self,
        operation: str,
        *,
        connection_id: str | None = None,
        table: str | None = None,
    ) -> Any:
        deadline = self._clock() + self._timeout
        try:
            project_root = self._resolve_root(deadline)
            project_id, connections, active = _read_access(project_root)
            selected = _select_connection(connections, active, connection_id)
            installation_id = self._installation_id()
            client = self._client_with_ensure(
                installation_id, project_root, deadline
            )
            payload: dict[str, Any] = {
                "version": 2,
                "project_id": project_id,
                "project_root": project_root,
                "connection_id": selected,
                "operation": operation,
            }
            if operation == "describe_table":
                payload["table"] = table
            result = client.metadata(payload)
            self._remaining(deadline)
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

    def list_databases(self, connection_id: str | None = None) -> list[dict[str, str]]:
        return self._call("list_databases", connection_id=connection_id)

    def list_tables(self, connection_id: str | None = None) -> list[dict[str, str]]:
        return self._call("list_tables", connection_id=connection_id)

    def describe_table(
        self, table: str, connection_id: str | None = None
    ) -> dict[str, object]:
        return self._call(
            "describe_table", connection_id=connection_id, table=table
        )
