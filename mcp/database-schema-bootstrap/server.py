from __future__ import annotations

import argparse
import json
import logging
import pathlib

from service.config import (
    assert_secure_config_permissions,
    load_connections,
    load_projects,
    load_secrets,
)
from service.errors import ConfigError, GatewayError
from service.gateway import MetadataGateway
from service.http_server import MetadataHttpServer
from service.runtime_state import remove_ready_state_if_owned, write_ready_state


logger = logging.getLogger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local PostgreSQL metadata gateway v2."
    )
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--runtime-root")
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--instance-token")
    parser.add_argument("--process-identity")
    parser.add_argument("--ready-state")
    return parser.parse_args(argv)


def _load_installation_id(runtime_root: pathlib.Path) -> str:
    state_path = runtime_root / "install-state.json"
    try:
        data = json.loads(state_path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        raise ConfigError("Runtime installation state is unavailable.") from exc
    if not isinstance(data, dict) or data.get("version") != 2:
        raise ConfigError("Runtime installation state is invalid.")
    if data.get("dependency_installation") != "completed":
        raise ConfigError("Runtime dependency installation is incomplete.")
    installation_id = data.get("installation_id")
    if not isinstance(installation_id, str) or not installation_id:
        raise ConfigError("Runtime installation identity is invalid.")
    return installation_id


def build_server(
    runtime_root: str | pathlib.Path,
    *,
    port: int = 0,
    instance_token: str,
    process_identity: str,
    ready_state: str | pathlib.Path | None = None,
    installation_id: str | None = None,
    gateway: MetadataGateway | None = None,
) -> MetadataHttpServer:
    if not 0 <= port <= 65535:
        raise ConfigError("Service port must be between 0 and 65535.")
    if not instance_token or not process_identity:
        raise ConfigError("Service instance identity is incomplete.")
    root = pathlib.Path(runtime_root).absolute()
    config_root = root / "config"
    state_path = pathlib.Path(ready_state) if ready_state else root / "state" / "service.json"
    if state_path.absolute() != (root / "state" / "service.json").absolute():
        raise ConfigError("Service state path is outside the managed runtime location.")
    assert_secure_config_permissions(config_root)
    load_connections(config_root / "connections.json")
    load_secrets(config_root / "secrets.json")
    load_projects(config_root / "projects.json")
    effective_installation_id = installation_id or _load_installation_id(root)
    effective_gateway = gateway or MetadataGateway(config_root)
    server = MetadataHttpServer(
        ("127.0.0.1", port),
        effective_gateway,
        instance_token=instance_token,
        installation_id=effective_installation_id,
        process_identity=process_identity,
    )
    actual_port = server.server_address[1]
    write_ready_state(
        state_path,
        endpoint=f"http://127.0.0.1:{actual_port}",
        port=actual_port,
        installation_id=effective_installation_id,
        instance_token=instance_token,
        process_identity=process_identity,
    )
    return server


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = parse_args(argv)
    if args.self_check:
        return 0
    if not all(
        (args.runtime_root, args.instance_token, args.process_identity, args.ready_state)
    ):
        logger.error("Metadata service startup arguments are incomplete.")
        return 2
    try:
        server = build_server(
            args.runtime_root,
            port=args.port,
            instance_token=args.instance_token,
            process_identity=args.process_identity,
            ready_state=args.ready_state,
        )
    except GatewayError:
        logger.error("Metadata service startup failed.")
        return 1
    logger.warning("Metadata service listening on 127.0.0.1:%s", server.server_address[1])
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        logger.warning("Metadata service stopped.")
    finally:
        server.server_close()
        remove_ready_state_if_owned(
            args.ready_state,
            instance_token=args.instance_token,
            process_identity=args.process_identity,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
