# Schema Introspection Reference

Use the Python script path first, then fall back to direct SQL patterns only when needed.

## Preferred Path

Run [../scripts/inspect_schema.py](../scripts/inspect_schema.py) with the shared config file and target tables.

Typical shape:

```bash
<python-bin> scripts/inspect_schema.py --env-file path/to/database.env --table users --table orders
```

Expected behavior:

- prints `CREATE TABLE` output for engines that support it directly
- prints equivalent metadata for engines that do not
- exits with actionable errors when config or drivers are missing

## MySQL or MariaDB

Preferred:

```sql
SHOW CREATE TABLE `table_name`;
```

If the schema name matters:

```sql
SHOW CREATE TABLE `database_name`.`table_name`;
```

Useful fallback metadata:

```sql
SELECT
  COLUMN_NAME,
  COLUMN_TYPE,
  IS_NULLABLE,
  COLUMN_DEFAULT,
  COLUMN_KEY,
  EXTRA
FROM information_schema.COLUMNS
WHERE TABLE_SCHEMA = 'database_name'
  AND TABLE_NAME = 'table_name'
ORDER BY ORDINAL_POSITION;
```

## PostgreSQL

Preferred when shell access and client tools are available:

```bash
pg_dump --schema-only --table public.table_name db_name
```

SQL fallback for column metadata:

```sql
SELECT
  column_name,
  data_type,
  is_nullable,
  column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name = 'table_name'
ORDER BY ordinal_position;
```

Useful constraint metadata:

```sql
SELECT
  tc.constraint_name,
  tc.constraint_type,
  kcu.column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
 AND tc.table_schema = kcu.table_schema
WHERE tc.table_schema = 'public'
  AND tc.table_name = 'table_name';
```

PostgreSQL does not expose a simple built-in `SHOW CREATE TABLE` command like MySQL. When `pg_dump` is unavailable, gather equivalent metadata and state that the table DDL was reconstructed from catalog views.

## SQLite

Preferred:

```sql
SELECT sql
FROM sqlite_master
WHERE type = 'table'
  AND name = 'table_name';
```

Useful fallback metadata:

```sql
PRAGMA table_info('table_name');
```

## When Introspection Fails

If credentials, network, or permissions block access:

1. Ask the user for a working connection string or local access path.
2. If they cannot provide access, ask for the table DDL output.
3. Only then fall back to a manual table description.
