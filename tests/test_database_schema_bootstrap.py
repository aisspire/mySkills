from __future__ import annotations

import contextlib
import http.client
import io
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import uuid
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "database-schema-bootstrap"
SERVICE_ROOT = ROOT / "mcp" / "database-schema-bootstrap"
CONTROL_ROOT = ROOT / "tools" / "database-schema-bootstrap"
for import_root in (CONTROL_ROOT, SERVICE_ROOT, SKILL_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

try:  # The repository's top-level `mcp/` is a namespace when SDK is absent.
    from mcp import Client  # type: ignore[attr-defined]  # noqa: E402
except ImportError:
    Client = None  # type: ignore[assignment,misc]
from control import (  # noqa: E402
    EXCLUDE_END,
    EXCLUDE_START,
    Control,
    ControlError,
    FileLock,
    add_exclude_marker,
    remove_exclude_marker,
)
from install import Installer  # noqa: E402
from installer_common import (  # noqa: E402
    InstallError,
    inspect_managed_config,
    managed_config_block,
    replace_managed_config,
    venv_python,
)
from mcp_server import create_server  # noqa: E402
from project_routing import ProjectMetadataRouter, ProjectRoutingError  # noqa: E402
from rpc_client import MetadataServiceClient, MetadataServiceError  # noqa: E402
import server as service_entry  # noqa: E402
from service.config import (  # noqa: E402
    ACCESS_RELATIVE_PATH,
    AccessConfig,
    PostgresProfile,
    ProjectGrant,
    access_document,
    assert_secure_config_permissions,
    atomic_write_json,
    connection_to_json,
    ensure_config_layout,
    load_access,
    load_connections,
    load_projects,
    load_secrets,
    project_document,
)
from service.errors import (  # noqa: E402
    ConfigError,
    ConnectionUnavailableError,
    PolicyError,
)
from service.gateway import MetadataGateway, UNAVAILABLE_MESSAGE  # noqa: E402
from service.http_server import MAX_REQUEST_BYTES, MetadataHttpServer  # noqa: E402
from service.postgres_metadata import PostgresMetadataService  # noqa: E402
from service.protocol import parse_metadata_request  # noqa: E402
from service.runtime_state import (  # noqa: E402
    remove_ready_state_if_owned,
    write_ready_state,
)
from uninstall import (  # noqa: E402
    ALL_CATEGORIES,
    DEFAULT_CATEGORIES,
    UninstallError,
    Uninstaller,
)
from tests.database_schema_bootstrap_fake_service import FakeGatewayServer  # noqa: E402


def profile(connection_id: str = "erp-ro", **overrides: object) -> PostgresProfile:
    values: dict[str, object] = {
        "connection_id": connection_id,
        "host": f"{connection_id}.example.test",
        "port": 5432,
        "database": "app",
        "connection_database": "postgres",
        "schema": "public",
        "user": "metadata_reader",
    }
    values.update(overrides)
    return PostgresProfile(**values)  # type: ignore[arg-type]


def write_central_config(
    config_root: pathlib.Path,
    *,
    profiles: dict[str, PostgresProfile] | None = None,
    passwords: dict[str, str] | None = None,
    projects: dict[str, ProjectGrant] | None = None,
) -> None:
    ensure_config_layout(config_root)
    profiles = profiles or {}
    passwords = passwords or {}
    projects = projects or {}
    atomic_write_json(
        config_root / "connections.json",
        {
            "version": 2,
            "connections": {
                connection_id: connection_to_json(value)
                for connection_id, value in profiles.items()
            },
        },
    )
    atomic_write_json(
        config_root / "secrets.json",
        {
            "version": 2,
            "secrets": {
                connection_id: {"password": value}
                for connection_id, value in passwords.items()
            },
        },
        secret=True,
    )
    atomic_write_json(
        config_root / "projects.json",
        {
            "version": 2,
            "projects": {
                project_id: project_document(value)
                for project_id, value in projects.items()
            },
        },
    )


def make_git_project(parent: pathlib.Path, name: str = "project") -> pathlib.Path:
    root = parent / name
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeCursor:
    def __init__(self, responses: list[list[tuple[object, ...]]]):
        self.responses = list(responses)
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, query: str, params: object | None = None) -> None:
        self.calls.append((query, params))

    def fetchall(self):
        return self.responses.pop(0)


