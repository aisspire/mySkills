from __future__ import annotations

import argparse
import ctypes
import json
import os
import pathlib
import re
import sqlite3
import sys
from ctypes import wintypes
from typing import Any
from urllib.parse import unquote, urlsplit


PLACEHOLDER_PREFIX = "__"
PLACEHOLDER_SUFFIX = "__"


class ConfigError(RuntimeError):
    pass


class DriverError(RuntimeError):
    pass


def parse_env_file(path: str | pathlib.Path) -> dict[str, str]:
    env_path = pathlib.Path(path)
    if not env_path.exists():
        raise ConfigError(f"Config file not found: {env_path}")

    values: dict[str, str] = {}
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        val = value.strip()
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        values[key.strip()] = val
    return values


def is_placeholder(value: Any | None) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return not text or (
        text.startswith(PLACEHOLDER_PREFIX) and text.endswith(PLACEHOLDER_SUFFIX)
    )


def merge_config(file_config: dict[str, str], environ: dict[str, str] | None = None) -> dict[str, str]:
    env = environ or os.environ
    merged = dict(file_config)
    for key, value in env.items():
        if key in merged and value.strip():
            merged[key] = value.strip()
    return merged


def load_postgres_driver():
    try:
        import psycopg  # type: ignore

        return "psycopg", psycopg
    except ImportError:
        try:
            import psycopg2  # type: ignore

            return "psycopg2", psycopg2
        except ImportError as exc:
            raise DriverError(
                "PostgreSQL driver not available. Install `psycopg[binary]` or `psycopg2-binary` "
                "in the Python environment that runs this script."
            ) from exc


def load_mysql_driver():
    try:
        import pymysql  # type: ignore

        return "pymysql", pymysql
    except ImportError:
        try:
            import mysql.connector  # type: ignore

            return "mysql.connector", mysql.connector
        except ImportError as exc:
            raise DriverError(
                "MySQL driver not available. Install `pymysql` or `mysql-connector-python` "
                "in the Python environment that runs this script."
            ) from exc


PROFILE_RELATIVE_PATH = pathlib.Path(
    ".agents/database-schema-bootstrap/profiles/default.json"
)
PLAINTEXT_SECRET_KEYS = {
    "password",
    "db_password",
    "db_pass",
    "pass",
    "secret",
}


def config_value(
    config: dict[str, Any],
    canonical_key: str,
    default: Any | None = None,
) -> Any:
    aliases = {
        "DB_TYPE": ("DB_TYPE", "db_type"),
        "DB_HOST": ("DB_HOST", "host"),
        "DB_PORT": ("DB_PORT", "port"),
        "DB_NAME": ("DB_NAME", "database", "db_name"),
        "DB_SCHEMA": ("DB_SCHEMA", "schema"),
        "DB_USER": ("DB_USER", "user", "username"),
        "DB_PASSWORD": ("DB_PASSWORD", "password"),
        "DB_DSN": ("DB_DSN", "dsn"),
        "SQLITE_PATH": ("SQLITE_PATH", "sqlite_path"),
        "TARGET_TABLES": ("TARGET_TABLES", "target_tables"),
        "CREDENTIAL_TARGET": ("CREDENTIAL_TARGET", "credential_target"),
        "CONNECTION_DATABASE": (
            "CONNECTION_DATABASE",
            "connection_database",
            "MAINTENANCE_DATABASE",
            "maintenance_database",
        ),
    }
    for key in aliases.get(canonical_key, (canonical_key,)):
        if key in config:
            value = config[key]
            if value is not None:
                return value
    return default


def normalize_db_type(value: Any | None) -> str:
    if value is None:
        return ""
    db_type = str(value).strip().lower()
    aliases = {
        "postgresql": "postgres",
        "mariadb": "mysql",
    }
    return aliases.get(db_type, db_type)


def default_project_config_path(
    project_root: str | pathlib.Path | None = None,
) -> pathlib.Path:
    root = pathlib.Path(project_root) if project_root is not None else pathlib.Path.cwd()
    return root / PROFILE_RELATIVE_PATH


def dsn_contains_plaintext_password(value: Any) -> bool:
    text = str(value).strip()
    if not text:
        return False
    if re.search(r"(?i)(password|pwd)\s*=\s*[^;\s]+", text):
        return True
    try:
        parsed = urlsplit(text)
    except ValueError:
        return False
    return parsed.password is not None


