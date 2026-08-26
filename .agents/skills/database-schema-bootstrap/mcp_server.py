from __future__ import annotations

import argparse
import json
import logging
import math
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from project_routing import INSTALL_STATE_FIELDS, ProjectMetadataRouter
from rpc_client import MetadataServiceError


logger = logging.getLogger(__name__)
T = TypeVar("T")


def _finite_positive_timeout(value: str) -> float:
    try:
        timeout = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "timeout must be a finite positive number."
        ) from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise argparse.ArgumentTypeError("timeout must be a finite positive number.")
    return timeout


def _safe_call(operation: str, callback: Callable[[], T]) -> T:
    try:
        return callback()
    except MetadataServiceError as exc:
        logger.warning("%s failed: %s", operation, exc)
        raise RuntimeError(str(exc)) from None
    except Exception:
        logger.exception("%s failed", operation)
        raise RuntimeError("Database metadata operation failed.") from None


def create_server(client: Any) -> Any:
    """Expose exactly three metadata tools and optional connection selection."""

    from mcp.server import MCPServer
    from mcp.types import ToolAnnotations

    server = MCPServer("database-schema-bootstrap")
    read_only_annotations = ToolAnnotations(
        read_only_hint=True,
        open_world_hint=False,
    )

    @server.tool(annotations=read_only_annotations)
    def list_databases(connection_id: str | None = None) -> list[dict[str, str]]:
        """List database names for one enabled project connection."""

        return _safe_call(
            "list_databases", lambda: client.list_databases(connection_id)
        )

    @server.tool(annotations=read_only_annotations)
    def list_tables(connection_id: str | None = None) -> list[dict[str, str]]:
        """List base tables for one enabled project connection."""

        return _safe_call("list_tables", lambda: client.list_tables(connection_id))

    @server.tool(annotations=read_only_annotations)
    def describe_table(
        table: str, connection_id: str | None = None
    ) -> dict[str, object]:
        """Describe one table without reading application rows."""

        return _safe_call(
            "describe_table", lambda: client.describe_table(table, connection_id)
        )

    return server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-facing stdio adapter for metadata gateway v2."
    )
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--runtime-root", help=argparse.SUPPRESS)
    parser.add_argument("--endpoint", help=argparse.SUPPRESS)
    parser.add_argument(
        "--timeout",
        type=_finite_positive_timeout,
        default=25.0,
        help="End-to-end routing timeout in seconds.",
    )
    return parser.parse_args(argv)


def _assert_runtime_complete(runtime_root: Path) -> None:
    try:
        data = json.loads(
            (runtime_root / "install-state.json").read_text(encoding="utf-8")
        )
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise MetadataServiceError("Database metadata runtime is not installed.") from exc
    if (
        not isinstance(data, dict)
        or set(data) != INSTALL_STATE_FIELDS
        or data.get("version") != 2
        or data.get("dependency_installation") != "completed"
    ):
        raise MetadataServiceError("Database metadata runtime is incomplete.")


def build_server(timeout: float = 25.0, *, runtime_root: Path | None = None) -> Any:
    root = runtime_root or Path(__file__).resolve().parent.parent
    _assert_runtime_complete(root)
    return create_server(ProjectMetadataRouter(root, timeout=timeout))


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = parse_args(argv)
    try:
        if args.endpoint is not None:
            raise MetadataServiceError("Static metadata service endpoints are not allowed.")
        runtime_root = (
            Path(args.runtime_root).absolute()
            if args.runtime_root
            else Path(__file__).resolve().parent.parent
        )
        if args.self_check:
            _assert_runtime_complete(runtime_root)
            from mcp.server import MCPServer  # noqa: F401

            return 0
        server = build_server(args.timeout, runtime_root=runtime_root)
    except (MetadataServiceError, ImportError):
        logger.error("MCP adapter startup failed.")
        return 1
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
