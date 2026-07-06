# Schema 探查参考

优先使用 Python 脚本。只有辅助脚本无法运行，且用户仍需要精确元数据查询时，才退回到直接 SQL 模式。

## 首选路径

使用 `.agents/database-schema-bootstrap/profiles/default.json` 中的项目 profile 运行 [../scripts/inspect_schema.py](../scripts/inspect_schema.py)。

典型命令：

```powershell
python .\.agents\skills\database-schema-bootstrap\scripts\inspect_schema.py list-databases
python .\.agents\skills\database-schema-bootstrap\scripts\inspect_schema.py list-tables
python .\.agents\skills\database-schema-bootstrap\scripts\inspect_schema.py describe --table users --table orders
```

预期行为：

- `list-databases` 输出数据库名称
- `list-tables` 输出表名称
- 对支持直接获取的数据库引擎输出 `CREATE TABLE`
- 对不支持直接获取的数据库引擎输出等价元数据
- 永不输出数据行、行数、样例数据或密码
- 配置或驱动缺失时，用可操作的错误信息退出

MySQL 的 `list-databases` 可以只连接到 server，不要求 profile 预先填写 `database`。

PostgreSQL 的 `list-databases` 必须先连接到某个数据库。profile 应填写 `connection_database` 或 `maintenance_database`，常用值为 `postgres`；如果 DSN 已包含数据库名，也可由 DSN 提供。

## MySQL or MariaDB

列出数据库：

```sql
SELECT SCHEMA_NAME
FROM information_schema.SCHEMATA
ORDER BY SCHEMA_NAME;
```

列出表：

```sql
SELECT TABLE_SCHEMA, TABLE_NAME
FROM information_schema.TABLES
WHERE TABLE_TYPE = 'BASE TABLE'
ORDER BY TABLE_SCHEMA, TABLE_NAME;
```

查看表结构：

```sql
SHOW CREATE TABLE `table_name`;
```

如果需要指定 schema 名称：

```sql
SHOW CREATE TABLE `database_name`.`table_name`;
```

可用的兜底元数据查询：

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

列出数据库：

```sql
SELECT datname
FROM pg_database
WHERE datistemplate = false
ORDER BY datname;
```

列出表：

```sql
SELECT table_schema, table_name
FROM information_schema.tables
WHERE table_type = 'BASE TABLE'
  AND table_schema NOT IN ('pg_catalog', 'information_schema')
ORDER BY table_schema, table_name;
```

字段元数据 SQL 兜底：

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

可用的约束元数据查询：

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

PostgreSQL 不像 MySQL 一样提供简单内置的 `SHOW CREATE TABLE`。当 `pg_dump` 不可用时，收集等价元数据，并说明表 DDL 是根据 catalog views 重建的。

## SQLite

列出表：

```sql
SELECT name
FROM sqlite_master
WHERE type = 'table'
  AND name NOT LIKE 'sqlite_%'
ORDER BY name;
```

查看表结构：

```sql
SELECT sql
FROM sqlite_master
WHERE type = 'table'
  AND name = 'table_name';
```

可用的兜底元数据查询：

```sql
PRAGMA table_info('table_name');
```

## 探查失败时

如果凭据、网络、驱动或权限阻止访问：

1. 报告失败命令。
2. 说明根因。
3. 给出精确修复方式。
4. 给出修复后应重新运行的完整命令。
5. 如果仍无法访问，先要求 DDL 输出，再接受手动表结构描述。