def dsn_database_name(value: Any) -> str | None:
    try:
        parsed = urlsplit(str(value).strip())
    except ValueError:
        return None
    database_name = parsed.path.lstrip("/").split("/", 1)[0]
    if not database_name:
        return None
    return unquote(database_name)


def dsn_username(value: Any) -> str | None:
    try:
        parsed = urlsplit(str(value).strip())
    except ValueError:
        return None
    if parsed.username is None:
        return None
    return unquote(parsed.username)


def ensure_dsn_has_no_plaintext_password(value: Any) -> None:
    if dsn_contains_plaintext_password(value):
        raise ConfigError(
            "Plaintext database secrets are not allowed in DSN values. "
            "Use separate non-secret connection fields and `credential_target`."
        )


def assert_no_plaintext_secrets(config: dict[str, Any]) -> None:
    for key, value in config.items():
        normalized = key.strip().lower()
        if normalized in PLAINTEXT_SECRET_KEYS and not is_placeholder(str(value)):
            raise ConfigError(
                "Plaintext database secrets are not allowed in project profiles. "
                "Store the password in the OS credential store and reference it with "
                "`credential_target`."
            )
        if normalized in {"dsn", "db_dsn"} and dsn_contains_plaintext_password(value):
            raise ConfigError(
                "Plaintext database secrets are not allowed in DSN values. "
                "Use separate non-secret connection fields and `credential_target`."
            )


def load_profile(path: str | pathlib.Path) -> dict[str, Any]:
    profile_path = pathlib.Path(path)
    if not profile_path.exists():
        raise ConfigError(f"Config file not found: {profile_path}")
    try:
        data = json.loads(profile_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Config file is not valid JSON: {profile_path}") from exc
    if not isinstance(data, dict):
        raise ConfigError("Database profile must be a JSON object.")
    assert_no_plaintext_secrets(data)
    return data


def missing_config_keys(config: dict[str, Any]) -> list[str]:
    db_type = normalize_db_type(config_value(config, "DB_TYPE"))
    required = ["DB_TYPE"]

    if db_type == "sqlite":
        required.append("SQLITE_PATH")
    else:
        has_dsn = not is_placeholder(config_value(config, "DB_DSN"))
        if not has_dsn:
            required.extend(["DB_NAME", "DB_USER"])
            if is_placeholder(config_value(config, "DB_HOST")):
                required.append("DB_HOST")
        elif is_placeholder(config_value(config, "DB_NAME")) and is_placeholder(
            dsn_database_name(config_value(config, "DB_DSN"))
        ):
            required.append("DB_NAME")
        if is_placeholder(config_value(config, "CREDENTIAL_TARGET")):
            required.append("CREDENTIAL_TARGET")
    missing: list[str] = []
    for key in required:
        value = config_value(config, key)
        if is_placeholder(None if value is None else str(value)):
            missing.append(key)
    return missing


def postgres_connection_database(config: dict[str, Any]) -> Any:
    connection_database = config_value(config, "CONNECTION_DATABASE")
    if not is_placeholder(connection_database):
        return connection_database
    return config_value(config, "DB_NAME")


def missing_list_databases_config_keys(config: dict[str, Any]) -> list[str]:
    db_type = normalize_db_type(config_value(config, "DB_TYPE"))
    required = ["DB_TYPE"]

    if db_type == "sqlite":
        required.append("SQLITE_PATH")
    elif db_type in {"postgres", "mysql"}:
        has_dsn = not is_placeholder(config_value(config, "DB_DSN"))
        if not has_dsn:
            required.extend(["DB_HOST", "DB_USER"])
        elif is_placeholder(config_value(config, "DB_USER")) and is_placeholder(
            dsn_username(config_value(config, "DB_DSN"))
        ):
            required.append("DB_USER")
        if db_type == "postgres":
            dsn_has_database = has_dsn and not is_placeholder(
                dsn_database_name(config_value(config, "DB_DSN"))
            )
            if not dsn_has_database and is_placeholder(
                postgres_connection_database(config)
            ):
                required.append("CONNECTION_DATABASE")
        if is_placeholder(config_value(config, "CREDENTIAL_TARGET")):
            required.append("CREDENTIAL_TARGET")

    missing: list[str] = []
    for key in required:
        value = config_value(config, key)
        if is_placeholder(None if value is None else str(value)):
            missing.append(key)
    return missing


def resolve_target_tables(config: dict[str, Any], cli_tables: list[str]) -> list[str]:
    if cli_tables:
        return [table.strip() for table in cli_tables if table.strip()]
    raw = config_value(config, "TARGET_TABLES", "")
    if isinstance(raw, list):
        return [str(table).strip() for table in raw if str(table).strip()]
    return [table.strip() for table in str(raw).split(",") if table.strip()]


class CredentialAttribute(ctypes.Structure):
    _fields_ = [
        ("Keyword", wintypes.LPWSTR),
        ("Flags", wintypes.DWORD),
        ("ValueSize", wintypes.DWORD),
        ("Value", wintypes.LPBYTE),
    ]


class Credential(ctypes.Structure):
    _fields_ = [
        ("Flags", wintypes.DWORD),
        ("Type", wintypes.DWORD),
        ("TargetName", wintypes.LPWSTR),
        ("Comment", wintypes.LPWSTR),
        ("LastWritten", wintypes.FILETIME),
        ("CredentialBlobSize", wintypes.DWORD),
        ("CredentialBlob", wintypes.LPBYTE),
        ("Persist", wintypes.DWORD),
        ("AttributeCount", wintypes.DWORD),
        ("Attributes", ctypes.POINTER(CredentialAttribute)),
        ("TargetAlias", wintypes.LPWSTR),
        ("UserName", wintypes.LPWSTR),
    ]


def read_windows_credential(target: str) -> str:
    if os.name != "nt":
        raise ConfigError(
            "Windows Credential Manager is required for `credential_target` profiles."
        )

    credential_pointer = ctypes.POINTER(Credential)()
    cred_read = ctypes.windll.advapi32.CredReadW
    cred_read.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.POINTER(Credential)),
    ]
    cred_read.restype = wintypes.BOOL

    if not cred_read(target, 1, 0, ctypes.byref(credential_pointer)):
        raise ConfigError(
            "Database credential was not found in Windows Credential Manager for "
            f"target `{target}`."
        )

    try:
        credential = credential_pointer.contents
        raw = bytes(
            ctypes.string_at(
                credential.CredentialBlob,
                credential.CredentialBlobSize,
            )
        )
        try:
            return raw.decode("utf-16-le").rstrip("\x00")
        except UnicodeDecodeError:
            return raw.decode("utf-8")
    finally:
        ctypes.windll.advapi32.CredFree(credential_pointer)