class FakeConnection:
    def __init__(self, responses: list[list[tuple[object, ...]]]):
        self.cursor_instance = FakeCursor(responses)
        self.closed = False

    def transaction(self):
        return FakeTransaction()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class ConfigTests(unittest.TestCase):
    def test_strict_v2_config_loads_and_unknown_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "config"
            write_central_config(
                config,
                profiles={"erp-ro": profile()},
                passwords={"erp-ro": "secret-value"},
            )
            self.assertEqual(load_connections(config / "connections.json")["erp-ro"].host, "erp-ro.example.test")
            self.assertEqual(load_secrets(config / "secrets.json")["erp-ro"], "secret-value")

            data = json.loads((config / "connections.json").read_text(encoding="utf-8"))
            data["connections"]["erp-ro"]["target_tables"] = ["users"]
            atomic_write_json(config / "connections.json", data)
            with self.assertRaises(ConfigError):
                load_connections(config / "connections.json")

    def test_password_is_allowed_only_in_strict_secrets_document(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "config"
            write_central_config(config, profiles={"erp-ro": profile()})
            data = json.loads((config / "connections.json").read_text(encoding="utf-8"))
            data["connections"]["erp-ro"]["password"] = "secret-value"
            atomic_write_json(config / "connections.json", data)
            with self.assertRaises(ConfigError) as raised:
                load_connections(config / "connections.json")
            self.assertNotIn("secret-value", str(raised.exception))

    def test_access_active_must_be_enabled_and_unknown_fields_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "access.json"
            project_id = str(uuid.uuid4())
            atomic_write_json(
                path,
                {
                    "version": 2,
                    "project_id": project_id,
                    "connections": {"erp-ro": {"enabled": False}},
                    "active": "erp-ro",
                },
            )
            with self.assertRaises(ConfigError):
                load_access(path)
            atomic_write_json(
                path,
                {
                    "version": 2,
                    "project_id": project_id,
                    "connections": {},
                    "active": None,
                    "extra": True,
                },
            )
            with self.assertRaises(ConfigError):
                load_access(path)

    @unittest.skipIf(os.name == "nt", "POSIX permission gate")
    def test_posix_config_and_secret_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            config = pathlib.Path(temporary) / "config"
            ensure_config_layout(config)
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o700)
            self.assertEqual(stat.S_IMODE((config / "secrets.json").stat().st_mode), 0o600)
            os.chmod(config / "secrets.json", 0o644)
            with self.assertRaises(ConfigError):
                assert_secure_config_permissions(config)

    def test_atomic_json_replacement_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "config.json"
            atomic_write_json(path, {"version": 2, "value": "first"})
            atomic_write_json(path, {"version": 2, "value": "second"})
            self.assertEqual(json.loads(path.read_text())["value"], "second")
            self.assertEqual(list(path.parent.glob(".*.tmp")), [])


class PostgresAndProtocolTests(unittest.TestCase):
    def test_password_enters_only_connect_factory_and_not_result(self):
        connection = FakeConnection([[('app',)]])
        captured: dict[str, object] = {}

        def connect_factory(**kwargs: object):
            captured.update(kwargs)
            return connection

        result = PostgresMetadataService(
            profile(), "secret-value", connect_factory=connect_factory
        ).list_databases()
        self.assertEqual(result, [{"database": "app"}])
        self.assertEqual(captured["password"], "secret-value")
        self.assertNotIn("secret-value", json.dumps(result))
        self.assertIn("SET TRANSACTION READ ONLY", connection.cursor_instance.calls[0][0])
        self.assertTrue(connection.closed)

    def test_fixed_table_queries_are_parameterized_and_table_injection_is_rejected(self):
        connection = FakeConnection([[('public', 'users')]])
        service = PostgresMetadataService(
            profile(), "secret-value", connect_factory=lambda **_: connection
        )
        self.assertEqual(service.list_tables()[0]["table"], "users")
        query, params = connection.cursor_instance.calls[1]
        self.assertIn("information_schema.tables", query)
        self.assertEqual(params, ("public",))
        with self.assertRaises(PolicyError):
            service.describe_table("users; SELECT 1")

    def test_protocol_accepts_exact_three_operations_and_rejects_sql_or_extra_fields(self):
        base = {
            "version": 2,
            "project_id": "33333333-3333-4333-8333-333333333333",
            "project_root": "/project",
            "connection_id": "erp-ro",
        }
        self.assertEqual(
            parse_metadata_request({**base, "operation": "list_tables"}).operation,
            "list_tables",
        )
        for payload in (
            {**base, "operation": "execute_sql", "sql": "SELECT 1"},
            {**base, "operation": "list_tables", "dsn": "postgres://secret"},
            {**base, "operation": "describe_table", "table": "users", "path": "/tmp/x"},
        ):
            with self.assertRaises(PolicyError):
                parse_metadata_request(payload)


class GatewayTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.project = self.root / "project"
        self.project.mkdir()
        self.project_root = os.path.normcase(os.path.abspath(self.project))
        self.access_path = self.project / ACCESS_RELATIVE_PATH
        self.access_path.parent.mkdir(parents=True)
        self.project_id = "11111111-1111-4111-8111-111111111111"
        atomic_write_json(
            self.access_path,
            access_document(
                AccessConfig(
                    self.project_id,
                    {"erp-ro": True, "reporting-ro": False},
                    "erp-ro",
                )
            ),
        )
        grant = ProjectGrant(
            self.project_id,
            self.project_root,
            ("erp-ro",),
            os.path.normcase(os.path.abspath(self.access_path)),
        )
        self.config = self.root / "config"
        write_central_config(
            self.config,
            profiles={
                "erp-ro": profile("erp-ro"),
                "reporting-ro": profile("reporting-ro"),
            },
            passwords={"erp-ro": "erp-secret", "reporting-ro": "report-secret"},
            projects={self.project_id: grant},
        )
        self.created: list[tuple[str, str]] = []

        created = self.created

        class FakeMetadata:
            def __init__(inner, selected, password, *, connect_factory=None):
                created.append((selected.connection_id, password))
                inner.selected = selected

            def list_databases(inner):
                return [{"database": inner.selected.database}]

            def list_tables(inner):
                return [{"schema": inner.selected.schema, "table": inner.selected.connection_id}]

            def describe_table(inner, table):
                return {"schema": inner.selected.schema, "table": table}

        self.gateway = MetadataGateway(self.config, service_factory=FakeMetadata)

    def payload(self, connection_id: str = "erp-ro", operation: str = "list_tables"):
        return {
            "version": 2,
            "project_id": self.project_id,
            "project_root": self.project_root,
            "connection_id": connection_id,
            "operation": operation,
        }

    def test_grant_enabled_root_and_secret_intersection_routes_connection(self):
        result = self.gateway.execute(self.payload())
        self.assertEqual(
            result,
            [{"connection_id": "erp-ro", "schema": "public", "table": "erp-ro"}],
        )
        self.assertEqual(self.created, [("erp-ro", "erp-secret")])

    def test_describe_result_includes_connection_id(self):
        payload = self.payload(operation="describe_table")
        payload["table"] = "users"
        result = self.gateway.execute(payload)
        self.assertEqual(result["connection_id"], "erp-ro")
        self.assertEqual(result["table"], "users")

    def test_unknown_disabled_ungranted_deleted_secret_share_one_error(self):
        cases = ["unknown-ro", "reporting-ro"]
        for connection_id in cases:
            with self.subTest(connection_id=connection_id):
                with self.assertRaises(ConnectionUnavailableError) as raised:
                    self.gateway.execute(self.payload(connection_id))
                self.assertEqual(str(raised.exception), UNAVAILABLE_MESSAGE)
        secrets = json.loads((self.config / "secrets.json").read_text())
        secrets["secrets"].pop("erp-ro")
        atomic_write_json(self.config / "secrets.json", secrets, secret=True)
        with self.assertRaises(ConnectionUnavailableError) as raised:
            self.gateway.execute(self.payload())
        self.assertEqual(str(raised.exception), UNAVAILABLE_MESSAGE)

    def test_project_root_mismatch_and_access_path_tampering_fail_closed(self):
        payload = self.payload()
        payload["project_root"] = str(self.root / "other")
        with self.assertRaises(ConnectionUnavailableError):
            self.gateway.execute(payload)
        projects = json.loads((self.config / "projects.json").read_text())
        projects["projects"][self.project_id]["access_path"] = str(self.root / "forged.json")
        atomic_write_json(self.config / "projects.json", projects)
        with self.assertRaises(ConnectionUnavailableError):
            self.gateway.execute(self.payload())

    def test_hot_config_update_is_visible_without_gateway_restart(self):
        connections = json.loads((self.config / "connections.json").read_text())
        connections["connections"]["erp-ro"]["database"] = "updated"
        atomic_write_json(self.config / "connections.json", connections)
        result = self.gateway.execute(self.payload(operation="list_databases"))
        self.assertEqual(result[0]["database"], "updated")

    def test_corrupt_central_config_refuses_new_requests(self):
        (self.config / "projects.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(ConfigError):
            self.gateway.execute(self.payload())


class HttpTests(unittest.TestCase):
    def start_server(self, gateway: object):
        server = MetadataHttpServer(
            ("127.0.0.1", 0),
            gateway,
            instance_token="test-token",
            installation_id="installation-id",
            process_identity="process-id",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(lambda: thread.join(timeout=5))
        self.addCleanup(server.shutdown)
        return server, thread

    def request(self, server, method, path, body=None, token="test-token"):
        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        headers = {"X-Database-Schema-Bootstrap-Token": token}
        if body is not None:
            headers["Content-Type"] = "application/json"
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        connection.close()
        return response.status, data

    def test_health_is_token_protected_and_does_not_touch_gateway(self):
        class ExplodingGateway:
            def execute(self, payload):
                raise AssertionError("health must not execute metadata")

        server, _ = self.start_server(ExplodingGateway())
        status, _ = self.request(server, "GET", "/v2/health", token="wrong")
        self.assertEqual(status, 403)
        status, body = self.request(server, "GET", "/v2/health")
        self.assertEqual(status, 200)
        self.assertEqual(body["protocol_version"], 2)
        self.assertEqual(body["installation_id"], "installation-id")
        self.assertEqual(body["process_identity"], "process-id")

    def test_metadata_size_policy_and_error_redaction(self):
        class Gateway:
            def execute(self, payload):
                raise ConnectionUnavailableError("secret-value should never surface")

        server, _ = self.start_server(Gateway())
        status, body = self.request(
            server, "POST", "/v2/metadata", body=b'{"version":2}'
        )
        self.assertEqual(status, 403)
        self.assertEqual(body["error"], "Current project connection is unavailable.")
        self.assertNotIn("secret-value", json.dumps(body))

        connection = http.client.HTTPConnection(
            "127.0.0.1", server.server_address[1], timeout=5
        )
        connection.request(
            "POST",
            "/v2/metadata",
            body=b"x" * (MAX_REQUEST_BYTES + 1),
            headers={"X-Database-Schema-Bootstrap-Token": "test-token"},
        )
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 400)

    def test_graceful_shutdown_requires_exact_body_and_token(self):
        class Gateway:
            def execute(self, payload):
                return []

        server, thread = self.start_server(Gateway())
        status, _ = self.request(
            server, "POST", "/v2/control/shutdown", body=b"{}"
        )
        self.assertEqual(status, 400)
        status, body = self.request(
            server, "POST", "/v2/control/shutdown", body=b'{"version":2}'
        )
        self.assertEqual(status, 200)
        self.assertTrue(body["stopping"])
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())

    def test_client_validates_health_identity_and_v2_metadata(self):
        class Gateway:
            def execute(self, payload):
                return [{"connection_id": payload["connection_id"], "table": "users"}]

        server, _ = self.start_server(Gateway())
        endpoint = f"http://127.0.0.1:{server.server_address[1]}"
        client = MetadataServiceClient(endpoint, instance_token="test-token")
        health = client.health(
            expected_installation_id="installation-id",
            expected_process_identity="process-id",
            expected_pid=os.getpid(),
        )
        self.assertEqual(health["version"], 2)
        result = client.metadata(
            {
                "version": 2,
                "project_id": "p",
                "project_root": "/p",
                "connection_id": "erp-ro",
                "operation": "list_tables",
            }
        )
        self.assertEqual(result[0]["connection_id"], "erp-ro")
        with self.assertRaises(MetadataServiceError):
            client.health(
                expected_installation_id="wrong",
                expected_process_identity="process-id",
                expected_pid=os.getpid(),
            )


