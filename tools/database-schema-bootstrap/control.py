from __future__ import annotations

import argparse
import contextlib
import getpass
import hashlib
import json
import os
import pathlib
import secrets as token_secrets
import subprocess
import sys
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime
from typing import Any, Iterator, Mapping


SCRIPT_ROOT = pathlib.Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_ROOT.parents[1]
SERVICE_CANDIDATES = (
    SCRIPT_ROOT.parent / "service",
    REPO_ROOT / "mcp" / "database-schema-bootstrap",
)
ADAPTER_CANDIDATES = (
    SCRIPT_ROOT.parent / "adapter",
    REPO_ROOT / ".agents" / "skills" / "database-schema-bootstrap",
)
for candidate in (*SERVICE_CANDIDATES, *ADAPTER_CANDIDATES):
    if candidate.exists() and str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from rpc_client import MetadataServiceClient, MetadataServiceError  # noqa: E402
from service.config import (  # noqa: E402
    ACCESS_RELATIVE_PATH,
    AccessConfig,
    PostgresProfile,
    ProjectGrant,
    access_document,
    atomic_write_json,
    connection_to_json,
    ensure_config_layout,
    load_access,
    load_connections,
    load_projects,
    load_secrets,
    project_document,
    validate_connection_id,
)
from service.errors import ConfigError, GatewayError  # noqa: E402
from service.path_identity import canonical_project_root  # noqa: E402
from service.policy import validate_unqualified_identifier  # noqa: E402


EXCLUDE_START = "# >>> database-schema-bootstrap v2 access >>>"
EXCLUDE_ENTRY = "/.agents/database-schema-bootstrap/"
EXCLUDE_END = "# <<< database-schema-bootstrap v2 access <<<"
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
SERVICE_STATE_FIELDS = {
    "version",
    "protocol_version",
    "installation_id",
    "endpoint",
    "port",
    "pid",
    "instance_token",
    "process_identity",
    "started_at",
}


class ControlError(RuntimeError):
    pass