def resolve_connection_credentials(config: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    user = config_value(config, "DB_USER")
    if not is_placeholder(None if user is None else str(user)):
        resolved["user"] = user

    password = config_value(config, "DB_PASSWORD")
    if not is_placeholder(None if password is None else str(password)):
        raise ConfigError(
            "Plaintext database secrets are not allowed. Store the password in "
            "the OS credential store and reference it with `credential_target`."
        )

    credential_target = config_value(config, "CREDENTIAL_TARGET")
    if not is_placeholder(None if credential_target is None else str(credential_target)):
        resolved["password"] = read_windows_credential(str(credential_target))
    return resolved


def sqlite_connect_readonly(sqlite_path: str) -> sqlite3.Connection:
    path = pathlib.Path(sqlite_path).resolve()
    if not path.exists():
        raise ConfigError(f"SQLite database file not found: {path}")
    return sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)


def sqlite_list_databases(config: dict[str, Any]) -> list[dict[str, Any]]:
    sqlite_path = str(config_value(config, "SQLITE_PATH"))
    return [{"database": str(pathlib.Path(sqlite_path).resolve())}]


def sqlite_list_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    sqlite_path = str(config_value(config, "SQLITE_PATH"))
    connection = sqlite_connect_readonly(sqlite_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        )
        return [{"schema": None, "table": row[0]} for row in cursor.fetchall()]
    finally:
        connection.close()


