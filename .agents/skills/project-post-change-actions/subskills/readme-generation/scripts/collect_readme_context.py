#!/usr/bin/env python3
"""Collect project facts that help draft a truthful README."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


MANIFESTS = [
    "package.json",
    "Cargo.toml",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "composer.json",
    "Gemfile",
    "Makefile",
    "CMakeLists.txt",
    "tauri.conf.json",
    "src-tauri/tauri.conf.json",
]

LOCKFILES = [
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lockb",
    "Cargo.lock",
    "poetry.lock",
    "uv.lock",
    "Pipfile.lock",
]

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}
IMAGE_DIRS = ["docs", "assets", "public", "static", "media", ".github"]


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def exists(root: Path, names: list[str]) -> list[str]:
    return [name for name in names if (root / name).exists()]


def read_package_json(path: Path) -> dict[str, object]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - report scan errors, do not fail whole inventory
        return {"error": str(exc)}

    keys = ["name", "version", "description", "license", "type"]
    result: dict[str, object] = {key: data.get(key) for key in keys if data.get(key)}
    scripts = data.get("scripts")
    if isinstance(scripts, dict):
        result["scripts"] = sorted(scripts.keys())
    deps = []
    for dep_key in ["dependencies", "devDependencies"]:
        values = data.get(dep_key)
        if isinstance(values, dict):
            deps.extend(values.keys())
    if deps:
        result["notable_dependencies"] = sorted(deps)[:25]
    return result


def grep_toml_value(text: str, key: str) -> str | None:
    prefix = f"{key} = "
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(prefix):
            return stripped.removeprefix(prefix).strip().strip('"')
    return None


def read_toml_summary(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}

    result: dict[str, str] = {}
    for key in ["name", "version", "description", "license", "edition"]:
        value = grep_toml_value(text, key)
        if value:
            result[key] = value
    return result


def git_value(root: Path, args: list[str]) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            text=True,
            capture_output=True,
            check=True,
        )
    except Exception:
        return None
    value = completed.stdout.strip()
    return value or None


def find_images(root: Path, limit: int) -> list[str]:
    images: list[str] = []
    for dirname in IMAGE_DIRS:
        base = root / dirname
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS:
                images.append(rel(path, root))
                if len(images) >= limit:
                    return images
    return images


def find_ci(root: Path) -> list[str]:
    ci_paths: list[str] = []
    github_workflows = root / ".github" / "workflows"
    if github_workflows.exists():
        ci_paths.extend(rel(path, root) for path in github_workflows.glob("*") if path.is_file())
    for name in [".gitlab-ci.yml", "azure-pipelines.yml", "Jenkinsfile"]:
        if (root / name).exists():
            ci_paths.append(name)
    return sorted(ci_paths)


def collect(root: Path, image_limit: int) -> dict[str, object]:
    root = root.resolve()
    readmes = sorted(path.name for path in root.glob("README*") if path.is_file())
    licenses = sorted(path.name for path in root.glob("LICENSE*") if path.is_file())

    manifests = exists(root, MANIFESTS)
    manifest_details: dict[str, object] = {}
    if (root / "package.json").exists():
        manifest_details["package.json"] = read_package_json(root / "package.json")
    for toml_name in ["Cargo.toml", "pyproject.toml"]:
        if (root / toml_name).exists():
            manifest_details[toml_name] = read_toml_summary(root / toml_name)

    remote = git_value(root, ["remote", "get-url", "origin"])
    branch = git_value(root, ["branch", "--show-current"])

    return {
        "root": str(root),
        "git": {"remote_origin": remote, "branch": branch},
        "readmes": readmes,
        "licenses": licenses,
        "manifests": manifests,
        "locks": exists(root, LOCKFILES),
        "manifest_details": manifest_details,
        "ci": find_ci(root),
        "images": find_images(root, image_limit),
        "top_level_dirs": sorted(
            path.name for path in root.iterdir() if path.is_dir() and not path.name.startswith(".git")
        )[:40],
    }


def print_markdown(data: dict[str, object]) -> None:
    print("# README Context Inventory")
    print()
    print(f"- Root: `{data['root']}`")
    git = data["git"]
    if isinstance(git, dict):
        print(f"- Git remote: `{git.get('remote_origin') or 'unknown'}`")
        print(f"- Git branch: `{git.get('branch') or 'unknown'}`")
    for key, label in [
        ("readmes", "README files"),
        ("licenses", "License files"),
        ("manifests", "Manifests"),
        ("locks", "Lockfiles"),
        ("ci", "CI files"),
        ("images", "Candidate images"),
        ("top_level_dirs", "Top-level dirs"),
    ]:
        values = data.get(key) or []
        if values:
            joined = ", ".join(f"`{value}`" for value in values)
            print(f"- {label}: {joined}")
        else:
            print(f"- {label}: none found")
    details = data.get("manifest_details") or {}
    if details:
        print()
        print("## Manifest Details")
        for name, value in details.items():
            print()
            print(f"### {name}")
            print("```json")
            print(json.dumps(value, ensure_ascii=False, indent=2))
            print("```")


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect project facts for README drafting.")
    parser.add_argument("root", nargs="?", default=".", help="Project root to inspect.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    parser.add_argument("--image-limit", type=int, default=30, help="Maximum image paths to list.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists():
        raise SystemExit(f"Project root does not exist: {root}")
    if not root.is_dir():
        raise SystemExit(f"Project root is not a directory: {root}")

    data = collect(root, args.image_limit)
    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print_markdown(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
