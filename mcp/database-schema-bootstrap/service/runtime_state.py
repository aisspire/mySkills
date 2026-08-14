from __future__ import annotations

import json
import os
import pathlib
import uuid
from datetime import UTC, datetime
from typing import Any


def write_ready_state(
    path: str | pathlib.Path,
    *,
    endpoint: str,
    port: int,
    project_id: str,
    project_root: str,
    instance_token: str,
) -> None:
    """Write a complete service identity atomically after the socket is bound."""

    ready_path = pathlib.Path(path)
    ready_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "version": 1,
        "project_id": project_id,
        "project_root": project_root,
        "endpoint": endpoint,
        "port": port,
        "pid": os.getpid(),
        "instance_token": instance_token,
        "started_at": datetime.now(UTC).isoformat(),
    }
    temporary_path = ready_path.with_name(
        f".{ready_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    )
    try:
        temporary_path.write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )
        os.replace(temporary_path, ready_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def remove_ready_state_if_owned(
    path: str | pathlib.Path,
    *,
    instance_token: str,
) -> None:
    """Remove only the state record owned by the stopping service instance."""

    ready_path = pathlib.Path(path)
    try:
        state = json.loads(ready_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return
    if not isinstance(state, dict) or state.get("instance_token") != instance_token:
        return
    try:
        ready_path.unlink()
    except FileNotFoundError:
        return
