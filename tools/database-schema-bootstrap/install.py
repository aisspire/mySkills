from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import uuid
from datetime import UTC, datetime
from typing import Any

from installer_common import (
    InstallError,
    atomic_write_bytes,
    atomic_write_json,
    contains_v1_marker,
    inspect_managed_config,
    is_strict_v2_data_layout,
    managed_config_block,
    managed_file_manifest,
    read_install_state,
    replace_managed_config,
    sha256_bytes,
    sha256_file,
    tree_digest,
    venv_python,
)


RUNTIME_NAME = "database-schema-bootstrap"


def _legacy_message(repo_root: pathlib.Path) -> str:
    legacy = repo_root / "tools" / RUNTIME_NAME / "legacy-uninstall-v1.ps1"
    return (
        "A database-schema-bootstrap v1 or ambiguous legacy runtime is present. "
        "v2 will not read or migrate its profiles or credentials. Run the legacy "
        f"full uninstall explicitly, review its destructive cleanup, then reinstall: "
        f"powershell -NoProfile -ExecutionPolicy Bypass -File \"{legacy}\" -All -ConfirmAll. "
        "The cleanup must remove the v1 managed Codex block, runtime, project profiles, "
        "service state, and recorded Credential Manager entries."
    )


def _copy_tree(source: pathlib.Path, destination: pathlib.Path) -> None:
    if not source.is_dir():
        raise InstallError(f"Required source directory is missing: {source}")
    shutil.copytree(
        source,
        destination,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )


def _copy_files(
    source_root: pathlib.Path, destination_root: pathlib.Path, names: list[str]
) -> None:
    destination_root.mkdir(parents=True, exist_ok=True)
    for name in names:
        source = source_root / name
        if not source.is_file():
            raise InstallError(f"Required source file is missing: {source}")
        shutil.copy2(source, destination_root / name)


