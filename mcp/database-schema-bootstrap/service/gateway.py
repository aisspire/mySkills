from __future__ import annotations

import pathlib
from typing import Any, Callable

from .config import (
    ACCESS_RELATIVE_PATH,
    assert_secure_config_permissions,
    load_access,
    load_connections,
    load_projects,
    load_secrets,
)
from .errors import ConfigError, ConnectionUnavailableError
from .path_identity import canonical_project_root
from .postgres_metadata import ConnectFactory, PostgresMetadataService
from .protocol import MetadataRequest, parse_metadata_request


UNAVAILABLE_MESSAGE = "Current project connection is unavailable."


class MetadataGateway:
    """Authorize a project/connection pair and execute one fixed catalog operation."""

    def __init__(
        self,
        config_root: str | pathlib.Path,
        *,
        connect_factory: ConnectFactory | None = None,
        service_factory: Callable[..., PostgresMetadataService] = PostgresMetadataService,
    ) -> None:
        self.config_root = pathlib.Path(config_root)
        self._connect_factory = connect_factory
        self._service_factory = service_factory

    def _unavailable(self) -> ConnectionUnavailableError:
        return ConnectionUnavailableError(UNAVAILABLE_MESSAGE)

    def _authorize(self, request: MetadataRequest) -> tuple[Any, str]:
        assert_secure_config_permissions(self.config_root)
        projects = load_projects(self.config_root / "projects.json")
        connections = load_connections(self.config_root / "connections.json")
        secrets = load_secrets(self.config_root / "secrets.json")

        grant = projects.get(request.project_id)
        if grant is None:
            raise self._unavailable()
        try:
            request_root = canonical_project_root(request.project_root)
            bound_root = canonical_project_root(grant.root)
            expected_access = canonical_project_root(
                pathlib.Path(bound_root) / ACCESS_RELATIVE_PATH
            )
            registered_access = canonical_project_root(grant.access_path)
        except ValueError as exc:
            raise self._unavailable() from exc
        if request_root != bound_root or registered_access != expected_access:
            raise self._unavailable()
        if request.connection_id not in grant.connections:
            raise self._unavailable()
        try:
            access = load_access(grant.access_path)
        except ConfigError as exc:
            raise self._unavailable() from exc
        if access.project_id != request.project_id:
            raise self._unavailable()
        if access.connections.get(request.connection_id) is not True:
            raise self._unavailable()
        profile = connections.get(request.connection_id)
        password = secrets.get(request.connection_id)
        if profile is None or password is None:
            raise self._unavailable()
        return profile, password

    def execute(self, payload: object) -> Any:
        request = parse_metadata_request(payload)
        profile, password = self._authorize(request)
        service = self._service_factory(
            profile,
            password,
            connect_factory=self._connect_factory,
        )
        if request.operation == "list_databases":
            result = service.list_databases()
            return [
                {"connection_id": request.connection_id, **record} for record in result
            ]
        if request.operation == "list_tables":
            result = service.list_tables()
            return [
                {"connection_id": request.connection_id, **record} for record in result
            ]
        if request.operation == "describe_table" and request.table is not None:
            result = service.describe_table(request.table)
            return {"connection_id": request.connection_id, **result}
        raise self._unavailable()
