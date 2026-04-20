from __future__ import annotations

import argparse
import json
import os
import pathlib
import sqlite3
import sys
from typing import Any


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


def is_placeholder(value: str | None) -> bool:
    if value is None:
        return True
    text = value.strip()
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


def missing_config_keys(config: dict[str, str]) -> list[str]:
    db_type = normalize_db_type(config.get("DB_TYPE"))
    required = ["DB_TYPE", "TARGET_TABLES"]

    if db_type == "sqlite":
        required.append("SQLITE_PATH")
    else:
        has_dsn = not is_placeholder(config.get("DB_DSN"))
        if db_type == "mysql" or not has_dsn:
            required.extend(["DB_NAME", "DB_USER", "DB_PASSWORD"])
            if is_placeholder(config.get("DB_HOST")):
                required.append("DB_HOST")
        if not has_dsn:
            required.extend(["DB_NAME", "DB_USER", "DB_PASSWORD"])
            if is_placeholder(config.get("DB_HOST")):
                required.append("DB_HOST")

    missing: list[str] = []
    for key in required:
        if is_placeholder(config.get(key)):
            missing.append(key)
    return missing


def resolve_target_tables(config: dict[str, str], cli_tables: list[str]) -> list[str]:
    if cli_tables:
        return [table.strip() for table in cli_tables if table.strip()]
    raw = config.get("TARGET_TABLES", "")
    return [table.strip() for table in raw.split(",") if table.strip()]


def normalize_db_type(value: str | None) -> str:
    if value is None:
        return ""
    db_type = value.strip().lower()
    aliases = {
        "postgresql": "postgres",
        "mariadb": "mysql",
    }
    return aliases.get(db_type, db_type)


def sqlite_schema(sqlite_path: str, table: str) -> dict[str, Any]:
    connection = sqlite3.connect(sqlite_path)
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
        cursor.execute("SELECT * FROM pragma_table_info(?)", (table,))
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
        if not ddl and not columns:
            raise ConfigError(f"Table not found in SQLite database: {table}")
        return {
            "engine": "sqlite",
            "table": table,
            "ddl": ddl,
            "columns": columns,
        }
    finally:
        connection.close()


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


def postgres_connection_kwargs(config: dict[str, str]) -> dict[str, Any]:
    if not is_placeholder(config.get("DB_DSN")):
        return {"dsn": config["DB_DSN"]}
    kwargs: dict[str, Any] = {
        "dbname": config.get("DB_NAME"),
        "user": config.get("DB_USER"),
        "password": config.get("DB_PASSWORD"),
        "host": config.get("DB_HOST"),
    }
    if not is_placeholder(config.get("DB_PORT")):
        kwargs["port"] = config.get("DB_PORT")
    return kwargs


def mysql_connection_kwargs(config: dict[str, str]) -> dict[str, Any]:
    if not is_placeholder(config.get("DB_DSN")):
        return {"dsn": config["DB_DSN"]}
    kwargs: dict[str, Any] = {
        "database": config.get("DB_NAME"),
        "user": config.get("DB_USER"),
        "password": config.get("DB_PASSWORD"),
        "host": config.get("DB_HOST"),
    }
    if not is_placeholder(config.get("DB_PORT")):
        try:
            kwargs["port"] = int(config["DB_PORT"])
        except ValueError as exc:
            raise ConfigError("DB_PORT must be numeric for MySQL connections.") from exc
    return kwargs


def postgres_schema(config: dict[str, str], table: str) -> dict[str, Any]:
    driver_name, driver = load_postgres_driver()
    schema_name = config.get("DB_SCHEMA", "public")
    connection_kwargs = postgres_connection_kwargs(config)

    connection = driver.connect(**connection_kwargs)

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
            raise ConfigError(f"Table not found in PostgreSQL schema `{schema_name}`: {table}")
        return {
            "engine": "postgres",
            "schema": schema_name,
            "table": table,
            "ddl": None,
            "columns": columns,
            "constraints": constraints,
            "note": "PostgreSQL metadata returned because SHOW CREATE TABLE is not available.",
        }
    finally:
        connection.close()


def mysql_schema(config: dict[str, str], table: str) -> dict[str, Any]:
    driver_name, driver = load_mysql_driver()
    connection_kwargs = mysql_connection_kwargs(config)

    if driver_name == "pymysql":
        if "dsn" in connection_kwargs:
            raise ConfigError("DSN-based MySQL connections are not supported with pymysql in this helper.")
        connection = driver.connect(**connection_kwargs)
    else:
        if "dsn" in connection_kwargs:
            raise ConfigError(
                "DSN-based MySQL connections are not supported with mysql-connector in this helper."
            )
        connection = driver.connect(**connection_kwargs)

    try:
        cursor = connection.cursor()
        database_name = config.get("DB_NAME")
        safe_db = database_name.replace("`", "``") if database_name else ""
        safe_table = table.replace("`", "``")
        if database_name:
            cursor.execute(f"SHOW CREATE TABLE `{safe_db}`.`{safe_table}`")
        else:
            cursor.execute(f"SHOW CREATE TABLE `{table}`")
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


def inspect_table(config: dict[str, str], table: str) -> dict[str, Any]:
    db_type = normalize_db_type(config.get("DB_TYPE"))
    if db_type == "sqlite":
        return sqlite_schema(config["SQLITE_PATH"], table)
    if db_type == "postgres":
        return postgres_schema(config, table)
    if db_type == "mysql":
        return mysql_schema(config, table)
    raise ConfigError(f"Unsupported DB_TYPE: {config.get('DB_TYPE')}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect database schema using a shared env-style config.")
    parser.add_argument("--env-file", required=True, help="Path to the shared database env file.")
    parser.add_argument(
        "--table",
        action="append",
        default=[],
        help="Target table name. Repeat for multiple tables. Falls back to TARGET_TABLES in config.",
    )
    parser.add_argument(
        "--format",
        choices=["json", "text"],
        default="json",
        help="Output format.",
    )
    return parser


def render_text(results: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for result in results:
        schema = result.get('schema')
        schema_prefix = f"{schema}." if schema else ""
        header = f"[{result['engine']}] {schema_prefix}{result['table']}"
        blocks.append(header)
        ddl = result.get("ddl")
        if ddl:
            blocks.append(str(ddl))
        else:
            blocks.append(json.dumps(result, indent=2, ensure_ascii=False))
    return "\n\n".join(blocks)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = merge_config(parse_env_file(args.env_file))
        missing = missing_config_keys(config)
        if missing:
            raise ConfigError(
                "Shared config is incomplete. Missing or placeholder keys: "
                + ", ".join(sorted(missing))
            )
        tables = resolve_target_tables(config, args.table)
        if not tables:
            raise ConfigError("No target tables provided. Set TARGET_TABLES or pass --table.")
        results = [inspect_table(config, table) for table in tables]
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
