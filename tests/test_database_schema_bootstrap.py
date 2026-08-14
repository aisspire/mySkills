from __future__ import annotations

import contextlib
import io
import json
import http.client
import os
import pathlib
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
SKILL_ROOT = ROOT / ".agents" / "skills" / "database-schema-bootstrap"
SERVICE_ROOT = ROOT / "mcp" / "database-schema-bootstrap"
for import_root in (SERVICE_ROOT, SKILL_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from mcp import Client  # noqa: E402
from mcp_server import create_server, parse_args  # noqa: E402
from rpc_client import MetadataServiceClient, MetadataServiceError  # noqa: E402
import server as service_entry  # noqa: E402
from service.config import PostgresProfile, load_profile  # noqa: E402
from service.errors import ConfigError, PolicyError  # noqa: E402
from service.http_server import MetadataHttpServer  # noqa: E402
from service.path_identity import canonical_project_root as service_canonical_project_root  # noqa: E402
from service.postgres_metadata import PostgresMetadataService  # noqa: E402
from service.protocol import dispatch_metadata  # noqa: E402


def profile_data(**overrides):
    data = {
        "db_type": "postgres",
        "host": "127.0.0.1",
        "port": 5432,
        "database": "app",
        "connection_database": "postgres",
        "schema": "public",
        "user": "readonly_metadata_user",
        "credential_target": "database-schema-bootstrap/test",
        "target_tables": ["users"],
    }
    data.update(overrides)
    return data


class FakeTransaction:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class FakeCursor:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple[str, object | None]] = []

    def execute(self, query, params=None):
        self.calls.append((query, params))

    def fetchall(self):
        return self.responses.pop(0)


class FakeConnection:
    def __init__(self, responses):
        self.cursor_instance = FakeCursor(responses)
        self.closed = False

    def transaction(self):
        return FakeTransaction()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        self.closed = True


