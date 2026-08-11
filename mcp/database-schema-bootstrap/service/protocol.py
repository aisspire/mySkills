from __future__ import annotations

from typing import Any, Protocol

from .errors import PolicyError


class MetadataOperations(Protocol):
    def list_databases(self) -> list[dict[str, str]]: ...

    def list_tables(self) -> list[dict[str, str]]: ...

    def describe_table(self, table: str) -> dict[str, object]: ...


def dispatch_metadata(
    service: MetadataOperations,
    payload: object,
) -> Any:
    """Dispatch exactly the three allowed metadata operations."""

    if not isinstance(payload, dict):
        raise PolicyError("Metadata request must be a JSON object.")

    operation = payload.get("operation")
    if operation == "list_databases":
        if set(payload) != {"operation"}:
            raise PolicyError("The list_databases request has unexpected fields.")
        return service.list_databases()

    if operation == "list_tables":
        if set(payload) != {"operation"}:
            raise PolicyError("The list_tables request has unexpected fields.")
        return service.list_tables()

    if operation == "describe_table":
        if set(payload) != {"operation", "table"}:
            raise PolicyError("The describe_table request has unexpected fields.")
        table = payload.get("table")
        if not isinstance(table, str) or not table:
            raise PolicyError("The table field is required.")
        return service.describe_table(table)

    raise PolicyError("Unsupported metadata operation.")

