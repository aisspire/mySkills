---
name: database-schema-bootstrap
description: Use when a task depends on real PostgreSQL schema metadata such as database names, tables, columns, keys, constraints, or indexes; use the configured metadata-only MCP tools and never connect to the database directly. 用于依赖真实 PostgreSQL schema 元数据的任务，例如库名、表名、字段、键、约束或索引；只能使用已配置的只读元数据 MCP 工具，AI 不得直接连接数据库。
---

# Database Schema Bootstrap（数据库结构引导）

## 概览

当任务依赖真实 PostgreSQL 结构，而不是手写或猜测的表描述时，使用这个 skill。

数据库连接由根目录 `mcp/database-schema-bootstrap` 的独立 metadata service 管理。AI 侧 stdio MCP adapter 只负责把三个白名单工具转发到 loopback RPC；profile、Windows Credential Manager、PostgreSQL driver 和固定查询都位于独立服务，不在 AI 侧入口中。

独立服务应由人工、Windows Service 或其他受控进程提前启动。MCP adapter 不得启动、导入或读取独立服务的实现。

本 skill 只允许发现以下元数据：

- 数据库名称
- 表名称
- 字段、类型、可空性和默认值
- 主键、外键、约束和索引

不得读取业务行、样例数据、行数，也不得执行用户提供的 SQL。

## 何时使用

- 用户要基于已有 PostgreSQL 表编写 SQL、迁移或 CRUD 代码
- 任务依赖真实字段名、类型、默认值、键、约束或索引
- 需要解释表关系或排查 schema 不匹配
- 用户要查看数据库或表结构

## 何时不要使用

- schema 是全新设计，尚无真实 PostgreSQL
- 用户已经提供权威 DDL，且不需要核对真实数据库
- 任务要求读取或修改业务数据
- 任务与数据库结构无关

## 安全边界

1. AI 只能调用以下三个 MCP 工具：
   - `list_databases`
   - `list_tables`
   - `describe_table`
2. AI 不得调用 `psql`、Python 数据库脚本、旧 CLI、shell 或任意 SQL 连接数据库。
3. AI 不得读取、请求或转述密码；不得要求用户把密码粘贴到聊天中。
4. AI 不得调用 `SELECT *`、抽样查询、行数统计、`EXPLAIN ANALYZE`、`INSERT`、`UPDATE`、`DELETE`、DDL 或用户提供的任意 SQL。
5. MCP adapter 或独立服务不可用、profile 缺失或凭据失败时，停止数据库操作并报告阻塞；不得回退到直接连接数据库。
6. 数据库账号只能拥有元数据探查所需的最小权限。独立服务内部只运行固定的 PostgreSQL catalog 查询，不接受 SQL 字符串参数。
7. MCP adapter 只有 RPC endpoint，不包含 `psycopg`、profile loader、Credential Manager API 或数据库连接代码。

## 快速参考

- project profile：`.agents/database-schema-bootstrap/profiles/default.json`，由独立服务读取
- 独立服务：[mcp/database-schema-bootstrap](../../../mcp/database-schema-bootstrap/README.md)
- MCP 启动与通用 stdio 配置：[references/mcp-stdio.md](references/mcp-stdio.md)
- profile 字段：[references/config-template.md](references/config-template.md)
- profile 示例：[references/profile.example.json](references/profile.example.json)
- 人工初始化 Windows Credential Manager：`mcp/database-schema-bootstrap/set_db_secret.ps1`
- AI 侧 MCP 依赖：[requirements-mcp.txt](requirements-mcp.txt)

MCP 工具输入输出：

```text
list_databases()
  -> [{"database": "..."}]

list_tables()
  -> [{"schema": "public", "table": "..."}]

describe_table(table: "users")
  -> columns / constraints / indexes 等结构元数据
```

`schema`、数据库地址、用户名和密码都由独立服务管理，不是 MCP 工具参数。

## 必要输入

独立服务使用项目 profile，AI 不负责读取它来建立数据库连接。profile 只支持 PostgreSQL：

- `db_type`: 必须为 `postgres`
- `host`、`port`、`database`、`connection_database`
- `schema`：默认 `public`
- `user`
- `credential_target`：Windows Credential Manager 目标名称，不是密码
- `target_tables`：可选的人工提示清单，不改变工具权限

profile 禁止包含：

- `password`、`DB_PASSWORD` 或其他明文凭据
- DSN 或带密码的连接字符串
- MySQL、SQLite 或 `sqlite_path` 配置

密码由人工在独立服务运行账号的上下文中初始化，AI 不应代为输入或读取密码：

```powershell
E:\code\skills\mcp\database-schema-bootstrap\set_db_secret.ps1 -Target "database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user"
```

## 操作流程

1. 由人工或受控服务管理器启动 `mcp/database-schema-bootstrap/server.py`。
2. 确认 MCP 客户端已连接 AI 侧 adapter，且只显示三个白名单工具。
3. 根据任务调用 `list_databases`、`list_tables` 或 `describe_table`。
4. 只使用工具返回的结构事实编写后续建议，不把结构探查扩展为数据查询。
5. 如果 adapter 或独立服务不可用，报告需要人工配置的非密钥信息；不执行任何直接数据库命令。

## 输出规范

成功探查后，明确说明结果来自 MCP 元数据工具，例如：

- “MCP 返回的 schema 显示这些字段和约束。”
- “下面的 SQL 基于已发现的 PostgreSQL 表结构。”

如果工具返回的元数据不完整，区分已确认事实和仍然存在的不确定性。

## 常见错误

- 试图让 AI 读取 profile 中的密码或 `credential_target` 对应的密钥
- MCP adapter 或独立服务不可用时改用 `psql`、Python 或旧版 CLI
- 为了“验证连接”执行业务查询、`EXPLAIN ANALYZE` 或样例数据查询
- 把 `target_tables` 误认为数据库权限控制
- 把 MCP 工具描述中的“只读”当成任意 SQL 都可执行
- 让 MCP adapter 进程直接导入服务包、启动服务或接收 profile 路径

## 验证状态

当前实现提供 PostgreSQL-only 独立 metadata service、AI 侧 RPC-only MCP adapter、Credential Manager 隔离、固定元数据查询和工具白名单测试。

尚未用用户实际数据库凭据完成运行时探查验证；因此不要宣称真实 PostgreSQL 连接已经验证成功。真实验证只能通过 MCP 工具完成，不得绕过 MCP 直接执行 SQL。

目录分隔和 RPC 白名单是行为边界；如果 AI 与服务使用同一 Windows 用户且能读取服务目录、profile 或凭据，不能把它们宣称为绝对安全隔离。生产部署仍应使用独立服务账号、ACL 和禁止 AI 直连 PostgreSQL 的网络策略。
