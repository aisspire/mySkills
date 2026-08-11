from __future__ import annotations

import re

from .errors import PolicyError


_IDENTIFIER_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,62}\Z")


def validate_unqualified_identifier(value: str, *, label: str) -> str:
    """Accept only a simple PostgreSQL identifier, never a SQL fragment."""

    if not isinstance(value, str) or not _IDENTIFIER_PATTERN.fullmatch(value):
        raise PolicyError(f"{label} must be an unqualified PostgreSQL identifier.")
    return value


def validate_table_name(table: str) -> str:
    return validate_unqualified_identifier(table, label="Table name")

