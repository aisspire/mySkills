from __future__ import annotations

import argparse
import logging
from collections.abc import Callable
from typing import TypeVar

from mcp.server import MCPServer

from rpc_client import MetadataServiceClient, MetadataServiceError


logger = logging.getLogger(__name__)
T = TypeVar("T")


def _safe_call(operation: str, callback: Callable[[], T]) -> T:
    try:
        return callback()
    except MetadataServiceError as exc:
        logger.warning("%s failed: %s", operation, exc)
        raise RuntimeError(str(exc)) from None
    except Exception:
        logger.exception("%s failed", operation)
        raise RuntimeError("Database metadata operation failed.") from None


def create_server(client: MetadataServiceClient) -> MCPServer:
    """Expose only the fixed metadata tools to the MCP client."""

    server = MCPServer("database-schema-bootstrap")

    @server.tool()
    def list_databases() -> list[dict[str, str]]:
        """List PostgreSQL database names only; never read application rows."""

        return _safe_call("list_databases", client.list_databases)

    @server.tool()
    def list_tables() -> list[dict[str, str]]:
        """List base tables in the configured PostgreSQL schema only."""

        return _safe_call("list_tables", client.list_tables)

    @server.tool()
    def describe_table(table: str) -> dict[str, object]:
        """Describe one configured-schema table without reading business rows."""

        return _safe_call("describe_table", lambda: client.describe_table(table))

    return server


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="AI-facing MCP adapter for the independent metadata service."
    )
    parser.add_argument(
        "--endpoint",
        default="http://127.0.0.1:8765",
        help="Loopback endpoint of the separately started metadata service.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="RPC timeout in seconds.",
    )
    return parser.parse_args(argv)


def build_server(endpoint: str, timeout: float = 10.0) -> MCPServer:
    return create_server(MetadataServiceClient(endpoint, timeout=timeout))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        server = build_server(args.endpoint, args.timeout)
    except MetadataServiceError as exc:
        logger.error("MCP adapter startup failed: %s", exc)
        return 1
    server.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

