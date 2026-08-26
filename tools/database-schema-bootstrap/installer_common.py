from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shlex
import tempfile
import tomllib
from typing import Any, Iterable, Mapping


V2_START_PATTERN = re.compile(
    r"^# >>> database-schema-bootstrap v2 managed id=([0-9a-fA-F-]{36}) >>>$",
    re.MULTILINE,
)
V2_BLOCK_PATTERN = re.compile(
    r"^# >>> database-schema-bootstrap v2 managed id=(?P<id>[0-9a-fA-F-]{36}) >>>\n"
    r".*?"
    r"^# <<< database-schema-bootstrap v2 managed id=(?P=id) <<<$",
    re.MULTILINE | re.DOTALL,
)
V1_MARKER_PATTERN = re.compile(
    r"^# (?:>>>|<<<) database-schema-bootstrap managed id=[0-9a-fA-F-]{36} (?:>>>|<<<)$",
    re.MULTILINE,
)
CODEX_HOOK_STATE_MARKER = "\n[hooks.state]\n"
CODEX_HOOK_TRUST_HASH_PATTERN = re.compile(r"sha256:[0-9a-f]{64}")
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


class InstallError(RuntimeError):
    pass


def atomic_write_bytes(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = pathlib.Path(name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: pathlib.Path, payload: Mapping[str, Any], mode: int = 0o600) -> None:
    atomic_write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8"),
        mode,
    )


def read_json(path: pathlib.Path, *, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"{label} is unavailable or invalid.") from exc
    if not isinstance(data, dict):
        raise InstallError(f"{label} must be a JSON object.")
    return data