def _run(command: list[str], *, label: str) -> None:
    try:
        result = subprocess.run(
            command,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except OSError as exc:
        raise InstallError(f"{label} could not be started.") from exc
    if result.returncode != 0:
        raise InstallError(f"{label} failed.")


def _select_python(explicit: str | None) -> pathlib.Path:
    raw = explicit or os.environ.get("CODEX_PYTHON") or sys.executable
    if not raw:
        raise InstallError(
            "Python 3.11+ was not provided. Use --python or CODEX_PYTHON."
        )
    expanded = pathlib.Path(raw).expanduser()
    resolved_command = shutil.which(raw) if not expanded.is_absolute() else None
    executable = pathlib.Path(resolved_command).absolute() if resolved_command else expanded.absolute()
    try:
        result = subprocess.run(
            [
                str(executable),
                "-c",
                "import json,sys; print(json.dumps(list(sys.version_info[:3])))",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise InstallError("Configured Python interpreter could not be executed.") from exc
    try:
        version = tuple(json.loads(result.stdout))
    except (json.JSONDecodeError, TypeError):
        version = ()
    if result.returncode != 0 or version < (3, 11):
        raise InstallError("database-schema-bootstrap requires Python 3.11 or newer.")
    return executable


def _pid_alive(pid: object) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
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


class Installer:
    def __init__(
        self,
        *,
        repo_root: pathlib.Path,
        codex_home: pathlib.Path,
        python: pathlib.Path,
        skip_dependency_install: bool,
    ) -> None:
        self.repo_root = repo_root.absolute()
        self.codex_home = codex_home.absolute()
        self.runtime_root = self.codex_home / RUNTIME_NAME
        self.config_path = self.codex_home / "config.toml"
        self.python = python
        self.skip_dependency_install = skip_dependency_install

    def _config_content(self) -> str:
        try:
            return self.config_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return ""
        except OSError as exc:
            raise InstallError("Codex config.toml could not be read.") from exc

    def _detect_existing(self) -> dict[str, Any] | None:
        content = self._config_content()
        if contains_v1_marker(content):
            raise InstallError(_legacy_message(self.repo_root))
        state_path = self.runtime_root / "install-state.json"
        if state_path.exists():
            try:
                raw = json.loads(state_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise InstallError(_legacy_message(self.repo_root)) from exc
            if isinstance(raw, dict) and raw.get("version") == 1:
                raise InstallError(_legacy_message(self.repo_root))
            state = read_install_state(state_path)
            self._validate_existing_v2(state, content)
            return state
        if self.runtime_root.exists():
            if is_strict_v2_data_layout(self.runtime_root):
                return None
            if any(self.runtime_root.iterdir()):
                raise InstallError(_legacy_message(self.repo_root))
        installation_id, block = inspect_managed_config(content)
        if installation_id is not None or block is not None:
            raise InstallError(
                "A v2 managed Codex block exists without installation state; refusing ownership."
            )
        return None

    def _validate_existing_v2(self, state: dict[str, Any], content: str) -> None:
        if pathlib.Path(state["runtime_root"]).absolute() != self.runtime_root:
            raise InstallError("Installation state points to a different runtime root.")
        if pathlib.Path(state["config_path"]).absolute() != self.config_path:
            raise InstallError("Installation state points to a different Codex config.")
        installation_id, block = inspect_managed_config(content)
        if installation_id != str(state["installation_id"]).lower() or block is None:
            raise InstallError("Installation state and managed Codex block do not match.")
        if sha256_bytes(block.encode("utf-8")) != state["config_block_hash"]:
            raise InstallError("The managed Codex block was edited; refusing upgrade.")
        for record in state["managed_files"]:
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise InstallError("Installation file manifest is invalid.")
            path = self.runtime_root / record["path"]
            try:
                path.relative_to(self.runtime_root)
            except ValueError as exc:
                raise InstallError("Installation file manifest escapes the runtime.") from exc
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                raise InstallError(f"A managed runtime file was edited: {record['path']}")
        for record in state["managed_trees"]:
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise InstallError("Installation tree manifest is invalid.")
            path = self.runtime_root / record["path"]
            try:
                path.relative_to(self.runtime_root)
            except ValueError as exc:
                raise InstallError("Installation tree manifest escapes the runtime.") from exc
            if tree_digest(path) != record["sha256"]:
                raise InstallError(f"A managed runtime tree was edited: {record['path']}")

    def _blocking_orphans(self) -> None:
        path = self.runtime_root / "state" / "orphans.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise InstallError("Orphan process records are invalid; upgrade is blocked.") from exc
        records = data.get("orphans") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise InstallError("Orphan process records are invalid; upgrade is blocked.")
        for record in records:
            if not isinstance(record, dict):
                raise InstallError("Orphan process records are invalid; upgrade is blocked.")
            pid = record.get("pid")
            if pid is None or _pid_alive(pid):
                raise InstallError(
                    "An unverifiable metadata service process blocks destructive upgrade."
                )

    def _stage_sources(self, staging: pathlib.Path) -> None:
        skill_root = self.repo_root / ".agents" / "skills" / RUNTIME_NAME
        service_root = self.repo_root / "mcp" / RUNTIME_NAME
        control_root = self.repo_root / "tools" / RUNTIME_NAME
        _copy_files(
            skill_root,
            staging / "adapter",
            ["mcp_server.py", "project_routing.py", "rpc_client.py", "requirements-mcp.txt"],
        )
        _copy_files(service_root, staging / "service", ["server.py", "requirements.txt"])
        _copy_tree(service_root / "service", staging / "service" / "service")
        control_files = [
            "control.py",
            "installer_common.py",
            "uninstall.py",
            "db-schema-bootstrap.ps1",
            "db-schema-bootstrap.sh",
            "uninstall.ps1",
            "uninstall.sh",
        ]
        _copy_files(control_root, staging / "control", control_files)

    def _stage_data(self, staging: pathlib.Path) -> None:
        source_config = self.runtime_root / "config"
        destination = staging / "config"
        if source_config.exists():
            for item in source_config.rglob("*"):
                if item.is_symlink():
                    raise InstallError("Runtime configuration must not contain symlinks.")
            shutil.copytree(source_config, destination)
        else:
            destination.mkdir(parents=True)
            documents = {
                "connections.json": {"version": 2, "connections": {}},
                "secrets.json": {"version": 2, "secrets": {}},
                "projects.json": {"version": 2, "projects": {}},
            }
            for name, payload in documents.items():
                atomic_write_json(destination / name, payload, 0o600)
        if os.name != "nt":
            os.chmod(destination, 0o700)
            os.chmod(destination / "secrets.json", 0o600)
        old_logs = self.runtime_root / "logs"
        if old_logs.is_dir():
            shutil.copytree(old_logs, staging / "logs")
        else:
            (staging / "logs").mkdir(parents=True)
        (staging / "state").mkdir(parents=True)

    def _create_venv(self, staging: pathlib.Path) -> pathlib.Path:
        _run(
            [str(self.python), "-m", "venv", str(staging / ".venv")],
            label=(
                "Creating the dedicated venv (the selected Python may be missing venv/ensurepip)"
            ),
        )
        python_path = venv_python(staging)
        if not python_path.is_file():
            raise InstallError("The dedicated venv did not create its Python executable.")
        _run([str(python_path), "-m", "pip", "--version"], label="venv ensurepip check")
        if not self.skip_dependency_install:
            for requirements in (
                staging / "service" / "requirements.txt",
                staging / "adapter" / "requirements-mcp.txt",
            ):
                _run(
                    [
                        str(python_path),
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "-r",
                        str(requirements),
                    ],
                    label=f"Installing runtime dependencies from {requirements.name}",
                )
        return python_path

    def _validate_staged_config(
        self, staging: pathlib.Path, staged_python: pathlib.Path
    ) -> None:
        script = (
            "import pathlib,sys; "
            "sys.path.insert(0, sys.argv[1]); "
            "from service.config import (assert_secure_config_permissions,load_connections,load_projects,load_secrets); "
            "root=pathlib.Path(sys.argv[2]); "
            "assert_secure_config_permissions(root); "
            "load_connections(root/'connections.json'); "
            "load_secrets(root/'secrets.json'); "
            "load_projects(root/'projects.json')"
        )
        _run(
            [
                str(staged_python),
                "-B",
                "-c",
                script,
                str(staging / "service"),
                str(staging / "config"),
            ],
            label="Strict staged configuration validation",
        )

    def _stop_existing(self, existing: dict[str, Any] | None) -> None:
        if existing is None:
            return
        self._blocking_orphans()
        state_path = self.runtime_root / "state" / "service.json"
        if not state_path.exists():
            return
        old_python = venv_python(self.runtime_root)
        old_control = self.runtime_root / "control" / "control.py"
        if not old_python.is_file() or not old_control.is_file():
            raise InstallError("The existing daemon cannot be stopped by its managed runtime.")
        try:
            result = subprocess.run(
                [
                    str(old_python),
                    "-B",
                    str(old_control),
                    "--runtime-root",
                    str(self.runtime_root),
                    "service",
                    "stop",
                ],
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise InstallError("The existing metadata daemon could not be stopped.") from exc
        if result.returncode != 0:
            raise InstallError("The existing metadata daemon could not be verified and stopped.")
        self._blocking_orphans()

    def install(self) -> pathlib.Path:
        self.codex_home.mkdir(parents=True, exist_ok=True)
        existing = self._detect_existing()
        installation_id = (
            str(existing["installation_id"]) if existing else str(uuid.uuid4())
        )
        staging = self.runtime_root.with_name(
            f".{self.runtime_root.name}.{uuid.uuid4().hex}.staging"
        )
        backup = self.runtime_root.with_name(
            f".{self.runtime_root.name}.{uuid.uuid4().hex}.backup"
        )
        config_existed = self.config_path.exists()
        config_before = self._config_content()
        moved_existing = False
        moved_staging = False
        try:
            staging.mkdir(parents=True)
            self._stage_sources(staging)
            self._stage_data(staging)
            staged_python = self._create_venv(staging)
            self._validate_staged_config(staging, staged_python)
            final_python = venv_python(self.runtime_root)
            block = managed_config_block(
                installation_id, self.runtime_root, final_python
            )
            dependency_status = (
                "incomplete" if self.skip_dependency_install else "completed"
            )
            install_state = {
                "version": 2,
                "installation_id": installation_id,
                "runtime_root": str(self.runtime_root),
                "config_path": str(self.config_path),
                "config_block_hash": sha256_bytes(block.encode("utf-8")),
                "python_path": str(final_python),
                "dependency_installation": dependency_status,
                "managed_files": managed_file_manifest(
                    staging, ("adapter", "service", "control")
                ),
                "managed_trees": [
                    {"path": ".venv", "sha256": tree_digest(staging / ".venv")}
                ],
                "installed_at": datetime.now(UTC).isoformat(),
            }
            atomic_write_json(staging / "install-state.json", install_state, 0o600)
            _run(
                [str(staged_python), "-B", str(staging / "service" / "server.py"), "--self-check"],
                label="Metadata service self-check",
            )
            if dependency_status == "completed":
                _run(
                    [
                        str(staged_python),
                        "-B",
                        str(staging / "adapter" / "mcp_server.py"),
                        "--runtime-root",
                        str(staging),
                        "--self-check",
                    ],
                    label="MCP adapter self-check",
                )
            self._stop_existing(existing)
            if self.runtime_root.exists():
                os.replace(self.runtime_root, backup)
                moved_existing = True
            os.replace(staging, self.runtime_root)
            moved_staging = True
            updated_config = replace_managed_config(config_before, block)
            atomic_write_bytes(self.config_path, updated_config.encode("utf-8"), 0o600)
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            return self.runtime_root
        except Exception:
            if moved_staging and self.runtime_root.exists():
                failed = self.runtime_root.with_name(
                    f".{self.runtime_root.name}.{uuid.uuid4().hex}.failed"
                )
                os.replace(self.runtime_root, failed)
                if moved_existing and backup.exists():
                    os.replace(backup, self.runtime_root)
                shutil.rmtree(failed, ignore_errors=True)
            elif moved_existing and backup.exists() and not self.runtime_root.exists():
                os.replace(backup, self.runtime_root)
            if config_existed:
                atomic_write_bytes(self.config_path, config_before.encode("utf-8"), 0o600)
            else:
                self.config_path.unlink(missing_ok=True)
            raise
        finally:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            if backup.exists() and not self.runtime_root.exists():
                os.replace(backup, self.runtime_root)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install or upgrade database-schema-bootstrap v2."
    )
    parser.add_argument("--python")
    parser.add_argument("--codex-home")
    parser.add_argument("--skip-dependency-install", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        python = _select_python(args.python)
        codex_home = pathlib.Path(
            args.codex_home
            or os.environ.get("CODEX_HOME")
            or pathlib.Path.home() / ".codex"
        )
        repo_root = pathlib.Path(__file__).resolve().parents[2]
        runtime = Installer(
            repo_root=repo_root,
            codex_home=codex_home,
            python=python,
            skip_dependency_install=args.skip_dependency_install,
        ).install()
        print(f"Installed database-schema-bootstrap v2 runtime: {runtime}")
        if args.skip_dependency_install:
            print(
                "Dependency installation was skipped; runtime is incomplete and hooks/adapters are disabled."
            )
        return 0
    except InstallError as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
