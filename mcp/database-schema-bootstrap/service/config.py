from __future__ import annotations

import json
import os
import pathlib
import re
import stat
import tempfile
import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from .errors import ConfigError
from .policy import validate_unqualified_identifier


CONFIG_VERSION = 2
CONNECTION_ID_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9._-]{0,63}\Z")
ACCESS_RELATIVE_PATH = pathlib.Path(".agents") / "database-schema-bootstrap" / "access.json"


@dataclass(frozen=True)
class PostgresProfile:
    connection_id: str
    host: str
    port: int
    database: str
    connection_database: str
    schema: str
    user: str


@dataclass(frozen=True)
class ProjectGrant:
    project_id: str
    root: str
    connections: tuple[str, ...]
    access_path: str


@dataclass(frozen=True)
class AccessConfig:
    project_id: str
    connections: Mapping[str, bool]
    active: str | None


def validate_connection_id(value: object) -> str:
    if not isinstance(value, str) or not CONNECTION_ID_PATTERN.fullmatch(value):
        raise ConfigError(
            "Connection ID must match [A-Za-z][A-Za-z0-9._-]{0,63}."
        )
    return value


def validate_project_id(value: object) -> str:
    if not isinstance(value, str):
        raise ConfigError("Project ID must be a canonical UUID.")
    try:
        canonical = str(uuid.UUID(value))
    except ValueError as exc:
        raise ConfigError("Project ID must be a canonical UUID.") from exc
    if value != canonical:
        raise ConfigError("Project ID must be a canonical UUID.")
    return value


def _require_exact_keys(data: Mapping[str, Any], allowed: set[str], *, label: str) -> None:
    unknown = set(data) - allowed
    missing = allowed - set(data)
    if unknown or missing:
        raise ConfigError(f"{label} has invalid or unknown fields.")


def _required_string(data: Mapping[str, Any], key: str, *, label: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} field `{key}` is required.")
    return value.strip()


