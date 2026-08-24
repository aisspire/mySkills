---
name: database-schema-bootstrap
description: Use when a task depends on real PostgreSQL schema metadata such as databases, tables, columns, keys, constraints, or indexes; use only the configured metadata-only MCP tools and never connect directly. 用于任务依赖真实 PostgreSQL schema 元数据时；只能使用已配置的元数据 MCP 工具，禁止直接连接数据库。
---

# Database Schema Bootstrap

## Overview

通过当前 Git 项目已启用的 connection ID 读取真实 PostgreSQL 结构元数据。公开能力只有：

- `list_databases(connection_id?: string)`
- `list_tables(connection_id?: string)`
- `describe_table(table: string, connection_id?: string)`

每项结果都包含 `connection_id`。省略 ID 时使用项目 `active`；显式 ID 也必须在项目 access 中 `enabled=true`。

本 skill 不读取业务行、不接受任意 SQL，也不管理数据库密码。

## When to Use

- 编写 SQL、迁移或 CRUD 前需要确认真实字段、类型、默认值、键或索引。
- 排查代码与 PostgreSQL schema 不一致。
- 用户要求列出数据库、表或描述表结构。
- 设计判断依赖已部署数据库的实际约束，而用户未提供权威 DDL。

## When NOT to Use

- 全新设计尚未落库，或用户提供的 DDL 已是本次任务的权威来源。
- 任务要求读取样例数据、业务行、行数、统计、执行计划或修改数据。
- 目标是 MySQL、SQLite 或其他非 PostgreSQL 数据库。
- 任务只涉及应用代码且不依赖真实 schema。
- 用户要求安装、录入密码或变更中央授权；这属于人工控制流程，不是 AI schema 探查。

## Trust Boundary

1. 只调用三个 MCP 工具；禁止 `psql`、Python 数据库脚本、shell 数据库命令和任意 SQL。
2. 可以读取当前项目的 `.agents/database-schema-bootstrap/access.json`，用于识别 enabled ID 与 active。
3. 不得读取 runtime 的 `connections.json`、`secrets.json`、`projects.json`、`service.json`、install state 或日志。
4. 不得请求、接收、转述或验证密码；不要让用户把密码粘贴到聊天中。
5. adapter/gateway 不可用、项目未初始化、无 enabled ID 或授权失败时停止数据库操作；不得回退直连或尝试另一项目的连接。
6. `enabled=false` 只表示逻辑不可用，不代表 connection ID 保密。
7. MCP 结果只证明返回的结构事实；未返回内容仍是不确定项。

运行时的明文 secret 是同一用户环境内的防误用软边界，不是对同用户恶意进程的强隔离。AI 不应因为文件可能可读而主动检查它。

## Workflow

1. 确认任务确实需要真实 PostgreSQL schema。
2. 如需选择连接，只读取当前 Git 根的项目 access：
   - 用户明确 connection ID：确认它 `enabled=true`；
   - 用户未指定：使用非空且已启用的 `active`；
   - 无可用 ID：报告需要人工执行项目 grant/enable/use，不猜测中央连接。
3. 根据问题调用最小工具：
   - 实例数据库清单：`list_databases`；
   - schema 基础表清单：`list_tables`；
   - 单表字段、约束和索引：`describe_table`。
4. 用返回的 `connection_id` 标注事实来源，避免混淆多个连接。
5. 后续 SQL 或代码只基于已确认 schema；明确区分已确认事实与未返回信息。

## Tool Contract

```text
list_databases(connection_id?: "erp-prod-ro")
  -> [{"connection_id":"erp-prod-ro","database":"erp"}]

list_tables(connection_id?: "erp-prod-ro")
  -> [{"connection_id":"erp-prod-ro","schema":"public","table":"users"}]

describe_table(table: "users", connection_id?: "erp-prod-ro")
  -> connection_id / schema / table / columns / constraints / indexes
```

`list_databases` 列出目标 PostgreSQL 实例中的非模板数据库，不用于列举中央 connection ID。`describe_table.table` 只能是未限定表名，不接受 schema、SQL 片段或表达式。

详细契约见 [schema introspection](references/v2-schema-introspection.md)。项目 access 结构见 [project access](references/v2-project-access.md)。stdio 与 gateway 路由见 [MCP routing](references/v2-mcp-stdio.md)。

## Failure Handling

- “当前项目连接不可用”：可能是未知、禁用、未授权、已删除、缺 secret 或根绑定不一致；不要探测中央配置来区分。
- “runtime incomplete”：人工重新运行不带 skip 的安装/升级；AI 不安装全局依赖。
- “service unavailable/invalid state”：人工使用 control `service status/ensure`；身份无法验证时不建议强杀 PID。
- PostgreSQL 连接/权限失败：只报告非秘密错误类别和 connection ID；不要求密码，不改用直连。
- 元数据不完整：说明哪些字段已返回、哪些仍未知，不用业务查询补齐。

## Common Mistakes

- 把 connection ID 当成数据库名，或用 `list_databases` 枚举中央连接。
- 显式传入 access 中 disabled 的 ID。
- 读取 runtime secrets、中央 connections/projects 或 service state 来“排错”。
- MCP 失败后改用 `psql`、Python、DSN 或用户提供 SQL。
- 用 `SELECT *`、抽样、计数或 `EXPLAIN ANALYZE` 验证 schema。
- 混合多个 connection 的结果却不保留返回的 `connection_id`。
- 把本地明文 secrets 描述成强安全隔离。

## Verification Status

正式 v2 skill 已完成静态安全/结构复审和自动行为测试，当前等级为 `static-compliant`。完整 venv 中的 MCP 工具枚举、loopback HTTP、双项目 FakeGateway 路由和 daemon ensure/status/stop 已验证。

尚未完成 Windows 普通用户、WSL 普通用户和真实 PostgreSQL 的双平台发布门禁，因此不得宣称跨平台发布验收完成或真实数据库连接已全面验收。