class FileLock:
    """Small cross-platform exclusive file lock used by all mutations/ensure calls."""

    def __init__(self, path: pathlib.Path, timeout: float = 25.0) -> None:
        self.path = path
        self.timeout = timeout
        self._handle: Any = None

    def __enter__(self) -> "FileLock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("a+b")
        self._handle.seek(0, os.SEEK_END)
        if self._handle.tell() == 0:
            self._handle.write(b"0")
            self._handle.flush()
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    self._handle.seek(0)
                    msvcrt.locking(self._handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(self._handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except OSError as exc:
                if time.monotonic() >= deadline:
                    self._handle.close()
                    self._handle = None
                    raise ControlError("Timed out waiting for the runtime control lock.") from exc
                time.sleep(0.05)

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        if self._handle is None:
            return
        try:
            if os.name == "nt":
                import msvcrt

                self._handle.seek(0)
                msvcrt.locking(self._handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._handle.fileno(), fcntl.LOCK_UN)
        finally:
            self._handle.close()
            self._handle = None


def runtime_root_from_args(value: str | None) -> pathlib.Path:
    if value:
        return pathlib.Path(value).absolute()
    codex_home = pathlib.Path(os.environ.get("CODEX_HOME", pathlib.Path.home() / ".codex"))
    return (codex_home / "database-schema-bootstrap").absolute()


def venv_python(runtime_root: pathlib.Path) -> pathlib.Path:
    if os.name == "nt":
        return runtime_root / ".venv" / "Scripts" / "python.exe"
    return runtime_root / ".venv" / "bin" / "python"


def _json_bytes(payload: Mapping[str, Any]) -> bytes:
    return (json.dumps(payload, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_write_bytes(path: pathlib.Path, data: bytes, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        if os.name != "nt":
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_file_transaction(
    changes: Mapping[pathlib.Path, bytes | None],
    *,
    secret_paths: set[pathlib.Path] | None = None,
) -> None:
    """Apply cross-file changes and restore every original if any write fails."""

    secret_paths = secret_paths or set()
    snapshots: dict[pathlib.Path, tuple[bytes | None, int | None]] = {}
    for path in changes:
        if path.exists():
            snapshots[path] = (path.read_bytes(), path.stat().st_mode & 0o777)
        else:
            snapshots[path] = (None, None)
    applied: list[pathlib.Path] = []
    try:
        for path, data in changes.items():
            if data is None:
                path.unlink(missing_ok=True)
            else:
                _atomic_write_bytes(path, data, 0o600 if path in secret_paths else 0o600)
            applied.append(path)
    except Exception:
        for path in reversed(applied):
            original, mode = snapshots[path]
            try:
                if original is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_write_bytes(path, original, mode or 0o600)
            except Exception:
                pass
        raise


def _connections_document(profiles: Mapping[str, PostgresProfile]) -> dict[str, Any]:
    return {
        "version": 2,
        "connections": {
            connection_id: connection_to_json(profile)
            for connection_id, profile in profiles.items()
        },
    }


def _secrets_document(passwords: Mapping[str, str]) -> dict[str, Any]:
    return {
        "version": 2,
        "secrets": {
            connection_id: {"password": password}
            for connection_id, password in passwords.items()
        },
    }


def _projects_document(projects: Mapping[str, ProjectGrant]) -> dict[str, Any]:
    return {
        "version": 2,
        "projects": {
            project_id: project_document(grant)
            for project_id, grant in projects.items()
        },
    }


def discover_git_root(project_path: str | os.PathLike[str]) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", os.fspath(project_path), "rev-parse", "--show-toplevel"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ControlError("Current path is not inside a Git worktree.") from exc
    if result.returncode != 0 or not result.stdout.strip():
        raise ControlError("Current path is not inside a Git worktree.")
    return canonical_project_root(result.stdout.strip())


def git_exclude_path(project_root: str) -> pathlib.Path:
    commands = (
        [
            "git",
            "-C",
            project_root,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "info/exclude",
        ],
        ["git", "-C", project_root, "rev-parse", "--git-path", "info/exclude"],
    )
    for command in commands:
        result = subprocess.run(
            command, check=False, capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            path = pathlib.Path(result.stdout.strip())
            if not path.is_absolute():
                path = pathlib.Path(project_root) / path
            return path.absolute()
    raise ControlError("Git local exclude path is unavailable.")


def add_exclude_marker(content: str) -> str:
    block = f"{EXCLUDE_START}\n{EXCLUDE_ENTRY}\n{EXCLUDE_END}"
    if block in content:
        return content
    if EXCLUDE_START in content or EXCLUDE_END in content:
        raise ControlError("The database-schema-bootstrap exclude marker was edited.")
    prefix = content.rstrip("\r\n")
    return (prefix + ("\n\n" if prefix else "") + block + "\n")


def remove_exclude_marker(content: str) -> str:
    block = f"{EXCLUDE_START}\n{EXCLUDE_ENTRY}\n{EXCLUDE_END}"
    normalized = content.replace("\r\n", "\n")
    if EXCLUDE_START not in normalized and EXCLUDE_END not in normalized:
        return content
    if normalized.count(EXCLUDE_START) != 1 or normalized.count(EXCLUDE_END) != 1:
        raise ControlError("The database-schema-bootstrap exclude marker was edited.")
    if block not in normalized:
        raise ControlError("The database-schema-bootstrap exclude marker was edited.")
    before, after = normalized.split(block, 1)
    cleaned = before.rstrip("\n") + after.lstrip("\n")
    return (cleaned + "\n") if cleaned else ""


def _read_text_or_empty(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def _is_pid_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _validate_service_state(data: object) -> dict[str, Any]:
    if not isinstance(data, dict) or set(data) != SERVICE_STATE_FIELDS:
        raise ControlError("Metadata service state is invalid.")
    if (
        data.get("version") != 2
        or data.get("protocol_version") != 2
        or not isinstance(data.get("installation_id"), str)
        or not isinstance(data.get("endpoint"), str)
        or isinstance(data.get("port"), bool)
        or not isinstance(data.get("port"), int)
        or isinstance(data.get("pid"), bool)
        or not isinstance(data.get("pid"), int)
        or not isinstance(data.get("instance_token"), str)
        or not data.get("instance_token")
        or not isinstance(data.get("process_identity"), str)
        or not data.get("process_identity")
        or not isinstance(data.get("started_at"), str)
    ):
        raise ControlError("Metadata service state is invalid.")
    return data


class Control:
    def __init__(self, runtime_root: str | pathlib.Path) -> None:
        self.runtime_root = pathlib.Path(runtime_root).absolute()
        self.config_root = self.runtime_root / "config"
        self.state_root = self.runtime_root / "state"
        self.lock_path = self.state_root / "service.lock"
        ensure_config_layout(self.config_root)

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        with FileLock(self.lock_path):
            yield

    def _paths(self) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path]:
        return (
            self.config_root / "connections.json",
            self.config_root / "secrets.json",
            self.config_root / "projects.json",
        )

    def connection_add(
        self,
        connection_id: str,
        *,
        host: str,
        port: int,
        database: str,
        connection_database: str,
        schema: str,
        user: str,
        password: str,
    ) -> None:
        connection_id = validate_connection_id(connection_id)
        validate_unqualified_identifier(schema, label="Schema name")
        if not all(
            isinstance(value, str) and value.strip()
            for value in (host, database, connection_database, user)
        ):
            raise ControlError("Connection fields must not be blank.")
        if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
            raise ControlError("Connection port must be between 1 and 65535.")
        if not isinstance(password, str) or not password:
            raise ControlError("Database password must not be empty.")
        profile = PostgresProfile(
            connection_id=connection_id,
            host=host.strip(),
            port=port,
            database=database.strip(),
            connection_database=connection_database.strip(),
            schema=schema,
            user=user.strip(),
        )
        connections_path, secrets_path, _ = self._paths()
        with self.locked():
            connections = load_connections(connections_path)
            passwords = load_secrets(secrets_path)
            if connection_id in connections or connection_id in passwords:
                raise ControlError("Connection ID already exists.")
            connections[connection_id] = profile
            passwords[connection_id] = password
            atomic_file_transaction(
                {
                    connections_path: _json_bytes(_connections_document(connections)),
                    secrets_path: _json_bytes(_secrets_document(passwords)),
                },
                secret_paths={secrets_path},
            )

    def connection_list(self) -> list[dict[str, Any]]:
        connections = load_connections(self.config_root / "connections.json")
        return [
            {
                "connection_id": connection_id,
                **connection_to_json(profile),
                "password": "<redacted>",
            }
            for connection_id, profile in connections.items()
        ]

    def connection_show(self, connection_id: str) -> dict[str, Any]:
        connection_id = validate_connection_id(connection_id)
        profiles = load_connections(self.config_root / "connections.json")
        profile = profiles.get(connection_id)
        if profile is None:
            raise ControlError("Connection ID was not found.")
        return {
            "connection_id": connection_id,
            **connection_to_json(profile),
            "password": "<redacted>",
        }

    def connection_update(self, connection_id: str, **updates: Any) -> None:
        connection_id = validate_connection_id(connection_id)
        allowed = {
            "host",
            "port",
            "database",
            "connection_database",
            "schema",
            "user",
        }
        if not updates or set(updates) - allowed:
            raise ControlError("No valid non-secret connection fields were provided.")
        path = self.config_root / "connections.json"
        with self.locked():
            profiles = load_connections(path)
            profile = profiles.get(connection_id)
            if profile is None:
                raise ControlError("Connection ID was not found.")
            if "schema" in updates:
                validate_unqualified_identifier(updates["schema"], label="Schema name")
            if "port" in updates and (
                isinstance(updates["port"], bool)
                or not isinstance(updates["port"], int)
                or not 1 <= updates["port"] <= 65535
            ):
                raise ControlError("Connection port must be between 1 and 65535.")
            for key, value in updates.items():
                if key != "port" and (not isinstance(value, str) or not value.strip()):
                    raise ControlError("Connection fields must not be blank.")
                if isinstance(value, str):
                    updates[key] = value.strip()
            profiles[connection_id] = replace(profile, **updates)
            atomic_write_json(path, _connections_document(profiles))

    def connection_set_password(self, connection_id: str, password: str) -> None:
        connection_id = validate_connection_id(connection_id)
        if not password:
            raise ControlError("Database password must not be empty.")
        secrets_path = self.config_root / "secrets.json"
        with self.locked():
            profiles = load_connections(self.config_root / "connections.json")
            if connection_id not in profiles:
                raise ControlError("Connection ID was not found.")
            passwords = load_secrets(secrets_path)
            passwords[connection_id] = password
            atomic_write_json(secrets_path, _secrets_document(passwords), secret=True)

    def connection_remove(self, connection_id: str) -> None:
        connection_id = validate_connection_id(connection_id)
        connections_path, secrets_path, projects_path = self._paths()
        with self.locked():
            profiles = load_connections(connections_path)
            passwords = load_secrets(secrets_path)
            projects = load_projects(projects_path)
            if any(connection_id in grant.connections for grant in projects.values()):
                raise ControlError("Connection still has project grants and cannot be removed.")
            if connection_id not in profiles:
                raise ControlError("Connection ID was not found.")
            profiles.pop(connection_id)
            passwords.pop(connection_id, None)
            atomic_file_transaction(
                {
                    connections_path: _json_bytes(_connections_document(profiles)),
                    secrets_path: _json_bytes(_secrets_document(passwords)),
                },
                secret_paths={secrets_path},
            )

    def project_init(self, project_path: str | os.PathLike[str]) -> AccessConfig:
        root = discover_git_root(project_path)
        access_path = pathlib.Path(root) / ACCESS_RELATIVE_PATH
        exclude_path = git_exclude_path(root)
        projects_path = self.config_root / "projects.json"
        with self.locked():
            if access_path.exists():
                raise ControlError("Project access configuration already exists.")
            projects = load_projects(projects_path)
            project_id = str(uuid.uuid4())
            access = AccessConfig(project_id=project_id, connections={}, active=None)
            projects[project_id] = ProjectGrant(
                project_id=project_id,
                root=root,
                connections=(),
                access_path=canonical_project_root(access_path),
            )
            updated_exclude = add_exclude_marker(_read_text_or_empty(exclude_path))
            atomic_file_transaction(
                {
                    projects_path: _json_bytes(_projects_document(projects)),
                    access_path: _json_bytes(access_document(access)),
                    exclude_path: updated_exclude.encode("utf-8"),
                }
            )
            return access

    def _project_context(
        self, project_path: str | os.PathLike[str]
    ) -> tuple[str, pathlib.Path, AccessConfig, dict[str, ProjectGrant], ProjectGrant]:
        root = discover_git_root(project_path)
        access_path = pathlib.Path(root) / ACCESS_RELATIVE_PATH
        access = load_access(access_path)
        projects = load_projects(self.config_root / "projects.json")
        grant = projects.get(access.project_id)
        if grant is None:
            raise ControlError("Project registration is unavailable.")
        if (
            canonical_project_root(grant.root) != root
            or canonical_project_root(grant.access_path)
            != canonical_project_root(access_path)
        ):
            raise ControlError("Project registration is bound to a different Git root.")
        return root, access_path, access, projects, grant

    def project_grant(self, project_path: str, connection_id: str) -> AccessConfig:
        connection_id = validate_connection_id(connection_id)
        projects_path = self.config_root / "projects.json"
        with self.locked():
            if connection_id not in load_connections(self.config_root / "connections.json"):
                raise ControlError("Connection ID was not found.")
            _, access_path, access, projects, grant = self._project_context(project_path)
            if connection_id in grant.connections or connection_id in access.connections:
                raise ControlError("Project already contains this connection ID.")
            updated_access = AccessConfig(
                project_id=access.project_id,
                connections={**access.connections, connection_id: False},
                active=access.active,
            )
            projects[access.project_id] = replace(
                grant, connections=(*grant.connections, connection_id)
            )
            atomic_file_transaction(
                {
                    projects_path: _json_bytes(_projects_document(projects)),
                    access_path: _json_bytes(access_document(updated_access)),
                }
            )
            return updated_access

    def project_enable(self, project_path: str, connection_id: str) -> AccessConfig:
        return self._set_enabled(project_path, connection_id, True)

    def project_disable(self, project_path: str, connection_id: str) -> AccessConfig:
        return self._set_enabled(project_path, connection_id, False)

    def _set_enabled(
        self, project_path: str, connection_id: str, enabled: bool
    ) -> AccessConfig:
        connection_id = validate_connection_id(connection_id)
        with self.locked():
            _, access_path, access, _, grant = self._project_context(project_path)
            if connection_id not in grant.connections or connection_id not in access.connections:
                raise ControlError("Project connection is not granted.")
            updated_connections = dict(access.connections)
            updated_connections[connection_id] = enabled
            active = access.active
            if enabled and active is None:
                active = connection_id
            if not enabled and active == connection_id:
                active = None
            updated = AccessConfig(access.project_id, updated_connections, active)
            atomic_write_json(access_path, access_document(updated))
            return updated

    def project_use(self, project_path: str, connection_id: str) -> AccessConfig:
        connection_id = validate_connection_id(connection_id)
        with self.locked():
            _, access_path, access, _, grant = self._project_context(project_path)
            if (
                connection_id not in grant.connections
                or access.connections.get(connection_id) is not True
            ):
                raise ControlError("Project connection must be granted and enabled first.")
            updated = AccessConfig(access.project_id, dict(access.connections), connection_id)
            atomic_write_json(access_path, access_document(updated))
            return updated

    def project_revoke(self, project_path: str, connection_id: str) -> AccessConfig:
        connection_id = validate_connection_id(connection_id)
        projects_path = self.config_root / "projects.json"
        with self.locked():
            _, access_path, access, projects, grant = self._project_context(project_path)
            if connection_id not in grant.connections:
                raise ControlError("Project connection is not granted.")
            updated_connections = dict(access.connections)
            updated_connections.pop(connection_id, None)
            updated = AccessConfig(
                access.project_id,
                updated_connections,
                None if access.active == connection_id else access.active,
            )
            projects[access.project_id] = replace(
                grant,
                connections=tuple(
                    item for item in grant.connections if item != connection_id
                ),
            )
            atomic_file_transaction(
                {
                    projects_path: _json_bytes(_projects_document(projects)),
                    access_path: _json_bytes(access_document(updated)),
                }
            )
            return updated

    def project_rebind(
        self, project_path: str, *, confirm_old_root: bool = False
    ) -> ProjectGrant:
        new_root = discover_git_root(project_path)
        access_path = pathlib.Path(new_root) / ACCESS_RELATIVE_PATH
        access = load_access(access_path)
        projects_path = self.config_root / "projects.json"
        with self.locked():
            projects = load_projects(projects_path)
            grant = projects.get(access.project_id)
            if grant is None:
                raise ControlError("Project registration is unavailable.")
            old_root = canonical_project_root(grant.root)
            if old_root != new_root and pathlib.Path(old_root).exists() and not confirm_old_root:
                raise ControlError(
                    "Old project root still exists; pass the explicit rebind confirmation."
                )
            updated = replace(
                grant,
                root=new_root,
                access_path=canonical_project_root(access_path),
            )
            projects[access.project_id] = updated
            exclude_path = git_exclude_path(new_root)
            updated_exclude = add_exclude_marker(_read_text_or_empty(exclude_path))
            changes: dict[pathlib.Path, bytes | None] = {
                projects_path: _json_bytes(_projects_document(projects)),
                exclude_path: updated_exclude.encode("utf-8"),
            }
            if old_root != new_root and pathlib.Path(old_root).exists():
                try:
                    old_exclude = git_exclude_path(old_root)
                except ControlError:
                    old_exclude = None
                if (
                    old_exclude is not None
                    and old_exclude != exclude_path
                    and not self._exclude_is_shared(projects, old_exclude)
                ):
                    changes[old_exclude] = remove_exclude_marker(
                        _read_text_or_empty(old_exclude)
                    ).encode("utf-8")
            atomic_file_transaction(changes)
            return updated

    def project_status(self, project_path: str) -> dict[str, Any]:
        root, access_path, access, _, grant = self._project_context(project_path)
        return {
            "version": 2,
            "project_id": access.project_id,
            "root": root,
            "access_path": str(access_path),
            "grants": list(grant.connections),
            "connections": dict(access.connections),
            "active": access.active,
        }

    def project_remove(self, project_path: str) -> str:
        projects_path = self.config_root / "projects.json"
        with self.locked():
            root, access_path, access, projects, _ = self._project_context(project_path)
            projects.pop(access.project_id)
            exclude_path = git_exclude_path(root)
            cleaned_exclude = (
                _read_text_or_empty(exclude_path)
                if self._exclude_is_shared(projects, exclude_path)
                else remove_exclude_marker(_read_text_or_empty(exclude_path))
            )
            atomic_file_transaction(
                {
                    projects_path: _json_bytes(_projects_document(projects)),
                    access_path: None,
                    exclude_path: cleaned_exclude.encode("utf-8"),
                }
            )
            return access.project_id

    @staticmethod
    def _exclude_is_shared(
        projects: Mapping[str, ProjectGrant], exclude_path: pathlib.Path
    ) -> bool:
        for grant in projects.values():
            if not pathlib.Path(grant.root).exists():
                continue
            try:
                if git_exclude_path(grant.root) == exclude_path:
                    return True
            except ControlError:
                continue
        return False

    def read_install_state(self) -> dict[str, Any]:
        path = self.runtime_root / "install-state.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise ControlError("Runtime installation state is unavailable.") from exc
        if not isinstance(data, dict) or set(data) != INSTALL_STATE_FIELDS:
            raise ControlError("Runtime installation state is invalid.")
        if data.get("version") != 2:
            raise ControlError("Runtime installation state is invalid.")
        return data

    def _read_service_state(self) -> dict[str, Any] | None:
        path = self.state_root / "service.json"
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, json.JSONDecodeError) as exc:
            raise ControlError("Metadata service state is invalid.") from exc
        return _validate_service_state(raw)

    def _healthy_client(
        self, state: dict[str, Any], installation_id: str, timeout: float = 2.0
    ) -> MetadataServiceClient:
        if state.get("installation_id") != installation_id:
            raise ControlError("Metadata service installation identity does not match.")
        client = MetadataServiceClient(
            state["endpoint"],
            instance_token=state["instance_token"],
            timeout=timeout,
        )
        try:
            client.health(
                expected_installation_id=installation_id,
                expected_process_identity=state["process_identity"],
                expected_pid=state["pid"],
            )
        except MetadataServiceError as exc:
            raise ControlError("Metadata service health check failed.") from exc
        return client

    def _record_orphan(self, raw_state: object, reason: str) -> None:
        path = self.state_root / "orphans.json"
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            document = {"version": 2, "orphans": []}
        except (OSError, json.JSONDecodeError):
            document = {"version": 2, "orphans": []}
        if not isinstance(document, dict) or set(document) != {"version", "orphans"}:
            document = {"version": 2, "orphans": []}
        records = document.get("orphans")
        if not isinstance(records, list):
            records = []
        state = raw_state if isinstance(raw_state, dict) else {}
        pid = state.get("pid") if isinstance(state.get("pid"), int) else None
        record = {
            "pid": pid,
            "process_identity": state.get("process_identity")
            if isinstance(state.get("process_identity"), str)
            else None,
            "reason": reason,
            "observed_at": datetime.now(UTC).isoformat(),
            "unverifiable": pid is None or _is_pid_alive(pid),
        }
        digest = hashlib.sha256(
            json.dumps(record, sort_keys=True).encode("utf-8")
        ).hexdigest()
        if not any(isinstance(item, dict) and item.get("record_id") == digest for item in records):
            records.append({"record_id": digest, **record})
        atomic_write_json(path, {"version": 2, "orphans": records}, secret=True)

    def service_status(self) -> dict[str, Any]:
        install_state = self.read_install_state()
        try:
            state = self._read_service_state()
        except ControlError:
            return {"status": "invalid", "version": 2}
        if state is None:
            return {"status": "stopped", "version": 2}
        try:
            self._healthy_client(state, install_state["installation_id"])
        except ControlError:
            return {
                "status": "unhealthy",
                "version": 2,
                "pid": state.get("pid"),
            }
        return {
            "status": "running",
            "version": 2,
            "pid": state["pid"],
            "endpoint": state["endpoint"],
            "installation_id": state["installation_id"],
            "process_identity": state["process_identity"],
        }

    def _project_has_enabled(self, project_root: str) -> bool:
        try:
            access = load_access(pathlib.Path(project_root) / ACCESS_RELATIVE_PATH)
        except ConfigError:
            return False
        return any(access.connections.values())

    def service_ensure(
        self, *, project_root: str | None = None, hook: bool = False
    ) -> dict[str, Any]:
        if hook:
            if not project_root:
                return {"status": "skipped", "reason": "no-project"}
            try:
                root = discover_git_root(project_root)
            except ControlError:
                return {"status": "skipped", "reason": "not-git"}
            if not self._project_has_enabled(root):
                return {"status": "skipped", "reason": "no-enabled-connection"}
        with self.locked():
            install_state = self.read_install_state()
            if install_state.get("dependency_installation") != "completed":
                raise ControlError("Runtime dependency installation is incomplete.")
            installation_id = install_state["installation_id"]
            state_path = self.state_root / "service.json"
            raw_state: object = None
            try:
                raw_state = json.loads(state_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                pass
            except (OSError, json.JSONDecodeError):
                self._record_orphan(None, "state-invalid")
                state_path.rename(
                    self.state_root / f"service.invalid.{uuid.uuid4().hex}.json"
                )
            if raw_state is not None:
                try:
                    state = _validate_service_state(raw_state)
                    self._healthy_client(state, installation_id)
                    return self.service_status()
                except ControlError:
                    self._record_orphan(raw_state, "health-or-identity-mismatch")
                    state_path.rename(
                        self.state_root / f"service.orphan.{uuid.uuid4().hex}.json"
                    )
            return self._start_service(installation_id)

    def _start_service(self, installation_id: str) -> dict[str, Any]:
        python_path = venv_python(self.runtime_root)
        service_script = self.runtime_root / "service" / "server.py"
        if not python_path.is_file() or not service_script.is_file():
            raise ControlError("Installed runtime interpreter or service is unavailable.")
        self.state_root.mkdir(parents=True, exist_ok=True)
        logs_root = self.runtime_root / "logs"
        logs_root.mkdir(parents=True, exist_ok=True)
        token = token_secrets.token_urlsafe(32)
        process_identity = str(uuid.uuid4())
        state_path = self.state_root / "service.json"
        command = [
            str(python_path),
            "-B",
            str(service_script),
            "--runtime-root",
            str(self.runtime_root),
            "--port",
            "0",
            "--instance-token",
            token,
            "--process-identity",
            process_identity,
            "--ready-state",
            str(state_path),
        ]
        creationflags = 0
        popen_kwargs: dict[str, Any] = {"close_fds": True}
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | 0x00000008
            popen_kwargs["creationflags"] = creationflags
        else:
            popen_kwargs["start_new_session"] = True
        log_path = logs_root / "service.log"
        with log_path.open("ab") as log_handle:
            process = subprocess.Popen(
                command,
                stdin=subprocess.DEVNULL,
                stdout=log_handle,
                stderr=log_handle,
                **popen_kwargs,
            )
        deadline = time.monotonic() + 10
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            try:
                state = self._read_service_state()
                if state is not None:
                    self._healthy_client(state, installation_id, timeout=1.0)
                    return self.service_status()
            except Exception as exc:
                last_error = exc
            time.sleep(0.1)
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self._record_orphan({"pid": process.pid}, "startup-timeout")
        state_path.unlink(missing_ok=True)
        raise ControlError("Metadata service failed to start.") from last_error

    def service_stop(self) -> dict[str, Any]:
        with self.locked():
            install_state = self.read_install_state()
            state_path = self.state_root / "service.json"
            try:
                raw_state = json.loads(state_path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return {"status": "stopped", "version": 2}
            except (OSError, json.JSONDecodeError) as exc:
                self._record_orphan(None, "stop-state-invalid")
                raise ControlError(
                    "Service state is invalid; no process was terminated."
                ) from exc
            try:
                state = _validate_service_state(raw_state)
                client = self._healthy_client(
                    state, install_state["installation_id"], timeout=3.0
                )
            except ControlError as exc:
                self._record_orphan(raw_state, "stop-identity-unverified")
                raise ControlError(
                    "Service identity could not be verified; no process was terminated."
                ) from exc
            try:
                client.shutdown()
            except MetadataServiceError as exc:
                self._record_orphan(raw_state, "shutdown-rejected")
                raise ControlError("Metadata service rejected graceful shutdown.") from exc
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline and _is_pid_alive(state["pid"]):
                time.sleep(0.1)
            if _is_pid_alive(state["pid"]):
                self._record_orphan(raw_state, "shutdown-timeout")
                raise ControlError(
                    "Metadata service did not exit; no forceful termination was attempted."
                )
            try:
                current = json.loads(state_path.read_text(encoding="utf-8"))
            except (FileNotFoundError, OSError, json.JSONDecodeError):
                current = None
            if (
                isinstance(current, dict)
                and current.get("instance_token") == state["instance_token"]
                and current.get("process_identity") == state["process_identity"]
            ):
                state_path.unlink(missing_ok=True)
            return {"status": "stopped", "version": 2}


def _prompt_required(prompt: str, value: str | None = None) -> str:
    result = value if value is not None else input(prompt).strip()
    if not result:
        raise ControlError("Required input was empty.")
    return result


def _read_confirmed_password() -> str:
    first = getpass.getpass("Database password: ")
    second = getpass.getpass("Confirm database password: ")
    if not first or first != second:
        raise ControlError("Password confirmation did not match.")
    return first


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="database-schema-bootstrap v2 control")
    parser.add_argument("--runtime-root")
    root = parser.add_subparsers(dest="area", required=True)

    connection = root.add_parser("connection").add_subparsers(dest="action", required=True)
    add = connection.add_parser("add")
    add.add_argument("connection_id")
    add.add_argument("--host")
    add.add_argument("--port", type=int, default=5432)
    add.add_argument("--database")
    add.add_argument("--connection-database", default="postgres")
    add.add_argument("--schema", default="public")
    add.add_argument("--user")
    connection.add_parser("list")
    show = connection.add_parser("show")
    show.add_argument("connection_id")
    update = connection.add_parser("update")
    update.add_argument("connection_id")
    update.add_argument("--host")
    update.add_argument("--port", type=int)
    update.add_argument("--database")
    update.add_argument("--connection-database")
    update.add_argument("--schema")
    update.add_argument("--user")
    set_password = connection.add_parser("set-password")
    set_password.add_argument("connection_id")
    remove = connection.add_parser("remove")
    remove.add_argument("connection_id")
    remove.add_argument("--confirm")

    project = root.add_parser("project").add_subparsers(dest="action", required=True)
    for action in ("init", "status", "remove"):
        command = project.add_parser(action)
        command.add_argument("--project", default=".")
        if action == "remove":
            command.add_argument("--confirm")
    for action in ("grant", "revoke", "enable", "disable", "use"):
        command = project.add_parser(action)
        command.add_argument("connection_id")
        command.add_argument("--project", default=".")
    rebind = project.add_parser("rebind")
    rebind.add_argument("--project", default=".")
    rebind.add_argument("--confirm-old-root", action="store_true")

    service = root.add_parser("service").add_subparsers(dest="action", required=True)
    for action in ("ensure", "start", "status", "stop"):
        command = service.add_parser(action)
        if action in {"ensure", "start"}:
            command.add_argument("--hook", action="store_true")
            command.add_argument("--project-root")
    return parser


def _hook_project_root(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    try:
        raw = sys.stdin.read(64 * 1024)
    except OSError:
        return None
    if not raw.strip():
        return os.getcwd()
    try:
        event = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ControlError("SessionStart hook input is invalid JSON.") from exc
    cwd = event.get("cwd") if isinstance(event, dict) else None
    if not isinstance(cwd, str) or not cwd.strip():
        raise ControlError("SessionStart hook input does not contain a valid cwd.")
    return cwd


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    control = Control(runtime_root_from_args(args.runtime_root))
    try:
        if args.area == "connection":
            if args.action == "add":
                control.connection_add(
                    args.connection_id,
                    host=_prompt_required("PostgreSQL host: ", args.host),
                    port=args.port,
                    database=_prompt_required("Target database: ", args.database),
                    connection_database=args.connection_database,
                    schema=args.schema,
                    user=_prompt_required("PostgreSQL user: ", args.user),
                    password=_read_confirmed_password(),
                )
                print("Connection added.")
            elif args.action == "list":
                _print_json(control.connection_list())
            elif args.action == "show":
                _print_json(control.connection_show(args.connection_id))
            elif args.action == "update":
                updates = {
                    key: value
                    for key, value in {
                        "host": args.host,
                        "port": args.port,
                        "database": args.database,
                        "connection_database": args.connection_database,
                        "schema": args.schema,
                        "user": args.user,
                    }.items()
                    if value is not None
                }
                control.connection_update(args.connection_id, **updates)
                print("Connection updated.")
            elif args.action == "set-password":
                control.connection_set_password(
                    args.connection_id, _read_confirmed_password()
                )
                print("Password updated.")
            elif args.action == "remove":
                if args.confirm != args.connection_id:
                    raise ControlError(
                        "Pass --confirm with the exact connection ID to remove it."
                    )
                control.connection_remove(args.connection_id)
                print("Connection removed.")
        elif args.area == "project":
            if args.action == "init":
                _print_json(access_document(control.project_init(args.project)))
            elif args.action == "grant":
                _print_json(
                    access_document(control.project_grant(args.project, args.connection_id))
                )
            elif args.action == "revoke":
                _print_json(
                    access_document(control.project_revoke(args.project, args.connection_id))
                )
            elif args.action == "enable":
                _print_json(
                    access_document(control.project_enable(args.project, args.connection_id))
                )
            elif args.action == "disable":
                _print_json(
                    access_document(control.project_disable(args.project, args.connection_id))
                )
            elif args.action == "use":
                _print_json(
                    access_document(control.project_use(args.project, args.connection_id))
                )
            elif args.action == "rebind":
                _print_json(
                    project_document(
                        control.project_rebind(
                            args.project, confirm_old_root=args.confirm_old_root
                        )
                    )
                )
            elif args.action == "status":
                _print_json(control.project_status(args.project))
            elif args.action == "remove":
                status = control.project_status(args.project)
                if args.confirm != status["project_id"]:
                    raise ControlError(
                        "Pass --confirm with the exact project ID to remove it."
                    )
                print(f"Removed project {control.project_remove(args.project)}.")
        elif args.area == "service":
            if args.action in {"ensure", "start"}:
                project_root = (
                    _hook_project_root(args.project_root) if args.hook else args.project_root
                )
                result = control.service_ensure(project_root=project_root, hook=args.hook)
                # SessionStart treats JSON-looking stdout as a hook response and
                # validates its event-specific schema. The service status object
                # is a control-plane result, not a hook response, so successful
                # hook invocations must stay silent. Interactive control calls
                # keep their existing JSON output.
                if not args.hook:
                    _print_json(result)
            elif args.action == "status":
                _print_json(control.service_status())
            elif args.action == "stop":
                _print_json(control.service_stop())
        return 0
    except (ControlError, GatewayError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