def _parse_port(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError("Connection field `port` must be an integer.")
    if not 1 <= value <= 65535:
        raise ConfigError("Connection field `port` must be between 1 and 65535.")
    return value


def _read_json_object(path: pathlib.Path, *, label: str) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise ConfigError(f"{label} is unavailable.") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{label} is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{label} must be a JSON object.")
    return data


def _validate_versioned_container(
    data: Mapping[str, Any], container_key: str, *, label: str
) -> Mapping[str, Any]:
    _require_exact_keys(data, {"version", container_key}, label=label)
    if data.get("version") != CONFIG_VERSION:
        raise ConfigError(f"{label} version is unsupported.")
    container = data.get(container_key)
    if not isinstance(container, dict):
        raise ConfigError(f"{label} field `{container_key}` must be an object.")
    return container


def load_connections(path: str | pathlib.Path) -> dict[str, PostgresProfile]:
    data = _read_json_object(pathlib.Path(path), label="Connections configuration")
    records = _validate_versioned_container(
        data, "connections", label="Connections configuration"
    )
    result: dict[str, PostgresProfile] = {}
    fields = {
        "db_type",
        "host",
        "port",
        "database",
        "connection_database",
        "schema",
        "user",
    }
    for raw_id, raw_record in records.items():
        connection_id = validate_connection_id(raw_id)
        if not isinstance(raw_record, dict):
            raise ConfigError("Connection record must be an object.")
        _require_exact_keys(raw_record, fields, label="Connection record")
        if raw_record.get("db_type") != "postgres":
            raise ConfigError("Only `db_type: postgres` connections are supported.")
        schema = _required_string(raw_record, "schema", label="Connection")
        validate_unqualified_identifier(schema, label="Schema name")
        result[connection_id] = PostgresProfile(
            connection_id=connection_id,
            host=_required_string(raw_record, "host", label="Connection"),
            port=_parse_port(raw_record.get("port")),
            database=_required_string(raw_record, "database", label="Connection"),
            connection_database=_required_string(
                raw_record, "connection_database", label="Connection"
            ),
            schema=schema,
            user=_required_string(raw_record, "user", label="Connection"),
        )
    return result


def load_secrets(path: str | pathlib.Path) -> dict[str, str]:
    data = _read_json_object(pathlib.Path(path), label="Secrets configuration")
    records = _validate_versioned_container(data, "secrets", label="Secrets configuration")
    result: dict[str, str] = {}
    for raw_id, raw_record in records.items():
        connection_id = validate_connection_id(raw_id)
        if not isinstance(raw_record, dict):
            raise ConfigError("Secret record must be an object.")
        _require_exact_keys(raw_record, {"password"}, label="Secret record")
        password = raw_record.get("password")
        if not isinstance(password, str) or not password:
            raise ConfigError("Secret password must be a non-empty string.")
        result[connection_id] = password
    return result


def load_projects(path: str | pathlib.Path) -> dict[str, ProjectGrant]:
    data = _read_json_object(pathlib.Path(path), label="Projects configuration")
    records = _validate_versioned_container(data, "projects", label="Projects configuration")
    result: dict[str, ProjectGrant] = {}
    for raw_id, raw_record in records.items():
        project_id = validate_project_id(raw_id)
        if not isinstance(raw_record, dict):
            raise ConfigError("Project record must be an object.")
        _require_exact_keys(
            raw_record,
            {"project_id", "root", "connections", "access_path"},
            label="Project record",
        )
        if raw_record.get("project_id") != project_id:
            raise ConfigError("Project record identity does not match its key.")
        root = _required_string(raw_record, "root", label="Project")
        access_path = _required_string(raw_record, "access_path", label="Project")
        raw_connections = raw_record.get("connections")
        if not isinstance(raw_connections, list) or any(
            not isinstance(item, str) for item in raw_connections
        ):
            raise ConfigError("Project connections must be an array of connection IDs.")
        connections = tuple(validate_connection_id(item) for item in raw_connections)
        if len(set(connections)) != len(connections):
            raise ConfigError("Project connections must not contain duplicates.")
        result[project_id] = ProjectGrant(
            project_id=project_id,
            root=root,
            connections=connections,
            access_path=access_path,
        )
    return result


def load_access(path: str | pathlib.Path) -> AccessConfig:
    data = _read_json_object(pathlib.Path(path), label="Project access configuration")
    _require_exact_keys(
        data,
        {"version", "project_id", "connections", "active"},
        label="Project access configuration",
    )
    if data.get("version") != CONFIG_VERSION:
        raise ConfigError("Project access configuration version is unsupported.")
    project_id = validate_project_id(data.get("project_id"))
    raw_connections = data.get("connections")
    if not isinstance(raw_connections, dict):
        raise ConfigError("Project access connections must be an object.")
    connections: dict[str, bool] = {}
    for raw_id, raw_record in raw_connections.items():
        connection_id = validate_connection_id(raw_id)
        if not isinstance(raw_record, dict):
            raise ConfigError("Project access connection record must be an object.")
        _require_exact_keys(raw_record, {"enabled"}, label="Project access connection")
        enabled = raw_record.get("enabled")
        if not isinstance(enabled, bool):
            raise ConfigError("Project access `enabled` must be boolean.")
        connections[connection_id] = enabled
    active = data.get("active")
    if active is not None:
        active = validate_connection_id(active)
        if active not in connections or not connections[active]:
            raise ConfigError("Project access active connection must be enabled.")
    return AccessConfig(project_id=project_id, connections=connections, active=active)


def connection_to_json(profile: PostgresProfile) -> dict[str, Any]:
    return {
        "db_type": "postgres",
        "host": profile.host,
        "port": profile.port,
        "database": profile.database,
        "connection_database": profile.connection_database,
        "schema": profile.schema,
        "user": profile.user,
    }


def empty_connections_document() -> dict[str, Any]:
    return {"version": CONFIG_VERSION, "connections": {}}


def empty_secrets_document() -> dict[str, Any]:
    return {"version": CONFIG_VERSION, "secrets": {}}


def empty_projects_document() -> dict[str, Any]:
    return {"version": CONFIG_VERSION, "projects": {}}


def access_document(access: AccessConfig) -> dict[str, Any]:
    return {
        "version": CONFIG_VERSION,
        "project_id": access.project_id,
        "connections": {
            connection_id: {"enabled": enabled}
            for connection_id, enabled in access.connections.items()
        },
        "active": access.active,
    }


def project_document(grant: ProjectGrant) -> dict[str, Any]:
    return {
        "project_id": grant.project_id,
        "root": grant.root,
        "connections": list(grant.connections),
        "access_path": grant.access_path,
    }


def atomic_write_json(
    path: str | pathlib.Path,
    payload: Mapping[str, Any],
    *,
    secret: bool = False,
) -> None:
    destination = pathlib.Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary = pathlib.Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, 0o600 if secret else 0o600)
        os.replace(temporary, destination)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def ensure_config_layout(config_root: str | pathlib.Path) -> None:
    root = pathlib.Path(config_root)
    root.mkdir(parents=True, exist_ok=True)
    if os.name != "nt":
        os.chmod(root, 0o700)
    defaults = {
        root / "connections.json": empty_connections_document(),
        root / "secrets.json": empty_secrets_document(),
        root / "projects.json": empty_projects_document(),
    }
    for path, payload in defaults.items():
        if not path.exists():
            atomic_write_json(path, payload, secret=path.name == "secrets.json")


def assert_secure_config_permissions(config_root: str | pathlib.Path) -> None:
    if os.name == "nt":
        return
    root = pathlib.Path(config_root)
    secrets_path = root / "secrets.json"
    try:
        root_mode = stat.S_IMODE(root.stat().st_mode)
        secret_mode = stat.S_IMODE(secrets_path.stat().st_mode)
    except OSError as exc:
        raise ConfigError("Runtime configuration permissions cannot be verified.") from exc
    if root_mode & 0o077:
        raise ConfigError("Runtime config directory must not allow group or other access.")
    if secret_mode & 0o077:
        raise ConfigError("Secrets file must not allow group or other access.")