def read_install_state(path: pathlib.Path) -> dict[str, Any]:
    data = read_json(path, label="Installation state")
    if set(data) != INSTALL_STATE_FIELDS or data.get("version") != 2:
        raise InstallError("Installation state is not a strict v2 state file.")
    return data


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_digest(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    if not path.exists():
        raise InstallError(f"Managed tree is missing: {path}")
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        relative = item.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(bytes.fromhex(sha256_file(item)))
    return digest.hexdigest()


def managed_file_manifest(runtime_root: pathlib.Path, parts: Iterable[str]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for part in parts:
        root = runtime_root / part
        for item in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
            if item.suffix == ".pyc" or "__pycache__" in item.parts:
                continue
            records.append(
                {
                    "path": item.relative_to(runtime_root).as_posix(),
                    "sha256": sha256_file(item),
                }
            )
    return records


def venv_python(runtime_root: pathlib.Path, *, windows: bool | None = None) -> pathlib.Path:
    use_windows = os.name == "nt" if windows is None else windows
    if use_windows:
        return runtime_root / ".venv" / "Scripts" / "python.exe"
    return runtime_root / ".venv" / "bin" / "python"


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _hook_command(runtime_root: pathlib.Path, python_path: pathlib.Path) -> str:
    arguments = [
        str(python_path),
        "-B",
        str(runtime_root / "control" / "control.py"),
        "--runtime-root",
        str(runtime_root),
        "service",
        "ensure",
        "--hook",
    ]
    if os.name == "nt":
        import subprocess

        return subprocess.list2cmdline(arguments)
    return shlex.join(arguments)


def managed_config_block(
    installation_id: str,
    runtime_root: pathlib.Path,
    python_path: pathlib.Path,
) -> str:
    adapter = runtime_root / "adapter" / "mcp_server.py"
    lines = [
        f"# >>> database-schema-bootstrap v2 managed id={installation_id} >>>",
        "[mcp_servers.database-schema-bootstrap]",
        f"command = {_toml_string(str(python_path))}",
        "args = ["
        + ", ".join(
            _toml_string(value)
            for value in (
                "-B",
                str(adapter),
                "--runtime-root",
                str(runtime_root),
                "--timeout",
                "25",
            )
        )
        + "]",
        'enabled_tools = ["list_databases", "list_tables", "describe_table"]',
        'default_tools_approval_mode = "writes"',
        "startup_timeout_sec = 30",
        "tool_timeout_sec = 30",
        "enabled = true",
        "",
        "[[hooks.SessionStart]]",
        'matcher = "^(startup|resume|clear|compact)$"',
        "",
        "[[hooks.SessionStart.hooks]]",
        'type = "command"',
        f"command = {_toml_string(_hook_command(runtime_root, python_path))}",
        "timeout = 30",
        'statusMessage = "Preparing local database metadata gateway"',
        f"# <<< database-schema-bootstrap v2 managed id={installation_id} <<<",
    ]
    return "\n".join(lines)


def inspect_managed_config(content: str) -> tuple[str | None, str | None]:
    normalized = content.replace("\r\n", "\n")
    matches = list(V2_BLOCK_PATTERN.finditer(normalized))
    starts = list(V2_START_PATTERN.finditer(normalized))
    end_count = normalized.count("# <<< database-schema-bootstrap v2 managed id=")
    if not matches:
        if starts or end_count:
            raise InstallError("The v2 managed Codex block has incomplete boundaries.")
        return None, None
    if len(matches) != 1 or len(starts) != 1 or end_count != 1:
        raise InstallError("The v2 managed Codex block is duplicated or malformed.")
    block = matches[0].group(0)
    return matches[0].group("id").lower(), block


def _split_codex_hook_state(block: str) -> tuple[str, str | None]:
    state_start = block.find(CODEX_HOOK_STATE_MARKER)
    if state_start < 0:
        return block, None
    if block.find(CODEX_HOOK_STATE_MARKER, state_start + 1) >= 0:
        raise InstallError("Codex hook trust state is duplicated in the managed block.")

    end_start = block.rfind("\n# <<< database-schema-bootstrap v2 managed id=")
    if end_start <= state_start:
        raise InstallError("Codex hook trust state is not at the managed block boundary.")
    state = block[state_start + 1 : end_start].rstrip("\n")
    try:
        parsed = tomllib.loads(state)
    except tomllib.TOMLDecodeError as exc:
        raise InstallError("Codex hook trust state is invalid.") from exc
    if set(parsed) != {"hooks"} or set(parsed["hooks"]) != {"state"}:
        raise InstallError("Codex hook trust state contains unsupported tables.")
    records = parsed["hooks"]["state"]
    if not isinstance(records, dict):
        raise InstallError("Codex hook trust state is invalid.")
    for record in records.values():
        if (
            not isinstance(record, dict)
            or not record
            or not set(record) <= {"trusted_hash", "enabled"}
            or not isinstance(record.get("trusted_hash"), str)
            or CODEX_HOOK_TRUST_HASH_PATTERN.fullmatch(record["trusted_hash"]) is None
            or ("enabled" in record and not isinstance(record["enabled"], bool))
        ):
            raise InstallError("Codex hook trust state contains unsupported fields.")

    normalized = block[:state_start].rstrip("\n") + "\n" + block[end_start + 1 :]
    return normalized, state


def normalized_managed_config_block(block: str) -> str:
    normalized, _ = _split_codex_hook_state(block)
    return normalized


def replace_managed_config(content: str, block: str) -> str:
    normalized = content.replace("\r\n", "\n")
    _, existing = inspect_managed_config(normalized)
    if existing is None:
        prefix = normalized.rstrip("\n")
        return prefix + ("\n\n" if prefix else "") + block + "\n"
    _, hook_state = _split_codex_hook_state(existing)
    replacement = block + ("\n\n" + hook_state if hook_state else "")
    return normalized.replace(existing, replacement, 1).rstrip("\n") + "\n"


def remove_managed_config(content: str) -> str:
    normalized = content.replace("\r\n", "\n")
    _, existing = inspect_managed_config(normalized)
    if existing is None:
        return content
    _, hook_state = _split_codex_hook_state(existing)
    if hook_state is not None:
        return normalized.replace(existing, hook_state, 1).rstrip("\n") + "\n"
    before, after = normalized.split(existing, 1)
    left = before.rstrip("\n")
    right = after.lstrip("\n")
    cleaned = left + ("\n\n" if left and right else "") + right
    return (cleaned + "\n") if cleaned else ""


def contains_v1_marker(content: str) -> bool:
    return bool(V1_MARKER_PATTERN.search(content.replace("\r\n", "\n")))


def is_strict_v2_data_layout(runtime_root: pathlib.Path) -> bool:
    config_root = runtime_root / "config"
    if not config_root.is_dir():
        return False
    allowed = {"config"}
    present = {item.name for item in runtime_root.iterdir()}
    if present - allowed:
        return False
    expected = {
        "connections.json": "connections",
        "secrets.json": "secrets",
        "projects.json": "projects",
    }
    try:
        for name, container in expected.items():
            data = read_json(config_root / name, label=name)
            if set(data) != {"version", container} or data.get("version") != 2:
                return False
            if not isinstance(data.get(container), dict):
                return False
    except InstallError:
        return False
    return True