def quote_sqlite_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def sqlite_schema(config_or_path: dict[str, Any] | str, table: str) -> dict[str, Any]:
    sqlite_path = (
        str(config_value(config_or_path, "SQLITE_PATH"))
        if isinstance(config_or_path, dict)
        else str(config_or_path)
    )
    connection = sqlite_connect_readonly(sqlite_path)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT sql
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table,),
        )
        row = cursor.fetchone()
        ddl = row[0] if row else None
        cursor.execute(
            """
            SELECT cid, name, type, "notnull", dflt_value, pk
            FROM pragma_table_info(?)
            """,
            (table,),
        )
        columns = [
            {
                "cid": item[0],
                "name": item[1],
                "type": item[2],
                "notnull": bool(item[3]),
                "default": item[4],
                "pk": bool(item[5]),
            }
            for item in cursor.fetchall()
        ]
        cursor.execute(f"PRAGMA index_list({quote_sqlite_identifier(table)})")
        indexes = [
            {
                "name": item[1],
                "unique": bool(item[2]),
                "origin": item[3],
                "partial": bool(item[4]),
            }
            for item in cursor.fetchall()
        ]
        cursor.execute(f"PRAGMA foreign_key_list({quote_sqlite_identifier(table)})")
        foreign_keys = [
            {
                "id": item[0],
                "seq": item[1],
                "table": item[2],
                "from": item[3],
                "to": item[4],
                "on_update": item[5],
                "on_delete": item[6],
                "match": item[7],
            }
            for item in cursor.fetchall()
        ]
        if not ddl and not columns:
            raise ConfigError(f"Table not found in SQLite database: {table}")
        return {
            "engine": "sqlite",
            "table": table,
            "ddl": ddl,
            "columns": columns,
            "indexes": indexes,
            "foreign_keys": foreign_keys,
        }
    finally:
        connection.close()


def postgres_connection_kwargs(
    config: dict[str, Any],
    *,
    use_connection_database: bool = False,
) -> dict[str, Any]:
    dsn = config_value(config, "DB_DSN")
    database_name = (
        postgres_connection_database(config)
        if use_connection_database
        else config_value(config, "DB_NAME")
    )
    if not is_placeholder(dsn):
        credentials = resolve_connection_credentials(config)
        kwargs: dict[str, Any] = {"dsn": dsn}
        if not is_placeholder(database_name) and (
            use_connection_database or is_placeholder(dsn_database_name(dsn))
        ):
            kwargs["dbname"] = database_name
        if "user" in credentials:
            kwargs["user"] = credentials["user"]
        if "password" in credentials:
            kwargs["password"] = credentials["password"]
        return kwargs

    credentials = resolve_connection_credentials(config)
    kwargs: dict[str, Any] = {
        "dbname": database_name,
        "user": credentials.get("user", config_value(config, "DB_USER")),
        "password": credentials.get("password"),
        "host": config_value(config, "DB_HOST"),
    }
    if not is_placeholder(config_value(config, "DB_PORT")):
        kwargs["port"] = config_value(config, "DB_PORT")
    return {key: value for key, value in kwargs.items() if value is not None}


def mysql_connection_kwargs(config: dict[str, Any]) -> dict[str, Any]:
    if not is_placeholder(config_value(config, "DB_DSN")):
        dsn = config_value(config, "DB_DSN")
        ensure_dsn_has_no_plaintext_password(dsn)
        try:
            parsed = urlsplit(str(dsn).strip())
        except ValueError as exc:
            raise ConfigError("DB_DSN is not a valid MySQL DSN.") from exc
        credentials = resolve_connection_credentials(config)
        kwargs: dict[str, Any] = {
            "host": parsed.hostname,
            "user": credentials.get("user", dsn_username(dsn)),
            "password": credentials.get("password"),
            "database": config_value(config, "DB_NAME", dsn_database_name(dsn)),
        }
        if parsed.port is not None:
            kwargs["port"] = parsed.port
        return {key: value for key, value in kwargs.items() if value is not None}

    credentials = resolve_connection_credentials(config)
    kwargs: dict[str, Any] = {
        "database": config_value(config, "DB_NAME"),
        "user": credentials.get("user", config_value(config, "DB_USER")),
        "password": credentials.get("password"),
        "host": config_value(config, "DB_HOST"),
    }
    if not is_placeholder(config_value(config, "DB_PORT")):
        try:
            kwargs["port"] = int(config_value(config, "DB_PORT"))
        except ValueError as exc:
            raise ConfigError("DB_PORT must be numeric for MySQL connections.") from exc
    return {key: value for key, value in kwargs.items() if value is not None}


def connect_postgres(config: dict[str, Any], *, use_connection_database: bool = False):
    _, driver = load_postgres_driver()
    return driver.connect(
        **postgres_connection_kwargs(
            config,
            use_connection_database=use_connection_database,
        )
    )


def connect_mysql(config: dict[str, Any]):
    _, driver = load_mysql_driver()
    connection_kwargs = mysql_connection_kwargs(config)
    if "dsn" in connection_kwargs:
        raise ConfigError("DSN-based MySQL connections are not supported by this helper.")
    return driver.connect(**connection_kwargs)


