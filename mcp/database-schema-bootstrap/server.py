from __future__ import annotations

import argparse
import logging

from service.config import load_profile
from service.errors import ConfigError, GatewayError
from service.http_server import MetadataHttpServer
from service.path_identity import canonical_project_root
from service.postgres_metadata import PostgresMetadataService
from service.runtime_state import remove_ready_state_if_owned, write_ready_state


logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Independent PostgreSQL metadata service."
    )
    parser.add_argument(
        "--config",
        required=True,
        help="Absolute path to the project PostgreSQL profile.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="Loopback HTTP port; use 0 to request an available system port.",
    )
    parser.add_argument(
        "--instance-token",
        required=True,
        help="Opaque per-instance loopback authentication token.",
    )
    parser.add_argument(
        "--ready-state",
        required=True,
        help="Path of the atomically written ready-state JSON file.",
    )
    parser.add_argument(
        "--project-id",
        required=True,
        help="SHA-256 identity of the project root served by this instance.",
    )
    parser.add_argument(
        "--project-root",
        required=True,
        help="Canonical project-root path used for ready-state validation.",
    )
    return parser.parse_args(argv)


def build_server(
    config_path: str,
    port: int = 0,
    *,
    instance_token: str | None = None,
    ready_state: str | None = None,
    project_id: str | None = None,
    project_root: str | None = None,
) -> MetadataHttpServer:
    if not 0 <= port <= 65535:
        raise ConfigError("Service port must be between 0 and 65535.")
    instance_values = (instance_token, ready_state, project_id, project_root)
    if any(value is not None for value in instance_values) and not all(instance_values):
        raise ConfigError(
            "Instance token, ready-state path, project ID, and project root must be supplied together."
        )
    if instance_token is not None and not instance_token.strip():
        raise ConfigError("Service instance token must not be empty.")
    try:
        canonical_root = canonical_project_root(project_root or "")
    except ValueError as exc:
        raise ConfigError("Service project root is invalid.") from exc
    profile = load_profile(config_path)
    service = PostgresMetadataService(profile)
    server = MetadataHttpServer(
        ("127.0.0.1", port),
        service,
        instance_token=instance_token,
        project_id=project_id,
    )
    if ready_state is not None:
        actual_port = server.server_address[1]
        write_ready_state(
            ready_state,
            endpoint=f"http://127.0.0.1:{actual_port}",
            port=actual_port,
            project_id=project_id or "",
            project_root=canonical_root,
            instance_token=instance_token or "",
        )
    return server


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = parse_args(argv)
    try:
        server = build_server(
            args.config,
            args.port,
            instance_token=args.instance_token,
            ready_state=args.ready_state,
            project_id=args.project_id,
            project_root=args.project_root,
        )
    except GatewayError as exc:
        logger.error("Metadata service startup failed: %s", exc)
        return 1

    logger.warning("Metadata service listening on 127.0.0.1:%s", server.server_address[1])
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warning("Metadata service stopped.")
    finally:
        server.server_close()
        remove_ready_state_if_owned(
            args.ready_state,
            instance_token=args.instance_token,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