class DatabaseSchemaBootstrapTests(unittest.TestCase):
    def write_profile(self, data):
        path = ROOT / "tests" / ".tmp-profile.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.addCleanup(lambda: path.unlink(missing_ok=True))
        return path

    def test_profile_loads_postgres_only_fields(self):
        profile = load_profile(self.write_profile(profile_data()))

        self.assertIsInstance(profile, PostgresProfile)
        self.assertEqual(profile.database, "app")
        self.assertEqual(profile.schema, "public")
        self.assertEqual(profile.target_tables, ("users",))

    def test_legacy_maintenance_database_is_supported_as_alias(self):
        data = profile_data()
        data.pop("connection_database")

        profile = load_profile(
            self.write_profile({**data, "maintenance_database": "postgres"})
        )

        self.assertEqual(profile.connection_database, "postgres")

    def test_plaintext_password_is_rejected_without_echoing_value(self):
        with self.assertRaises(ConfigError) as raised:
            load_profile(self.write_profile(profile_data(password="secret-value")))

        self.assertNotIn("secret-value", str(raised.exception))
        self.assertIn("credential_target", str(raised.exception))

    def test_dsn_and_non_postgres_profiles_are_rejected(self):
        with self.assertRaises(ConfigError):
            load_profile(self.write_profile(profile_data(dsn="postgresql://user@host/app")))
        with self.assertRaises(ConfigError):
            load_profile(self.write_profile(profile_data(db_type="mysql")))
        with self.assertRaises(ConfigError):
            load_profile(self.write_profile(profile_data(sqlite_path="data.db")))

    def test_metadata_service_reads_password_only_for_driver_connection(self):
        profile = load_profile(self.write_profile(profile_data()))
        connection = FakeConnection([[('app',)]])
        captured = {}

        def connect_factory(**kwargs):
            captured.update(kwargs)
            return connection

        service = PostgresMetadataService(
            profile,
            credential_reader=lambda _: "secret-value",
            connect_factory=connect_factory,
        )

        result = service.list_databases()

        self.assertEqual(result, [{"database": "app"}])
        self.assertEqual(captured["password"], "secret-value")
        self.assertNotIn("secret-value", json.dumps(result))
        self.assertTrue(connection.closed)
        self.assertIn("SET TRANSACTION READ ONLY", connection.cursor_instance.calls[0][0])

    def test_list_tables_uses_configured_schema_and_returns_metadata_only(self):
        profile = load_profile(self.write_profile(profile_data()))
        connection = FakeConnection([[('public', 'users')]])
        service = PostgresMetadataService(
            profile,
            credential_reader=lambda _: "secret-value",
            connect_factory=lambda **_: connection,
        )

        result = service.list_tables()

        self.assertEqual(result, [{"schema": "public", "table": "users"}])
        query, params = connection.cursor_instance.calls[1]
        self.assertIn("information_schema.tables", query)
        self.assertEqual(params, ("public",))
        self.assertNotIn("SELECT *", query.upper())

    def test_describe_table_returns_columns_constraints_and_indexes(self):
        profile = load_profile(self.write_profile(profile_data()))
        connection = FakeConnection(
            [
                [("id", "bigint", "NO", None)],
                [("users_pkey", "PRIMARY KEY", "id")],
                [("users_pkey", True, True, True, "btree", "CREATE UNIQUE INDEX users_pkey", None)],
            ]
        )
        service = PostgresMetadataService(
            profile,
            credential_reader=lambda _: "secret-value",
            connect_factory=lambda **_: connection,
        )

        result = service.describe_table("users")

        self.assertEqual(result["table"], "users")
        self.assertEqual(result["columns"][0]["name"], "id")
        self.assertEqual(result["constraints"][0]["type"], "PRIMARY KEY")
        self.assertTrue(result["indexes"][0]["primary"])
        self.assertNotIn("secret-value", json.dumps(result))
        constraint_query, constraint_params = connection.cursor_instance.calls[2]
        self.assertIn("tc.constraint_schema = kcu.constraint_schema", constraint_query)
        self.assertIn("tc.table_name = kcu.table_name", constraint_query)
        self.assertEqual(constraint_params, ("public", "users"))

    def test_invalid_table_name_is_rejected_before_connection(self):
        profile = load_profile(self.write_profile(profile_data()))
        connect = mock.Mock()
        service = PostgresMetadataService(
            profile,
            credential_reader=lambda _: "secret-value",
            connect_factory=connect,
        )

        with self.assertRaises(PolicyError):
            service.describe_table("users; SELECT 1")

        connect.assert_not_called()

    def test_rpc_protocol_has_no_sql_escape_hatch(self):
        class FakeService:
            def list_databases(self):
                return [{"database": "app"}]

            def list_tables(self):
                return [{"schema": "public", "table": "users"}]

            def describe_table(self, table):
                return {"table": table}

        service = FakeService()
        self.assertEqual(
            dispatch_metadata(service, {"operation": "list_tables"}),
            [{"schema": "public", "table": "users"}],
        )
        with self.assertRaises(PolicyError):
            dispatch_metadata(service, {"operation": "execute_sql", "sql": "SELECT 1"})
        with self.assertRaises(PolicyError):
            dispatch_metadata(
                service,
                {"operation": "list_tables", "password": "secret-value"},
            )

    def test_adapter_source_has_no_database_or_credential_access(self):
        adapter_source = (SKILL_ROOT / "mcp_server.py").read_text(encoding="utf-8")
        rpc_source = (SKILL_ROOT / "rpc_client.py").read_text(encoding="utf-8")
        routing_source = (SKILL_ROOT / "project_routing.py").read_text(encoding="utf-8")

        combined = f"{adapter_source}\n{rpc_source}\n{routing_source}"
        self.assertNotIn("psycopg", combined)
        self.assertNotIn("CredRead", combined)
        self.assertNotIn("load_profile", combined)
        self.assertNotIn("password=", combined)

    def test_service_entry_is_separate_from_mcp_adapter(self):
        self.assertTrue((SERVICE_ROOT / "server.py").exists())
        self.assertTrue((SERVICE_ROOT / "service" / "postgres_metadata.py").exists())
        self.assertFalse((SKILL_ROOT / "gateway").exists())
        self.assertFalse((SKILL_ROOT / "scripts" / "inspect_schema.py").exists())

    def test_client_sends_only_fixed_rpc_fields(self):
        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc_value, traceback):
                return False

            def read(self, limit):
                return b'{"ok":true,"result":[{"schema":"public","table":"users"}]}'

        with mock.patch("urllib.request.urlopen", return_value=FakeResponse()) as opened:
            result = MetadataServiceClient("http://127.0.0.1:8765").list_tables()

        request = opened.call_args.args[0]
        self.assertEqual(
            json.loads(request.data),
            {"operation": "list_tables"},
        )
        self.assertEqual(result, [{"schema": "public", "table": "users"}])

    def test_client_rejects_endpoint_credentials(self):
        with self.assertRaises(MetadataServiceError) as raised:
            MetadataServiceClient("http://user:secret-value@127.0.0.1:8765")
        self.assertNotIn("secret-value", str(raised.exception))
        with self.assertRaises(MetadataServiceError):
            MetadataServiceClient("http://localhost:8765")

    def test_old_direct_cli_is_removed(self):
        self.assertFalse((SKILL_ROOT / "scripts" / "inspect_schema.py").exists())

    def test_project_identity_is_lexical_and_shared_with_service(self):
        from project_routing import (  # noqa: PLC0415
            canonical_project_root,
            project_id_for_root,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = pathlib.Path(temporary_directory)
            target = temporary_root / "target-project"
            target.mkdir()
            junction = temporary_root / "junction-project"
            result = subprocess.run(
                [
                    "cmd.exe",
                    "/c",
                    f'mklink /J "{junction}" "{target}"',
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                self.skipTest(
                    "junction creation is unavailable: "
                    + (result.stderr or result.stdout).strip()
                )
            self.addCleanup(lambda: os.rmdir(junction) if junction.exists() else None)

            lexical_path = canonical_project_root(junction / ".")
            self.assertEqual(lexical_path, service_canonical_project_root(junction / "."))
            self.assertEqual(
                project_id_for_root(junction),
                project_id_for_root(lexical_path),
            )
            self.assertNotEqual(lexical_path, canonical_project_root(target))
            self.assertNotEqual(lexical_path, os.path.normcase(os.path.realpath(junction)))

    def test_service_state_writer_uses_lexical_project_identity(self):
        from project_routing import canonical_project_root  # noqa: PLC0415

        self.assertNotIn(".resolve()", (SERVICE_ROOT / "server.py").read_text(encoding="utf-8"))
        self.assertEqual(
            service_canonical_project_root(ROOT / "."),
            canonical_project_root(ROOT / "."),
        )

    def test_project_identity_preserves_symlink_spelling_when_available(self):
        from project_routing import canonical_project_root  # noqa: PLC0415

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = pathlib.Path(temporary_directory)
            target = temporary_root / "target-project"
            target.mkdir()
            symlink = temporary_root / "symlink-project"
            try:
                os.symlink(target, symlink, target_is_directory=True)
            except (OSError, NotImplementedError) as exc:
                self.skipTest(f"directory symlink creation is unavailable: {exc}")
            self.addCleanup(lambda: symlink.unlink(missing_ok=True))

            lexical_path = canonical_project_root(symlink / ".")
            self.assertEqual(lexical_path, service_canonical_project_root(symlink / "."))
            self.assertNotEqual(lexical_path, canonical_project_root(target))
            self.assertNotEqual(lexical_path, os.path.normcase(os.path.realpath(symlink)))

    def test_project_router_uses_current_project_state_on_every_call(self):
        from project_routing import (  # noqa: PLC0415
            ProjectMetadataRouter,
            ProjectRoutingError,
            project_id_for_root,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_root = pathlib.Path(temporary_directory)
            project_a = temporary_root / "project-a"
            project_b = temporary_root / "project-b"
            state_root = temporary_root / "state" / "projects"
            project_a.mkdir()
            project_b.mkdir()
            state_root.mkdir(parents=True)

            def write_state(project_root: pathlib.Path, endpoint: str, token: str):
                project_id = project_id_for_root(project_root)
                (state_root / f"{project_id}.json").write_text(
                    json.dumps(
                        {
                            "version": 1,
                            "project_id": project_id,
                            "project_root": str(project_root.resolve()),
                            "endpoint": endpoint,
                            "port": int(endpoint.rsplit(":", 1)[1]),
                            "pid": 1,
                            "instance_token": token,
                        }
                    ),
                    encoding="utf-8",
                )

            write_state(project_a, "http://127.0.0.1:41001", "token-a")
            write_state(project_b, "http://127.0.0.1:41002", "token-b")
            current_project = [project_a]

            class FakeClient:
                def __init__(self, endpoint, *, instance_token, timeout):
                    self.endpoint = endpoint
                    self.instance_token = instance_token
                    self.timeout = timeout

                def health(self, expected_project_id):
                    if self.instance_token == "invalid":
                        raise MetadataServiceError("Instance token mismatch.")
                    return {"ok": True, "project_id": expected_project_id}

                def list_databases(self):
                    return [{"database": self.endpoint}]

                def list_tables(self):
                    return [{"schema": "public", "table": self.instance_token}]

                def describe_table(self, table):
                    return {"table": table, "endpoint": self.endpoint}

            router = ProjectMetadataRouter(
                state_root,
                project_root_resolver=lambda: current_project[0],
                client_factory=FakeClient,
            )

            self.assertEqual(router.list_tables()[0]["table"], "token-a")
            current_project[0] = project_b
            self.assertEqual(router.list_tables()[0]["table"], "token-b")

            (state_root / f"{project_id_for_root(project_b)}.json").unlink()
            with self.assertRaises(ProjectRoutingError):
                router.list_tables()

            write_state(project_b, "http://127.0.0.1:41002", "invalid")
            with self.assertRaises(ProjectRoutingError):
                router.list_tables()

    def test_project_router_fails_closed_when_project_identity_is_unavailable(self):
        from project_routing import (  # noqa: PLC0415
            ProjectMetadataRouter,
            ProjectRoutingError,
        )

        with tempfile.TemporaryDirectory() as temporary_directory:
            router = ProjectMetadataRouter(
                pathlib.Path(temporary_directory) / "state" / "projects",
                project_root_resolver=lambda: (_ for _ in ()).throw(
                    ProjectRoutingError("Git identity is unavailable.")
                ),
            )

            with self.assertRaises(ProjectRoutingError):
                router.list_tables()

    def test_git_root_discovery_caps_git_timeout_to_remaining_budget(self):
        from project_routing import discover_git_project_root  # noqa: PLC0415

        completed = subprocess.CompletedProcess(
            args=["git"], returncode=0, stdout=str(ROOT), stderr=""
        )
        with mock.patch("project_routing.subprocess.run", return_value=completed) as run:
            root = discover_git_project_root(timeout=1.25)

        self.assertEqual(root, ROOT)
        self.assertEqual(run.call_args.kwargs["timeout"], 1.25)

    def test_project_router_uses_remaining_budget_for_health_then_metadata(self):
        from project_routing import (  # noqa: PLC0415
            ProjectMetadataRouter,
            project_id_for_root,
        )

        class FakeClock:
            def __init__(self):
                self.value = 100.0

            def __call__(self):
                return self.value

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = pathlib.Path(temporary_directory) / "project"
            state_root = pathlib.Path(temporary_directory) / "state" / "projects"
            project_root.mkdir()
            state_root.mkdir(parents=True)
            project_id = project_id_for_root(project_root)
            (state_root / f"{project_id}.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "project_id": project_id,
                        "project_root": str(project_root.resolve()),
                        "endpoint": "http://127.0.0.1:41001",
                        "port": 41001,
                        "pid": 1,
                        "instance_token": "token",
                    }
                ),
                encoding="utf-8",
            )
            clock = FakeClock()
            constructed_timeouts: list[float] = []
            health_project_ids: list[str] = []

            class FakeClient:
                def __init__(self, endpoint, *, instance_token, timeout):
                    self.endpoint = endpoint
                    self.instance_token = instance_token
                    self.timeout = timeout
                    constructed_timeouts.append(timeout)

                def health(self, expected_project_id):
                    health_project_ids.append(expected_project_id)
                    clock.value += 3.0
                    return {"ok": True, "project_id": expected_project_id}

                def list_tables(self):
                    return [{"schema": "public", "table": "budgeted"}]

            router = ProjectMetadataRouter(
                state_root,
                project_root_resolver=lambda: project_root,
                client_factory=FakeClient,
                timeout=5.0,
                clock=clock,
            )

            self.assertEqual(
                router.list_tables(), [{"schema": "public", "table": "budgeted"}]
            )
            self.assertEqual(constructed_timeouts, [5.0, 2.0])
            self.assertEqual(health_project_ids, [project_id])

    def test_project_router_fails_closed_when_health_consumes_total_budget(self):
        from project_routing import (  # noqa: PLC0415
            ProjectMetadataRouter,
            ProjectRoutingError,
            project_id_for_root,
        )

        class FakeClock:
            def __init__(self):
                self.value = 100.0

            def __call__(self):
                return self.value

        with tempfile.TemporaryDirectory() as temporary_directory:
            project_root = pathlib.Path(temporary_directory) / "project"
            state_root = pathlib.Path(temporary_directory) / "state" / "projects"
            project_root.mkdir()
            state_root.mkdir(parents=True)
            project_id = project_id_for_root(project_root)
            (state_root / f"{project_id}.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "project_id": project_id,
                        "project_root": str(project_root.resolve()),
                        "endpoint": "http://127.0.0.1:41001",
                        "port": 41001,
                        "pid": 1,
                        "instance_token": "token",
                    }
                ),
                encoding="utf-8",
            )
            clock = FakeClock()
            metadata_calls: list[str] = []

            class FakeClient:
                def __init__(self, endpoint, *, instance_token, timeout):
                    self.timeout = timeout

                def health(self, expected_project_id):
                    clock.value += 5.1
                    return {"ok": True, "project_id": expected_project_id}

                def list_tables(self):
                    metadata_calls.append("list_tables")
                    return []

            router = ProjectMetadataRouter(
                state_root,
                project_root_resolver=lambda: project_root,
                client_factory=FakeClient,
                timeout=5.0,
                clock=clock,
            )

            with self.assertRaises(ProjectRoutingError) as raised:
                router.list_tables()

            self.assertIn("timed out", str(raised.exception).lower())
            self.assertEqual(metadata_calls, [])