def postgres_list_databases(config: dict[str, Any]) -> list[dict[str, Any]]:
    connection = connect_postgres(config, use_connection_database=True)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT datname
            FROM pg_database
            WHERE datistemplate = false
            ORDER BY datname
            """
        )
        return [{"database": row[0]} for row in cursor.fetchall()]
    finally:
        connection.close()


def mysql_list_databases(config: dict[str, Any]) -> list[dict[str, Any]]:
    connection = connect_mysql(config)
    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT SCHEMA_NAME
            FROM information_schema.SCHEMATA
            ORDER BY SCHEMA_NAME
            """
        )
        return [{"database": row[0]} for row in cursor.fetchall()]
    finally:
        connection.close()


def postgres_list_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    schema_name = config_value(config, "DB_SCHEMA")
    connection = connect_postgres(config)
    try:
        cursor = connection.cursor()
        if is_placeholder(None if schema_name is None else str(schema_name)):
            cursor.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name
                """
            )
            rows = cursor.fetchall()
        else:
            cursor.execute(
                """
                SELECT table_schema, table_name
                FROM information_schema.tables
                WHERE table_type = 'BASE TABLE'
                  AND table_schema = %s
                ORDER BY table_schema, table_name
                """,
                (schema_name,),
            )
            rows = cursor.fetchall()
        return [{"schema": row[0], "table": row[1]} for row in rows]
    finally:
        connection.close()


def mysql_list_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    database_name = config_value(config, "DB_NAME")
    connection = connect_mysql(config)
    try:
        cursor = connection.cursor()
        if is_placeholder(None if database_name is None else str(database_name)):
            cursor.execute(
                """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """
            )
            rows = cursor.fetchall()
        else:
            cursor.execute(
                """
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM information_schema.TABLES
                WHERE TABLE_TYPE = 'BASE TABLE'
                  AND TABLE_SCHEMA = %s
                ORDER BY TABLE_SCHEMA, TABLE_NAME
                """,
                (database_name,),
            )
            rows = cursor.fetchall()
        return [{"schema": row[0], "table": row[1]} for row in rows]
    finally:
        connection.close()


def postgres_schema(config: dict[str, Any], table: str) -> dict[str, Any]:
    schema_name = config_value(config, "DB_SCHEMA", "public")
    connection = connect_postgres(config)

    try:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT
              column_name,
              data_type,
              is_nullable,
              column_default
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name = %s
            ORDER BY ordinal_position
            """,
            (schema_name, table),
        )
        columns = [
            {
                "name": row[0],
                "type": row[1],
                "nullable": row[2],
                "default": row[3],
            }
            for row in cursor.fetchall()
        ]
        cursor.execute(
            """
            SELECT
              tc.constraint_name,
              tc.constraint_type,
              kcu.column_name
            FROM information_schema.table_constraints tc
            LEFT JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = %s
              AND tc.table_name = %s
            ORDER BY tc.constraint_name, kcu.ordinal_position
            """,
            (schema_name, table),
        )
        constraints = [
            {
                "name": row[0],
                "type": row[1],
                "column": row[2],
            }
            for row in cursor.fetchall()
        ]
        if not columns:
            raise ConfigError(
                f"Table not found in PostgreSQL schema `{schema_name}`: {table}"
            )
        return {
            "engine": "postgres",
            "schema": schema_name,
            "table": table,
            "ddl": None,
            "columns": columns,
            "constraints": constraints,
            "note": (
                "PostgreSQL metadata returned because SHOW CREATE TABLE is not "
                "available."
            ),
        }
    finally:
        connection.close()


def mysql_schema(config: dict[str, Any], table: str) -> dict[str, Any]:
    connection = connect_mysql(config)

    try:
        cursor = connection.cursor()
        database_name = config_value(config, "DB_NAME")
        safe_db = str(database_name).replace("`", "``") if database_name else ""
        safe_table = table.replace("`", "``")
        if database_name:
            cursor.execute(f"SHOW CREATE TABLE `{safe_db}`.`{safe_table}`")
        else:
            cursor.execute(f"SHOW CREATE TABLE `{safe_table}`")
        row = cursor.fetchone()
        if not row:
            raise ConfigError(f"Table not found in MySQL database: {table}")
        ddl = row[1]
        return {
            "engine": "mysql",
            "table": table,
            "ddl": ddl,
        }
    finally:
        connection.close()