class RuntimeStateTests(unittest.TestCase):
    def test_ready_state_is_v2_atomic_and_token_identity_owned(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = pathlib.Path(temporary) / "state" / "service.json"
            write_ready_state(
                path,
                endpoint="http://127.0.0.1:41001",
                port=41001,
                installation_id="installation-id",
                instance_token="token-a",
                process_identity="process-a",
            )
            data = json.loads(path.read_text())
            self.assertEqual(data["version"], 2)
            remove_ready_state_if_owned(
                path, instance_token="token-a", process_identity="wrong"
            )
            self.assertTrue(path.exists())
            remove_ready_state_if_owned(
                path, instance_token="token-a", process_identity="process-a"
            )
            self.assertFalse(path.exists())


class AdapterRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        (self.runtime / "state").mkdir(parents=True)
        self.project = self.root / "project"
        self.project.mkdir()
        self.project_id = "22222222-2222-4222-8222-222222222222"
        access_path = self.project / ACCESS_RELATIVE_PATH
        access_path.parent.mkdir(parents=True)
        atomic_write_json(
            access_path,
            access_document(
                AccessConfig(
                    self.project_id,
                    {"erp-ro": True, "reporting-ro": True},
                    "erp-ro",
                )
            ),
        )
        self.installation_id = "installation-id"
        atomic_write_json(
            self.runtime / "install-state.json",
            {
                "version": 2,
                "installation_id": self.installation_id,
                "runtime_root": str(self.runtime),
                "config_path": str(self.root / "config.toml"),
                "config_block_hash": "hash",
                "python_path": sys.executable,
                "dependency_installation": "completed",
                "managed_files": [],
                "managed_trees": [],
                "installed_at": "now",
            },
        )
        self.payloads: list[dict[str, object]] = []
        self.health_calls: list[str] = []

        payloads = self.payloads
        health_calls = self.health_calls

        class FakeClient:
            def __init__(inner, endpoint, *, instance_token, timeout):
                inner.endpoint = endpoint

            def health(
                inner,
                *,
                expected_installation_id,
                expected_process_identity,
                expected_pid,
            ):
                health_calls.append(expected_process_identity)
                return {"ok": True}

            def metadata(inner, payload):
                payloads.append(payload)
                return [{"connection_id": payload["connection_id"]}]

        self.client_factory = FakeClient

    def write_state(self):
        atomic_write_json(
            self.runtime / "state" / "service.json",
            {
                "version": 2,
                "protocol_version": 2,
                "installation_id": self.installation_id,
                "endpoint": "http://127.0.0.1:41001",
                "port": 41001,
                "pid": 123,
                "instance_token": "token",
                "process_identity": "process-id",
                "started_at": "now",
            },
        )

    def router(self, ensure_runner=None):
        return ProjectMetadataRouter(
            self.runtime,
            project_root_resolver=lambda: self.project,
            client_factory=self.client_factory,
            ensure_runner=ensure_runner,
        )

    def test_active_and_explicit_connection_are_forwarded_with_project_identity(self):
        self.write_state()
        self.router().list_tables()
        self.router().list_databases("reporting-ro")
        self.assertEqual(self.payloads[0]["connection_id"], "erp-ro")
        self.assertEqual(self.payloads[1]["connection_id"], "reporting-ro")
        self.assertEqual(self.payloads[0]["project_id"], self.project_id)
        self.assertNotIn("password", json.dumps(self.payloads))

    def test_disabled_or_unknown_explicit_connection_fails_before_http(self):
        access_path = self.project / ACCESS_RELATIVE_PATH
        atomic_write_json(
            access_path,
            access_document(
                AccessConfig(self.project_id, {"erp-ro": False}, None)
            ),
        )
        self.write_state()
        with self.assertRaises(ProjectRoutingError):
            self.router().list_tables("erp-ro")
        self.assertEqual(self.payloads, [])

    def test_missing_state_runs_ensure_once_then_reloads_state(self):
        calls: list[str] = []

        def ensure(project_root: str, timeout: float):
            calls.append(project_root)
            self.write_state()

        result = self.router(ensure_runner=ensure).list_tables()
        self.assertEqual(result, [{"connection_id": "erp-ro"}])
        self.assertEqual(calls, [os.path.normcase(os.path.abspath(self.project))])

    def test_incomplete_runtime_fails_without_ensure(self):
        state = json.loads((self.runtime / "install-state.json").read_text())
        state["dependency_installation"] = "incomplete"
        atomic_write_json(self.runtime / "install-state.json", state)
        calls: list[str] = []
        with self.assertRaises(ProjectRoutingError):
            self.router(ensure_runner=lambda *_: calls.append("ensure")).list_tables()
        self.assertEqual(calls, [])

    def test_adapter_source_has_no_service_psycopg_or_central_secret_import(self):
        sources = "\n".join(
            (SKILL_ROOT / name).read_text(encoding="utf-8")
            for name in ("mcp_server.py", "project_routing.py", "rpc_client.py")
        )
        self.assertNotIn("import psycopg", sources)
        self.assertNotIn("from service", sources)
        self.assertNotIn("secrets.json", sources)
        self.assertNotIn("connections.json", sources)
        self.assertNotIn("projects.json", sources)


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    @unittest.skipIf(Client is None, "MCP SDK test client is unavailable in this interpreter")
    async def test_exact_three_tools_accept_optional_connection_id(self):
        class FakeClient:
            def list_databases(self, connection_id=None):
                return [{"connection_id": connection_id or "active", "database": "app"}]

            def list_tables(self, connection_id=None):
                return [{"connection_id": connection_id or "active", "table": "users"}]

            def describe_table(self, table, connection_id=None):
                return {"connection_id": connection_id or "active", "table": table}

        server = create_server(FakeClient())
        async with Client(server) as client:
            tools = await client.list_tools()
            result = await client.call_tool(
                "describe_table",
                {"table": "users", "connection_id": "erp-ro"},
            )
        self.assertEqual(
            {tool.name for tool in tools.tools},
            {"list_databases", "list_tables", "describe_table"},
        )
        self.assertNotIn("execute_sql", repr(tools))
        self.assertIn("erp-ro", repr(result))


class FakeGatewayE2ETests(unittest.TestCase):
    def test_one_gateway_routes_two_git_projects_without_crossing_connections(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = pathlib.Path(temporary)
            runtime = root / "runtime"
            (runtime / "state").mkdir(parents=True)
            installation_id = "e2e-installation"
            atomic_write_json(
                runtime / "install-state.json",
                {
                    "version": 2,
                    "installation_id": installation_id,
                    "runtime_root": str(runtime),
                    "config_path": str(root / "config.toml"),
                    "config_block_hash": "hash",
                    "python_path": sys.executable,
                    "dependency_installation": "completed",
                    "managed_files": [],
                    "managed_trees": [],
                    "installed_at": "now",
                },
            )
            project_a = make_git_project(root, "project-a")
            project_b = make_git_project(root, "project-b")
            project_a_id = "44444444-4444-4444-8444-444444444444"
            project_b_id = "55555555-5555-4555-8555-555555555555"
            for project, project_id, connection_id in (
                (project_a, project_a_id, "project-a-ro"),
                (project_b, project_b_id, "project-b-ro"),
            ):
                access_path = project / ACCESS_RELATIVE_PATH
                access_path.parent.mkdir(parents=True)
                atomic_write_json(
                    access_path,
                    access_document(
                        AccessConfig(
                            project_id,
                            {connection_id: True},
                            connection_id,
                        )
                    ),
                )
            gateway = FakeGatewayServer(
                installation_id=installation_id,
                instance_token="e2e-token",
                process_identity="e2e-process",
                routes={
                    (project_a_id, "project-a-ro"): "project_a_table",
                    (project_b_id, "project-b-ro"): "project_b_table",
                },
            )
            thread = threading.Thread(target=gateway.serve_forever, daemon=True)
            thread.start()
            try:
                port = gateway.server_address[1]
                atomic_write_json(
                    runtime / "state" / "service.json",
                    {
                        "version": 2,
                        "protocol_version": 2,
                        "installation_id": installation_id,
                        "endpoint": f"http://127.0.0.1:{port}",
                        "port": port,
                        "pid": os.getpid(),
                        "instance_token": "e2e-token",
                        "process_identity": "e2e-process",
                        "started_at": "now",
                    },
                )
                router_a = ProjectMetadataRouter(
                    runtime,
                    project_root_resolver=lambda: project_a,
                    ensure_runner=lambda *_: self.fail("gateway should be reused"),
                )
                router_b = ProjectMetadataRouter(
                    runtime,
                    project_root_resolver=lambda: project_b,
                    ensure_runner=lambda *_: self.fail("gateway should be reused"),
                )
                self.assertEqual(router_a.list_tables()[0]["table"], "project_a_table")
                self.assertEqual(router_b.list_tables()[0]["table"], "project_b_table")
                with self.assertRaises(ProjectRoutingError):
                    router_a.list_tables("project-b-ro")
            finally:
                gateway.shutdown()
                gateway.server_close()
                thread.join(timeout=5)


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.runtime = self.root / "runtime"
        self.control = Control(self.runtime)
        self.project = make_git_project(self.root)

    def add_connection(self, connection_id="erp-ro", password="secret-value"):
        self.control.connection_add(
            connection_id,
            host="db.example.test",
            port=5432,
            database="app",
            connection_database="postgres",
            schema="public",
            user="metadata_reader",
            password=password,
        )

    def test_connection_password_is_separate_and_outputs_are_redacted(self):
        self.add_connection()
        connection_text = (self.runtime / "config" / "connections.json").read_text()
        secret_text = (self.runtime / "config" / "secrets.json").read_text()
        self.assertNotIn("secret-value", connection_text)
        self.assertIn("secret-value", secret_text)
        self.assertNotIn("secret-value", json.dumps(self.control.connection_list()))
        self.assertEqual(self.control.connection_show("erp-ro")["password"], "<redacted>")

    def test_connection_remove_requires_all_project_grants_revoked(self):
        self.add_connection()
        self.control.project_init(str(self.project))
        self.control.project_grant(str(self.project), "erp-ro")
        with self.assertRaises(ControlError):
            self.control.connection_remove("erp-ro")
        self.control.project_revoke(str(self.project), "erp-ro")
        self.control.connection_remove("erp-ro")
        self.assertEqual(self.control.connection_list(), [])

    def test_project_lifecycle_preserves_enabled_active_invariants_and_exclude(self):
        self.add_connection("erp-ro")
        self.add_connection("reporting-ro", "report-secret")
        initialized = self.control.project_init(str(self.project))
        access_path = self.project / ACCESS_RELATIVE_PATH
        exclude = pathlib.Path(
            subprocess.run(
                ["git", "-C", str(self.project), "rev-parse", "--git-path", "info/exclude"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        if not exclude.is_absolute():
            exclude = self.project / exclude
        self.assertTrue(access_path.exists())
        self.assertIn(EXCLUDE_START, exclude.read_text())

        access = self.control.project_grant(str(self.project), "erp-ro")
        self.assertFalse(access.connections["erp-ro"])
        access = self.control.project_enable(str(self.project), "erp-ro")
        self.assertEqual(access.active, "erp-ro")
        self.control.project_grant(str(self.project), "reporting-ro")
        self.control.project_enable(str(self.project), "reporting-ro")
        access = self.control.project_use(str(self.project), "reporting-ro")
        self.assertEqual(access.active, "reporting-ro")
        access = self.control.project_disable(str(self.project), "reporting-ro")
        self.assertIsNone(access.active)
        access = self.control.project_revoke(str(self.project), "reporting-ro")
        self.assertNotIn("reporting-ro", access.connections)

        project_id = initialized.project_id
        self.assertEqual(self.control.project_remove(str(self.project)), project_id)
        self.assertFalse(access_path.exists())
        self.assertNotIn(EXCLUDE_START, exclude.read_text())

    def test_exclude_marker_is_idempotent_and_edited_marker_fails_closed(self):
        first = add_exclude_marker("# user rule\n")
        self.assertEqual(add_exclude_marker(first), first)
        self.assertNotIn(EXCLUDE_START, remove_exclude_marker(first))
        with self.assertRaises(ControlError):
            remove_exclude_marker(f"{EXCLUDE_START}\nchanged\n{EXCLUDE_END}\n")

    def test_rebind_requires_confirmation_while_old_root_exists(self):
        initialized = self.control.project_init(str(self.project))
        new_root = make_git_project(self.root, "new-project")
        new_access = new_root / ACCESS_RELATIVE_PATH
        new_access.parent.mkdir(parents=True)
        atomic_write_json(new_access, access_document(initialized))
        with self.assertRaises(ControlError):
            self.control.project_rebind(str(new_root))
        rebound = self.control.project_rebind(
            str(new_root), confirm_old_root=True
        )
        self.assertEqual(rebound.root, os.path.normcase(os.path.abspath(new_root)))

    def test_shared_worktree_exclude_marker_is_removed_only_after_last_project(self):
        subprocess.run(
            [
                "git",
                "-C",
                str(self.project),
                "-c",
                "user.name=database-schema-bootstrap-test",
                "-c",
                "user.email=test@example.invalid",
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                "fixture",
            ],
            check=True,
        )
        worktree = self.root / "project-worktree"
        subprocess.run(
            [
                "git",
                "-C",
                str(self.project),
                "worktree",
                "add",
                "-q",
                "--detach",
                str(worktree),
            ],
            check=True,
        )
        first = self.control.project_init(str(self.project))
        second = self.control.project_init(str(worktree))
        exclude = pathlib.Path(
            subprocess.run(
                [
                    "git",
                    "-C",
                    str(self.project),
                    "rev-parse",
                    "--path-format=absolute",
                    "--git-path",
                    "info/exclude",
                ],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
        )
        self.assertIn(EXCLUDE_START, exclude.read_text(encoding="utf-8"))

        self.assertEqual(self.control.project_remove(str(self.project)), first.project_id)
        self.assertIn(EXCLUDE_START, exclude.read_text(encoding="utf-8"))
        self.assertEqual(self.control.project_remove(str(worktree)), second.project_id)
        self.assertNotIn(EXCLUDE_START, exclude.read_text(encoding="utf-8"))

    def test_concurrent_service_ensure_lock_starts_only_once(self):
        counter = 0
        counter_lock = threading.Lock()

        class FakeControl(Control):
            def read_install_state(inner):
                return {
                    "version": 2,
                    "installation_id": "id",
                    "dependency_installation": "completed",
                }

            def _read_service_state(inner):
                state_path = inner.state_root / "service.json"
                if state_path.exists():
                    return {
                        "version": 2,
                        "protocol_version": 2,
                        "installation_id": "id",
                        "endpoint": "http://127.0.0.1:41001",
                        "port": 41001,
                        "pid": os.getpid(),
                        "instance_token": "token",
                        "process_identity": "process",
                        "started_at": "now",
                    }
                return None

            def _healthy_client(inner, state, installation_id, timeout=2.0):
                return object()

            def _start_service(inner, installation_id):
                nonlocal counter
                with counter_lock:
                    counter += 1
                time.sleep(0.1)
                atomic_write_json(
                    inner.state_root / "service.json",
                    {
                        "version": 2,
                        "protocol_version": 2,
                        "installation_id": "id",
                        "endpoint": "http://127.0.0.1:41001",
                        "port": 41001,
                        "pid": os.getpid(),
                        "instance_token": "token",
                        "process_identity": "process",
                        "started_at": "now",
                    },
                )
                return {"status": "running"}

            def service_status(inner):
                return {"status": "running"}

        fake = FakeControl(self.runtime)
        results: list[dict[str, object]] = []
        threads = [
            threading.Thread(target=lambda: results.append(fake.service_ensure()))
            for _ in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertEqual(counter, 1)
        self.assertEqual(len(results), 4)

    def test_hook_without_access_or_enabled_connection_skips_service(self):
        class FakeControl(Control):
            def _start_service(self, installation_id):
                raise AssertionError("hook must not start")

        fake = FakeControl(self.runtime)
        result = fake.service_ensure(project_root=str(self.project), hook=True)
        self.assertEqual(result["status"], "skipped")


class InstallerAndUninstallerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = pathlib.Path(self.temporary.name)
        self.codex_home = self.root / "codex-home"

    def installer(self):
        return Installer(
            repo_root=ROOT,
            codex_home=self.codex_home,
            python=pathlib.Path(sys.executable),
            skip_dependency_install=True,
        )

    def test_managed_block_uses_dedicated_venv_three_tools_and_no_session_end(self):
        runtime = self.codex_home / "database-schema-bootstrap"
        block = managed_config_block("11111111-1111-4111-8111-111111111111", runtime, venv_python(runtime))
        self.assertIn(str(venv_python(runtime)), block)
        self.assertIn('enabled_tools = ["list_databases", "list_tables", "describe_table"]', block)
        self.assertIn("[[hooks.SessionStart]]", block)
        self.assertNotIn("SessionEnd", block)
        content = replace_managed_config("user_setting = true\n", block)
        installation_id, parsed = inspect_managed_config(content)
        self.assertEqual(installation_id, "11111111-1111-4111-8111-111111111111")
        self.assertEqual(parsed, block)

    def test_legacy_v1_uninstaller_keeps_credentials_before_core_mutation(self):
        source = (
            CONTROL_ROOT / "legacy-uninstall-v1.ps1"
        ).read_text(encoding="utf-8-sig")
        credential_delete = source.index(
            "Remove-DsbWindowsCredential -Target $credentialItem.Target"
        )
        service_stop = source.index(
            "Stop-DsbRecordedProjectServices -RuntimeRoot $effectiveRuntimeRoot"
        )
        config_delete = source.index(
            "Write-DsbAtomicUtf8File -Path $configItem.Target",
            credential_delete,
        )
        self.assertLess(credential_delete, service_stop)
        self.assertLess(credential_delete, config_delete)

    def test_skip_install_creates_dedicated_incomplete_runtime_and_preserves_user_config(self):
        self.codex_home.mkdir()
        (self.codex_home / "config.toml").write_text("user_setting = true\n")
        runtime = self.installer().install()
        state = json.loads((runtime / "install-state.json").read_text())
        self.assertEqual(state["dependency_installation"], "incomplete")
        self.assertTrue(venv_python(runtime).is_file())
        self.assertIn("user_setting = true", (self.codex_home / "config.toml").read_text())
        self.assertIn(str(venv_python(runtime)), (self.codex_home / "config.toml").read_text())
        result = subprocess.run(
            [
                str(venv_python(runtime)),
                "-B",
                str(runtime / "adapter" / "mcp_server.py"),
                "--runtime-root",
                str(runtime),
                "--self-check",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)

    def test_v1_state_or_marker_blocks_v2_without_mutation(self):
        runtime = self.codex_home / "database-schema-bootstrap"
        runtime.mkdir(parents=True)
        (runtime / "install-state.json").write_text('{"version":1}')
        with self.assertRaises(InstallError) as raised:
            self.installer().install()
        self.assertIn("legacy-uninstall-v1.ps1", str(raised.exception))
        self.assertEqual((runtime / "install-state.json").read_text(), '{"version":1}')

    def test_staging_failure_leaves_existing_v2_runtime_and_config_usable(self):
        runtime = self.installer().install()
        state_before = (runtime / "install-state.json").read_bytes()
        config_before = (self.codex_home / "config.toml").read_bytes()
        installer = self.installer()
        with mock.patch.object(
            installer, "_create_venv", side_effect=InstallError("staging failed")
        ):
            with self.assertRaises(InstallError):
                installer.install()
        self.assertEqual((runtime / "install-state.json").read_bytes(), state_before)
        self.assertEqual((self.codex_home / "config.toml").read_bytes(), config_before)

    def test_ordinary_uninstall_preserves_connection_data_and_all_removes_it(self):
        runtime = self.installer().install()
        connections = json.loads((runtime / "config" / "connections.json").read_text())
        connections["connections"]["erp-ro"] = connection_to_json(profile())
        atomic_write_json(runtime / "config" / "connections.json", connections)
        secrets = {"version": 2, "secrets": {"erp-ro": {"password": "secret-value"}}}
        atomic_write_json(runtime / "config" / "secrets.json", secrets, secret=True)

        report = Uninstaller(self.codex_home).uninstall(set(DEFAULT_CATEGORIES))
        self.assertTrue((runtime / "config" / "connections.json").exists())
        self.assertTrue((runtime / "config" / "secrets.json").exists())
        self.assertNotIn("database-schema-bootstrap v2 managed", (self.codex_home / "config.toml").read_text())
        self.assertTrue(report)

        Uninstaller(self.codex_home).uninstall(set(ALL_CATEGORIES))
        self.assertFalse(runtime.exists())

    def test_modified_managed_config_blocks_runtime_deletion(self):
        runtime = self.installer().install()
        config = self.codex_home / "config.toml"
        config.write_text(config.read_text().replace("tool_timeout_sec = 30", "tool_timeout_sec = 31"))
        with self.assertRaises(Exception):
            Uninstaller(self.codex_home).uninstall(set(DEFAULT_CATEGORIES))
        self.assertTrue(runtime.exists())

    def test_unverifiable_orphan_blocks_uninstall_before_any_mutation(self):
        runtime = self.installer().install()
        config_before = (self.codex_home / "config.toml").read_bytes()
        atomic_write_json(
            runtime / "state" / "orphans.json",
            {
                "version": 2,
                "orphans": [
                    {
                        "record_id": "fixture",
                        "pid": None,
                        "process_identity": None,
                        "reason": "state-invalid",
                        "observed_at": "fixture",
                        "unverifiable": True,
                    }
                ],
            },
            secret=True,
        )
        with self.assertRaises(UninstallError):
            Uninstaller(self.codex_home).uninstall(set(DEFAULT_CATEGORIES))
        self.assertEqual((self.codex_home / "config.toml").read_bytes(), config_before)
        self.assertTrue((runtime / "install-state.json").exists())


if __name__ == "__main__":
    unittest.main()
