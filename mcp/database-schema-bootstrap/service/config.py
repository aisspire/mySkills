from __future__ import annotations

import json
import pathlib
from dataclasses import dataclass
from typing import Any

from .errors import ConfigError
from .policy import validate_unqualified_identifier


PLAINTEXT_SECRET_KEYS = {
    "password",
    "db_password",
    "db_pass",
    "pass",
    "secret",
    "dsn",
    "db_dsn",
}
UNSUPPORTED_PROFILE_KEYS = {"sqlite_path"}


@dataclass(frozen=True)
class PostgresProfile:
    host: str
    port: int
    database: str
    connection_database: str
    schema: str
    user: str
    credential_target: str
    target_tables: tuple[str, ...]


def _required_string(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Profile field `{key}` is required.")
    return value.strip()


def _optional_string(data: dict[str, Any], key: str, default: str) -> str:
    value = data.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"Profile field `{key}` must be a non-empty string.")
    return value.strip()


def _parse_port(data: dict[str, Any]) -> int:
    value = data.get("port", 5432)
    if isinstance(value, bool):
        raise ConfigError("Profile field `port` must be an integer.")
    try:
        port = int(value)
    except (TypeError, ValueError) as exc:
        raise ConfigError("Profile field `port` must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError("Profile field `port` must be between 1 and 65535.")
    return port


def _parse_target_tables(data: dict[str, Any]) -> tuple[str, ...]:
    value = data.get("target_tables", [])
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError("Profile field `target_tables` must be a JSON array.")
    tables: list[str] = []
    for table in value:
        if not isinstance(table, str):
            raise ConfigError("Every `target_tables` item must be a string.")
        tables.append(validate_unqualified_identifier(table.strip(), label="Target table"))
    return tuple(tables)


def _reject_unsafe_or_unsupported_keys(data: dict[str, Any]) -> None:
    for raw_key in data:
        key = str(raw_key).strip().lower()
        if key in PLAINTEXT_SECRET_KEYS:
            raise ConfigError(
                "Plaintext database secrets and DSN values are not allowed. "
                "Use `credential_target` with Windows Credential Manager."
            )
        if key in UNSUPPORTED_PROFILE_KEYS:
            raise ConfigError(
                "Only PostgreSQL profiles are supported; SQLite fields are not allowed."
            )


def load_profile(path: str | pathlib.Path) -> PostgresProfile:
    profile_path = pathlib.Path(path)
    if not profile_path.exists():
        raise ConfigError(f"Profile file not found: {profile_path}")

    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError("Profile is not valid JSON.") from exc
    if not isinstance(data, dict):
        raise ConfigError("Profile must be a JSON object.")

    _reject_unsafe_or_unsupported_keys(data)

    if data.get("db_type") != "postgres":
        raise ConfigError("Only `db_type: postgres` profiles are supported.")

    connection_database = data.get("connection_database")
    legacy_connection_database = data.get("maintenance_database")
    if connection_database is None:
        connection_database = legacy_connection_database
    elif (
        legacy_connection_database is not None
        and legacy_connection_database != connection_database
    ):
        raise ConfigError(
            "`connection_database` and `maintenance_database` must match when both exist."
        )
    if not isinstance(connection_database, str) or not connection_database.strip():
        raise ConfigError("Profile field `connection_database` is required.")

    schema = _optional_string(data, "schema", "public")
    validate_unqualified_identifier(schema, label="Schema name")

    return PostgresProfile(
        host=_required_string(data, "host"),
        port=_parse_port(data),
        database=_required_string(data, "database"),
        connection_database=connection_database.strip(),
        schema=schema,
        user=_required_string(data, "user"),
        credential_target=_required_string(data, "credential_target"),
        target_tables=_parse_target_tables(data),
    )

