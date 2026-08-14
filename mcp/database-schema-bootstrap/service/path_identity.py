from __future__ import annotations

import os


def canonical_project_root(path: str | os.PathLike[str]) -> str:
    """Return the lexical project spelling shared by service and adapter.

    This intentionally does not call ``realpath`` or ``Path.resolve``. A
    project opened through a junction or symlink must retain that spelling so
    its identity is the same in the control script, service state, and MCP
    adapter.
    """

    try:
        normalized = os.path.normcase(os.path.normpath(os.path.abspath(os.fspath(path))))
    except (OSError, TypeError, ValueError) as exc:
        raise ValueError("Project identity is unavailable.") from exc

    drive, tail = os.path.splitdrive(normalized)
    root = drive + os.path.sep if drive and tail.startswith(("/", "\\")) else os.path.sep
    if normalized != root:
        normalized = normalized.rstrip("\\/")
    if not normalized:
        raise ValueError("Project identity is unavailable.")
    return normalized
