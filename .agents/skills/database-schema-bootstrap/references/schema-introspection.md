# PostgreSQL Schema 探查参考

schema 探查只能通过 `database-schema-bootstrap` MCP 工具完成。AI 侧 adapter 只调用独立 metadata service；AI 不应直接执行下面类型的数据库命令，也不应调用旧版 CLI。

## 工具契约

### `list_databases`

只返回非模板 PostgreSQL 数据库名称。它使用 profile 的 `connection_database` 作为连接入口。

### `list_tables`

只返回 profile 指定 schema 中的基础表名称，不读取表行。

### `describe_table`

输入一个未限定的表名，返回：

- 字段名、类型、可空性和默认值
- 约束名称、类型和字段
- 索引名称、唯一性、主键标记、有效性、访问方法、定义和条件

工具不会返回业务行、样例值、行数或执行计划。

## 失败处理

如果 MCP adapter 或独立服务不可用、profile 缺失、Credential Manager 中没有凭据、驱动缺失或数据库权限不足：

1. 报告失败类别和需要人工修复的非密钥信息。
2. 不要求用户粘贴密码。
3. 不改用 `psql`、Python、旧 CLI 或任意 SQL。
4. 修复后由人工重启独立服务和 MCP adapter，再调用白名单工具。

## 事实边界

MCP 返回的字段、约束和索引是已确认的 schema 事实。工具未返回的内容必须标记为不确定，不得通过业务数据查询补齐。
