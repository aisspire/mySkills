# v2 PostgreSQL schema 探查

## `list_databases`

连接到该 connection 配置的 `connection_database`，返回非模板数据库名。每条记录附带 `connection_id`。

## `list_tables`

连接到目标 `database`，只返回配置 `schema` 中 `BASE TABLE` 的 schema/table 名。不会读取表行。

## `describe_table`

输入一个未限定 PostgreSQL 表标识符，返回：

- 字段名、类型、可空性和默认值；
- 约束名称、类型和字段；
- 索引名称、唯一性、主键标记、有效性、访问方法、定义和条件。

结果附带 `connection_id`、engine、schema 和 table。工具不返回业务行、样例值、行数、执行计划或任意查询结果。

## 固定安全边界

gateway 内部使用只读事务、参数化查询、连接超时、statement timeout 和 lock timeout。工具不接受 SQL、schema、数据库名、host、user、password、DSN 或配置路径参数。

如果返回“当前项目连接不可用”，不要试图区分中央不存在、未授权、disabled、根不匹配或 secret 缺失；这些情况有意使用相同外部错误。报告需要人工检查 project status 与 connection 配置即可。
