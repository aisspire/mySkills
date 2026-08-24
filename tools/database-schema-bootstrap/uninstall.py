from __future__ import annotations

import argparse
import json
import os
import pathlib
import shutil
import sys
from typing import Any

from control import (
    Control,
    ControlError,
    atomic_file_transaction,
    git_exclude_path,
    remove_exclude_marker,
)
from installer_common import (
    InstallError,
    atomic_write_bytes,
    inspect_managed_config,
    is_strict_v2_data_layout,
    read_install_state,
    remove_managed_config,
    sha256_bytes,
    sha256_file,
    tree_digest,
)


ALL_CATEGORIES = (
    "codex-config",
    "runtime",
    "venv",
    "state",
    "logs",
    "connections",
    "secrets",
    "project-registrations",
    "project-access",
)
DEFAULT_CATEGORIES = ("codex-config", "runtime", "venv", "state", "logs")
IRREVERSIBLE_CATEGORIES = {
    "connections",
    "secrets",
    "project-registrations",
    "project-access",
}


class UninstallError(RuntimeError):
    pass


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


class Uninstaller:
    def __init__(self, codex_home: pathlib.Path) -> None:
        self.codex_home = codex_home.absolute()
        self.runtime_root = self.codex_home / "database-schema-bootstrap"
        self.config_path = self.codex_home / "config.toml"
        self.report: list[dict[str, str]] = []

    def _state(self) -> dict[str, Any] | None:
        path = self.runtime_root / "install-state.json"
        if not path.exists():
            if self.runtime_root.exists() and is_strict_v2_data_layout(self.runtime_root):
                return None
            if self.runtime_root.exists() and any(self.runtime_root.iterdir()):
                raise UninstallError(
                    "Runtime has no strict v2 installation state; refusing managed deletion."
                )
            return None
        try:
            return read_install_state(path)
        except InstallError as exc:
            raise UninstallError(str(exc)) from exc

    def _config_info(self, state: dict[str, Any] | None) -> dict[str, str]:
        try:
            content = self.config_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {"status": "missing", "content": "", "block": ""}
        except OSError as exc:
            raise UninstallError("Codex config.toml could not be read.") from exc
        try:
            installation_id, block = inspect_managed_config(content)
        except InstallError as exc:
            return {"status": "modified", "content": content, "block": ""}
        if block is None:
            return {"status": "missing", "content": content, "block": ""}
        if state is None:
            return {"status": "unowned", "content": content, "block": block}
        if (
            installation_id != str(state["installation_id"]).lower()
            or sha256_bytes(block.encode("utf-8")) != state["config_block_hash"]
        ):
            return {"status": "modified", "content": content, "block": block}
        return {"status": "verified", "content": content, "block": block}

    def inventory(self) -> list[dict[str, str]]:
        state = self._state()
        config = self._config_info(state)
        items = [
            {
                "category": "codex-config",
                "target": str(self.config_path),
                "status": config["status"],
            }
        ]
        paths = {
            "runtime": [
                self.runtime_root / "adapter",
                self.runtime_root / "service",
                self.runtime_root / "control",
                self.runtime_root / "install-state.json",
            ],
            "venv": [self.runtime_root / ".venv"],
            "state": [self.runtime_root / "state"],
            "logs": [self.runtime_root / "logs"],
            "connections": [self.runtime_root / "config" / "connections.json"],
            "secrets": [self.runtime_root / "config" / "secrets.json"],
            "project-registrations": [
                self.runtime_root / "config" / "projects.json"
            ],
        }
        for category, targets in paths.items():
            for target in targets:
                items.append(
                    {
                        "category": category,
                        "target": str(target),
                        "status": "present" if target.exists() else "missing",
                    }
                )
        projects_path = self.runtime_root / "config" / "projects.json"
        try:
            data = json.loads(projects_path.read_text(encoding="utf-8"))
            records = data.get("projects", {}) if isinstance(data, dict) else {}
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            records = {}
        if isinstance(records, dict):
            for record in records.values():
                access_path = record.get("access_path") if isinstance(record, dict) else None
                if isinstance(access_path, str):
                    items.append(
                        {
                            "category": "project-access",
                            "target": access_path,
                            "status": "present"
                            if pathlib.Path(access_path).exists()
                            else "missing",
                        }
                    )
        return items

    def _assert_no_blocking_orphans(self) -> None:
        path = self.runtime_root / "state" / "orphans.json"
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UninstallError(
                "Orphan service records are invalid; destructive cleanup is blocked."
            ) from exc
        records = data.get("orphans") if isinstance(data, dict) else None
        if not isinstance(records, list):
            raise UninstallError(
                "Orphan service records are invalid; destructive cleanup is blocked."
            )
        for record in records:
            if not isinstance(record, dict):
                raise UninstallError("Invalid orphan record blocks destructive cleanup.")
            if record.get("pid") is None or _pid_alive(record.get("pid")):
                raise UninstallError(
                    "An unverifiable service process blocks runtime/state deletion."
                )

    def _stop_service(self) -> None:
        state_path = self.runtime_root / "state" / "service.json"
        if not state_path.exists():
            self._assert_no_blocking_orphans()
            return
        try:
            Control(self.runtime_root).service_stop()
        except (ControlError, Exception) as exc:
            raise UninstallError(
                "The metadata daemon could not be verified and stopped; no runtime files were deleted."
            ) from exc
        self._assert_no_blocking_orphans()

    def _verified_program_files(self, state: dict[str, Any]) -> list[pathlib.Path]:
        paths: list[pathlib.Path] = []
        for record in state["managed_files"]:
            if not isinstance(record, dict) or set(record) != {"path", "sha256"}:
                raise UninstallError("Managed file manifest is invalid.")
            path = (self.runtime_root / record["path"]).absolute()
            try:
                path.relative_to(self.runtime_root)
            except ValueError as exc:
                raise UninstallError("Managed file manifest escapes the runtime.") from exc
            if not path.exists():
                self.report.append(
                    {"target": str(path), "result": "already-missing"}
                )
                continue
            if not path.is_file() or sha256_file(path) != record["sha256"]:
                self.report.append({"target": str(path), "result": "preserved-modified"})
                continue
            paths.append(path)
        return paths

    def _remove_program(self, state: dict[str, Any]) -> bool:
        verified = self._verified_program_files(state)
        modified = any(item["result"] == "preserved-modified" for item in self.report)
        for path in verified:
            path.unlink()
            self.report.append({"target": str(path), "result": "removed"})
        for name in ("adapter", "service", "control"):
            root = self.runtime_root / name
            if root.exists():
                for directory in sorted(
                    (item for item in root.rglob("*") if item.is_dir()),
                    reverse=True,
                ):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
                try:
                    root.rmdir()
                except OSError:
                    self.report.append(
                        {"target": str(root), "result": "preserved-unknown-files"}
                    )
                    modified = True
        return not modified

    def _remove_venv(self, state: dict[str, Any]) -> bool:
        records = state["managed_trees"]
        record = next(
            (
                item
                for item in records
                if isinstance(item, dict) and item.get("path") == ".venv"
            ),
            None,
        )
        path = self.runtime_root / ".venv"
        if not path.exists():
            return True
        if (
            not isinstance(record, dict)
            or set(record) != {"path", "sha256"}
            or tree_digest(path) != record["sha256"]
        ):
            self.report.append({"target": str(path), "result": "preserved-modified"})
            return False
        shutil.rmtree(path)
        self.report.append({"target": str(path), "result": "removed"})
        return True

    def _remove_project_access(self) -> None:
        projects_path = self.runtime_root / "config" / "projects.json"
        try:
            data = json.loads(projects_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
            raise UninstallError(
                "Project registrations are invalid; project access files were preserved."
            ) from exc
        if set(data) != {"version", "projects"} or data.get("version") != 2:
            raise UninstallError(
                "Project registrations are invalid; project access files were preserved."
            )
        changes: dict[pathlib.Path, bytes | None] = {}
        for record in data["projects"].values():
            if not isinstance(record, dict):
                raise UninstallError("Project registration record is invalid.")
            access_path = pathlib.Path(record.get("access_path", "")).absolute()
            root = pathlib.Path(record.get("root", "")).absolute()
            expected = root / ".agents" / "database-schema-bootstrap" / "access.json"
            if access_path != expected:
                raise UninstallError("Project access record escapes its registered root.")
            changes[access_path] = None
            try:
                exclude = git_exclude_path(str(root))
                content = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
                changes[exclude] = remove_exclude_marker(content).encode("utf-8")
            except (ControlError, OSError):
                self.report.append(
                    {"target": str(root), "result": "exclude-marker-preserved"}
                )
        atomic_file_transaction(changes)
        for path, value in changes.items():
            if value is None:
                self.report.append({"target": str(path), "result": "removed"})

    def uninstall(self, categories: set[str]) -> list[dict[str, str]]:
        state = self._state()
        config = self._config_info(state)
        core_selected = bool(categories & {"runtime", "venv", "state"})
        if state is None and core_selected and not is_strict_v2_data_layout(self.runtime_root):
            raise UninstallError("No strict v2 installation is available for core cleanup.")
        if core_selected and state is not None:
            if config["status"] == "modified":
                raise UninstallError(
                    "The managed Codex block was edited; runtime deletion is blocked."
                )
            self._stop_service()
        if "project-access" in categories:
            self._remove_project_access()
        if "codex-config" in categories and config["status"] == "verified":
            updated = remove_managed_config(config["content"])
            atomic_write_bytes(self.config_path, updated.encode("utf-8"), 0o600)
            self.report.append(
                {"target": str(self.config_path), "result": "managed-block-removed"}
            )
        elif "codex-config" in categories and config["status"] not in {"missing"}:
            self.report.append(
                {"target": str(self.config_path), "result": "preserved-unverified"}
            )

        runtime_clean = True
        venv_clean = True
        if state is not None and "runtime" in categories:
            runtime_clean = self._remove_program(state)
        if state is not None and "venv" in categories:
            venv_clean = self._remove_venv(state)
        for category, name in (("state", "state"), ("logs", "logs")):
            path = self.runtime_root / name
            if category in categories and path.exists():
                shutil.rmtree(path)
                self.report.append({"target": str(path), "result": "removed"})
        data_paths = {
            "connections": self.runtime_root / "config" / "connections.json",
            "secrets": self.runtime_root / "config" / "secrets.json",
            "project-registrations": self.runtime_root / "config" / "projects.json",
        }
        for category, path in data_paths.items():
            if category in categories and path.exists():
                path.unlink()
                self.report.append({"target": str(path), "result": "removed"})
        if (
            state is not None
            and "runtime" in categories
            and runtime_clean
            and ("venv" not in categories or venv_clean)
        ):
            install_state_path = self.runtime_root / "install-state.json"
            install_state_path.unlink(missing_ok=True)
            self.report.append(
                {"target": str(install_state_path), "result": "removed"}
            )
        config_root = self.runtime_root / "config"
        if config_root.exists():
            try:
                config_root.rmdir()
            except OSError:
                pass
        if self.runtime_root.exists():
            try:
                self.runtime_root.rmdir()
            except OSError:
                pass
        return self.report


def _parse_categories(raw: str | None, all_selected: bool) -> set[str]:
    if all_selected:
        return set(ALL_CATEGORIES)
    if raw is None:
        return set(DEFAULT_CATEGORIES)
    selected = {item.strip() for item in raw.split(",") if item.strip()}
    unknown = selected - set(ALL_CATEGORIES)
    if unknown:
        raise UninstallError(f"Unknown uninstall categories: {', '.join(sorted(unknown))}")
    return selected


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Uninstall database-schema-bootstrap v2.")
    parser.add_argument("--codex-home")
    parser.add_argument("--categories")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--confirm", action="store_true")
    parser.add_argument("--confirm-all", action="store_true")
    parser.add_argument("--inventory-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    codex_home = pathlib.Path(
        args.codex_home
        or os.environ.get("CODEX_HOME")
        or pathlib.Path.home() / ".codex"
    )
    uninstaller = Uninstaller(codex_home)
    try:
        categories = _parse_categories(args.categories, args.all)
        print(json.dumps(uninstaller.inventory(), ensure_ascii=False, indent=2))
        if args.inventory_only:
            return 0
        if categories & IRREVERSIBLE_CATEGORIES:
            if not args.confirm_all:
                raise UninstallError(
                    "Deleting connections, secrets, registrations, or project access is irreversible; pass --confirm-all after reviewing the inventory."
                )
        elif not (args.confirm or args.confirm_all):
            raise UninstallError(
                "Pass --confirm after reviewing the ordinary uninstall inventory."
            )
        report = uninstaller.uninstall(categories)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except (UninstallError, InstallError, ControlError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