class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def test_server_exposes_exactly_three_metadata_tools(self):
        class FakeClient:
            def list_databases(self):
                return [{"database": "app"}]

            def list_tables(self):
                return [{"schema": "public", "table": "users"}]

            def describe_table(self, table):
                return {"engine": "postgres", "schema": "public", "table": table}

        server = create_server(FakeClient())

        async with Client(server) as client:
            tools_result = await client.list_tools()
            tool_names = {tool.name for tool in tools_result.tools}
            describe_result = await client.call_tool(
                "describe_table", {"table": "users"}
            )

        self.assertEqual(
            tool_names,
            {"list_databases", "list_tables", "describe_table"},
        )
        self.assertNotIn("execute_sql", tool_names)
        self.assertNotIn("query", tool_names)
        self.assertNotIn("secret-value", repr(describe_result))

    def test_invalid_endpoint_process_writes_only_to_stderr(self):
        server_path = SKILL_ROOT / "mcp_server.py"
        result = subprocess.run(
            [
                sys.executable,
                str(server_path),
                "--endpoint",
                "http://user:secret-value@127.0.0.1:8765",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("MCP adapter startup failed", result.stderr)
        self.assertNotIn("secret-value", result.stderr)

    def test_adapter_timeout_defaults_to_25_seconds_and_rejects_non_finite_values(self):
        self.assertEqual(parse_args([]).timeout, 25.0)

        for value in ("0", "-1", "nan", "inf"):
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit):
                    parse_args(["--timeout", value])


class MetadataHttpServerTests(unittest.TestCase):
    def test_health_endpoint_is_available_without_database_access(self):
        class ExplodingService:
            def list_databases(self):
                raise AssertionError("Health checks must not access PostgreSQL metadata.")

            def list_tables(self):
                raise AssertionError("Health checks must not access PostgreSQL metadata.")

            def describe_table(self, table):
                raise AssertionError("Health checks must not access PostgreSQL metadata.")

        server = MetadataHttpServer(("127.0.0.1", 0), ExplodingService())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            connection.request("GET", "/v1/health")
            response = connection.getresponse()
            body = json.loads(response.read().decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(response.status, 200)
        self.assertTrue(body["ok"])

    def test_http_server_binds_only_loopback_by_construction(self):
        class FakeService:
            def list_databases(self):
                return []

            def list_tables(self):
                return []

            def describe_table(self, table):
                return {"table": table}

        server = MetadataHttpServer(("127.0.0.1", 0), FakeService())
        try:
            self.assertEqual(server.server_address[0], "127.0.0.1")
        finally:
            server.server_close()

    def test_dynamic_port_ready_state_and_health_token_are_project_bound(self):
        class FakeService:
            def list_databases(self):
                return []

            def list_tables(self):
                return []

            def describe_table(self, table):
                return {"table": table}

        profile_path = ROOT / "tests" / ".tmp-ready-profile.json"
        profile_path.write_text(json.dumps(profile_data()), encoding="utf-8")
        self.addCleanup(lambda: profile_path.unlink(missing_ok=True))
        ready_path = ROOT / "tests" / ".tmp-ready-state.json"
        self.addCleanup(lambda: ready_path.unlink(missing_ok=True))

        with mock.patch.object(service_entry, "PostgresMetadataService", return_value=FakeService()):
            server = service_entry.build_server(
                str(profile_path),
                port=0,
                instance_token="test-instance-token",
                ready_state=str(ready_path),
                project_id="project-sha256",
                project_root=str(ROOT),
            )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            ready_state = json.loads(ready_path.read_text(encoding="utf-8"))
            self.assertEqual(ready_state["project_id"], "project-sha256")
            self.assertEqual(ready_state["instance_token"], "test-instance-token")
            self.assertEqual(ready_state["port"], server.server_address[1])

            rejected = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            rejected.request("GET", "/v1/health")
            self.assertEqual(rejected.getresponse().status, 403)

            accepted = http.client.HTTPConnection(
                "127.0.0.1", server.server_address[1], timeout=5
            )
            accepted.request(
                "GET",
                "/v1/health",
                headers={"X-Database-Schema-Bootstrap-Token": "test-instance-token"},
            )
            accepted_response = accepted.getresponse()
            accepted_body = json.loads(accepted_response.read().decode("utf-8"))
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(accepted_response.status, 200)
        self.assertEqual(accepted_body["project_id"], "project-sha256")

    def test_token_aware_client_checks_project_health_before_metadata_calls(self):
        class FakeService:
            def list_databases(self):
                return [{"database": "app"}]

            def list_tables(self):
                return [{"schema": "public", "table": "users"}]

            def describe_table(self, table):
                return {"table": table}

        server = MetadataHttpServer(
            ("127.0.0.1", 0),
            FakeService(),
            instance_token="verified-token",
            project_id="project-sha256",
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}"
            client = MetadataServiceClient(endpoint, instance_token="verified-token")
            self.assertEqual(client.health("project-sha256")["project_id"], "project-sha256")
            self.assertEqual(client.list_tables(), [{"schema": "public", "table": "users"}])
            with self.assertRaises(MetadataServiceError):
                MetadataServiceClient(endpoint, instance_token="wrong-token").health(
                    "project-sha256"
                )
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

    def test_rpc_client_and_service_protocol_work_end_to_end_without_database(self):
        class FakeService:
            def list_databases(self):
                return [{"database": "app"}]

            def list_tables(self):
                return [{"schema": "public", "table": "users"}]

            def describe_table(self, table):
                return {"table": table}

        server = MetadataHttpServer(("127.0.0.1", 0), FakeService())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            endpoint = f"http://127.0.0.1:{server.server_address[1]}"
            result = MetadataServiceClient(endpoint).list_tables()
        finally:
            server.shutdown()
            thread.join(timeout=5)
            server.server_close()

        self.assertEqual(result, [{"schema": "public", "table": "users"}])


if __name__ == "__main__":
    unittest.main()
