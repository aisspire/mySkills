from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Callable, Iterator

from .config import PostgresProfile
from .credentials import read_profile_password
from .errors import CredentialError, GatewayError, MetadataError
from .policy import validate_table_name


ConnectFactory = Callable[..., Any]


class PostgresMetadataService:
    """Read fixed PostgreSQL catalog queries without exposing a SQL interface."""

    def __init__(
        self,
        profile: PostgresProfile,
        *,
        credential_reader=read_profile_password,
        connect_factory: ConnectFactory | None = None,
    ) -> None:
        self.profile = profile
        self._credential_reader = credential_reader
        self._connect_factory = connect_factory or self._load_connect_factory()

    @staticmethod
    def _load_connect_factory() -> ConnectFactory:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:
            raise MetadataError(
                "PostgreSQL driver is unavailable. Install the service requirements."
            ) from exc
        return psycopg.connect

    def _connect(self, database: str):
        try:
            password = self._credential_reader(self.profile)
            if not password:
                raise CredentialError("Database credential is empty.")
            return self._connect_factory(
                host=self.profile.host,
                port=self.profile.port,
                dbname=database,
                user=self.profile.user,
                password=password,
                connect_timeout=10,
                options="-c statement_timeout=10000 -c lock_timeout=3000",
            )
        except GatewayError:
            raise
        except Exception as exc:
            raise MetadataError("PostgreSQL connection failed.") from exc

    @contextmanager
    def _read_only_cursor(self, database: str) -> Iterator[Any]:
        connection = self._connect(database)
        try:
            with connection.transaction():
                cursor = connection.cursor()
                cursor.execute("SET TRANSACTION READ ONLY")
                yield cursor
        except GatewayError:
            raise
        except Exception as exc:
            raise MetadataError("PostgreSQL metadata query failed.") from exc
        finally:
            connection.close()

    def list_databases(self) -> list[dict[str, str]]:
        query = """
            SELECT datname
            FROM pg_catalog.pg_database
            WHERE datistemplate = false
            ORDER BY datname
        """
        try:
            with self._read_only_cursor(self.profile.connection_database) as cursor:
                cursor.execute(query)
                return [{"database": row[0]} for row in cursor.fetchall()]
        except GatewayError:
            raise
        except Exception as exc:
            raise MetadataError("Could not list PostgreSQL databases.") from exc

    def list_tables(self) -> list[dict[str, str]]:
        query = """
            SELECT table_schema, table_name
            FROM information_schema.tables
            WHERE table_type = 'BASE TABLE'
              AND table_schema = %s
            ORDER BY table_schema, table_name
        """
        try:
            with self._read_only_cursor(self.profile.database) as cursor:
                cursor.execute(query, (self.profile.schema,))
                return [
                    {"schema": row[0], "table": row[1]}
                    for row in cursor.fetchall()
                ]
        except GatewayError:
            raise
        except Exception as exc:
            raise MetadataError("Could not list PostgreSQL tables.") from exc

    def describe_table(self, table: str) -> dict[str, object]:
        table = validate_table_name(table)
        try:
            with self._read_only_cursor(self.profile.database) as cursor:
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
                    (self.profile.schema, table),
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
                     AND tc.constraint_schema = kcu.constraint_schema
                     AND tc.table_schema = kcu.table_schema
                     AND tc.table_name = kcu.table_name
                    WHERE tc.table_schema = %s
                      AND tc.table_name = %s
                    ORDER BY tc.constraint_name, kcu.ordinal_position
                    """,
                    (self.profile.schema, table),
                )
                constraints = [
                    {"name": row[0], "type": row[1], "column": row[2]}
                    for row in cursor.fetchall()
                ]

                cursor.execute(
                    """
                    SELECT
                      index_relation.relname,
                      index_definition.indisunique,
                      index_definition.indisprimary,
                      index_definition.indisvalid,
                      access_method.amname,
                      pg_get_indexdef(index_definition.indexrelid),
                      pg_get_expr(index_definition.indpred, index_definition.indrelid)
                    FROM pg_catalog.pg_index index_definition
                    JOIN pg_catalog.pg_class table_relation
                      ON table_relation.oid = index_definition.indrelid
                    JOIN pg_catalog.pg_namespace table_namespace
                      ON table_namespace.oid = table_relation.relnamespace
                    JOIN pg_catalog.pg_class index_relation
                      ON index_relation.oid = index_definition.indexrelid
                    JOIN pg_catalog.pg_am access_method
                      ON access_method.oid = index_relation.relam
                    WHERE table_namespace.nspname = %s
                      AND table_relation.relname = %s
                    ORDER BY index_relation.relname
                    """,
                    (self.profile.schema, table),
                )
                indexes = [
                    {
                        "name": row[0],
                        "unique": bool(row[1]),
                        "primary": bool(row[2]),
                        "valid": bool(row[3]),
                        "method": row[4],
                        "definition": row[5],
                        "predicate": row[6],
                    }
                    for row in cursor.fetchall()
                ]
        except GatewayError:
            raise
        except Exception as exc:
            raise MetadataError("Could not describe PostgreSQL table.") from exc

        if not columns:
            raise MetadataError("Table was not found or metadata is unavailable.")
        return {
            "engine": "postgres",
            "schema": self.profile.schema,
            "table": table,
            "ddl": None,
            "columns": columns,
            "constraints": constraints,
            "indexes": indexes,
            "note": "PostgreSQL metadata returned from catalog views.",
        }

