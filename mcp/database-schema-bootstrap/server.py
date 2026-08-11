from __future__ import annotations

import argparse
import logging

from service.config import load_profile
from service.errors import ConfigError, GatewayError
from service.http_server import MetadataHttpServer
from service.postgres_metadata import PostgresMetadataService


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
        default=8765,
        help="Loopback HTTP port for the fixed metadata protocol.",
    )
    return parser.parse_args(argv)


def build_server(config_path: str, port: int = 8765) -> MetadataHttpServer:
    if not 1 <= port <= 65535:
        raise ConfigError("Service port must be between 1 and 65535.")
    profile = load_profile(config_path)
    service = PostgresMetadataService(profile)
    return MetadataHttpServer(("127.0.0.1", port), service)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = parse_args(argv)
    try:
        server = build_server(args.config, args.port)
    except GatewayError as exc:
        logger.error("Metadata service startup failed: %s", exc)
        return 1

    logger.warning("Metadata service listening on 127.0.0.1:%s", args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.warning("Metadata service stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

