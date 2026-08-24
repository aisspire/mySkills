from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import validate_connection_id, validate_project_id
from .errors import ConfigError, PolicyError
from .policy import validate_table_name


@dataclass(frozen=True)
class MetadataRequest:
    project_id: str
    project_root: str
    connection_id: str
    operation: str
    table: str | None = None


def parse_metadata_request(payload: object) -> MetadataRequest:
    """Accept only the exact v2 fields for the three metadata operations."""

    if not isinstance(payload, dict):
        raise PolicyError("Metadata request must be a JSON object.")
    operation = payload.get("operation")
    base_fields = {
        "version",
        "project_id",
        "project_root",
        "connection_id",
        "operation",
    }
    expected_fields = (
        base_fields | {"table"} if operation == "describe_table" else base_fields
    )
    if set(payload) != expected_fields:
        raise PolicyError("Metadata request has invalid or unexpected fields.")
    if payload.get("version") != 2:
        raise PolicyError("Metadata protocol version is unsupported.")
    if operation not in {"list_databases", "list_tables", "describe_table"}:
        raise PolicyError("Unsupported metadata operation.")
    raw_project_id = payload.get("project_id")
    project_root = payload.get("project_root")
    try:
        project_id = validate_project_id(raw_project_id)
    except ConfigError as exc:
        raise PolicyError("Project identity is invalid.") from exc
    if not isinstance(project_root, str) or not project_root:
        raise PolicyError("Project root is required.")
    try:
        connection_id = validate_connection_id(payload.get("connection_id"))
    except ConfigError as exc:
        raise PolicyError("Connection identity is invalid.") from exc
    table: str | None = None
    if operation == "describe_table":
        raw_table = payload.get("table")
        if not isinstance(raw_table, str):
            raise PolicyError("The table field is required.")
        table = validate_table_name(raw_table)
    return MetadataRequest(
        project_id=project_id,
        project_root=project_root,
        connection_id=connection_id,
        operation=operation,
        table=table,
    )