def list_databases(config: dict[str, Any]) -> list[dict[str, Any]]:
    missing = missing_list_databases_config_keys(config)
    if missing:
        raise ConfigError(
            "Project database profile is incomplete. Missing or placeholder keys: "
            + ", ".join(sorted(missing))
        )
    db_type = normalize_db_type(config_value(config, "DB_TYPE"))
    if db_type == "sqlite":
        return sqlite_list_databases(config)
    if db_type == "postgres":
        return postgres_list_databases(config)
    if db_type == "mysql":
        return mysql_list_databases(config)
    raise ConfigError(f"Unsupported DB_TYPE: {config_value(config, 'DB_TYPE')}")


def raise_incomplete_profile_error(missing: list[str], config: dict[str, Any]) -> None:
    if "DB_NAME" in missing and not is_placeholder(config_value(config, "DB_DSN")):
        raise ConfigError("DSN must include a target database for this command.")
    raise ConfigError(
        "Project database profile is incomplete. Missing or placeholder keys: "
        + ", ".join(sorted(missing))
    )


def list_tables(config: dict[str, Any]) -> list[dict[str, Any]]:
    missing = missing_config_keys(config)
    if missing:
        raise_incomplete_profile_error(missing, config)
    db_type = normalize_db_type(config_value(config, "DB_TYPE"))
    if db_type == "sqlite":
        return sqlite_list_tables(config)
    if db_type == "postgres":
        return postgres_list_tables(config)
    if db_type == "mysql":
        return mysql_list_tables(config)
    raise ConfigError(f"Unsupported DB_TYPE: {config_value(config, 'DB_TYPE')}")


def describe_table(config: dict[str, Any], table: str) -> dict[str, Any]:
    missing = missing_config_keys(config)
    if missing:
        raise_incomplete_profile_error(missing, config)
    db_type = normalize_db_type(config_value(config, "DB_TYPE"))
    if db_type == "sqlite":
        return sqlite_schema(config, table)
    if db_type == "postgres":
        return postgres_schema(config, table)
    if db_type == "mysql":
        return mysql_schema(config, table)
    raise ConfigError(f"Unsupported DB_TYPE: {config_value(config, 'DB_TYPE')}")


def inspect_table(config: dict[str, Any], table: str) -> dict[str, Any]:
    return describe_table(config, table)


def add_common_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--config",
        help=(
            "Path to a project database profile. Defaults to "
            ".agents/database-schema-bootstrap/profiles/default.json."
        ),
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format.",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect database metadata using a project-level profile."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_databases_parser = subparsers.add_parser(
        "list-databases",
        help="List database names without reading table data.",
    )
    add_common_arguments(list_databases_parser)

    list_tables_parser = subparsers.add_parser(
        "list-tables",
        help="List table names without reading table data.",
    )
    add_common_arguments(list_tables_parser)

    describe_parser = subparsers.add_parser(
        "describe",
        help="Describe one or more table structures without reading rows.",
    )
    add_common_arguments(describe_parser)
    describe_parser.add_argument(
        "--table",
        action="append",
        required=True,
        help="Target table name. Repeat for multiple tables.",
    )
    return parser


def render_text(results: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for result in results:
        if set(result) == {"database"}:
            blocks.append(str(result["database"]))
            continue
        if set(result) == {"schema", "table"}:
            schema = result.get("schema")
            schema_prefix = f"{schema}." if schema else ""
            blocks.append(f"{schema_prefix}{result['table']}")
            continue
        schema = result.get("schema")
        schema_prefix = f"{schema}." if schema else ""
        header = f"[{result['engine']}] {schema_prefix}{result['table']}"
        blocks.append(header)
        ddl = result.get("ddl")
        if ddl:
            blocks.append(str(ddl))
        else:
            blocks.append(json.dumps(result, indent=2, ensure_ascii=False))
    return "\n\n".join(blocks)


def load_cli_profile(config_arg: str | None) -> dict[str, Any]:
    config_path = pathlib.Path(config_arg) if config_arg else default_project_config_path()
    return load_profile(config_path)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_cli_profile(args.config)
        if args.command == "list-databases":
            results = list_databases(config)
        elif args.command == "list-tables":
            results = list_tables(config)
        elif args.command == "describe":
            results = [describe_table(config, table) for table in args.table]
        else:
            raise ConfigError(f"Unsupported command: {args.command}")
    except (ConfigError, DriverError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    if args.format == "json":
        print(json.dumps(results, indent=2, ensure_ascii=False))
    else:
        print(render_text(results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
