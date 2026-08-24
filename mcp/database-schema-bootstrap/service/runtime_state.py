from __future__ import annotations

import json
import os
import pathlib
from datetime import UTC, datetime
from typing import Any

from .config import atomic_write_json


def write_ready_state(
    path: str | pathlib.Path,
    *,
    endpoint: str,
    port: int,
    installation_id: str,
    instance_token: str,
    process_identity: str,
) -> None:
    """Write the global daemon identity only after the loopback socket is bound."""

    payload: dict[str, Any] = {
        "version": 2,
        "protocol_version": 2,
        "installation_id": installation_id,
        "endpoint": endpoint,
        "port": port,
        "pid": os.getpid(),
        "instance_token": instance_token,
        "process_identity": process_identity,
        "started_at": datetime.now(UTC).isoformat(),
    }
    atomic_write_json(path, payload, secret=True)


def remove_ready_state_if_owned(
    path: str | pathlib.Path,
    *,
    instance_token: str,
    process_identity: str,
) -> None:
    """A retiring daemon cannot remove a newer daemon's state record."""

    ready_path = pathlib.Path(path)
    try:
        state = json.loads(ready_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if (
        not isinstance(state, dict)
        or state.get("instance_token") != instance_token
        or state.get("process_identity") != process_identity
    ):
        return
    try:
        ready_path.unlink()
    except FileNotFoundError:
        return
