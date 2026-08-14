---
name: database-schema-bootstrap
description: Use when a task depends on real PostgreSQL schema metadata such as database names, tables, columns, keys, constraints, or indexes; use the configured metadata-only MCP tools and never connect to the database directly. 用于依赖真实 PostgreSQL schema 元数据的任务，例如库名、表名、字段、键、约束或索引；只能使用已配置的只读元数据 MCP 工具，AI 不得直接连接数据库。
---

# Database Schema Bootstrap（数据库结构引导）

## 概览

当任务依赖真实 PostgreSQL 结构，而不是手写或猜测的表描述时，使用这个 skill。

数据库连接由全局安装的受信任 metadata service 管理。AI 侧 stdio MCP adapter 每次工具调用都会按当前 Git 项目查找匹配的 loopback 状态，再把请求转发到该项目的服务实例；profile、Windows Credential Manager、PostgreSQL driver 和固定查询都位于独立服务与控制脚本，不在 AI 侧入口中。

全局 MCP 与 `SessionStart` hook 由人工安装到用户级 Codex 配置。hook 只处理当前 Git 项目：没有 project profile、项目身份无法确认、状态缺失或健康令牌不匹配时 adapter 必须失败关闭。MCP adapter 不得导入服务实现、读取 profile 或启动任意数据库连接。

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
5. MCP adapter 或本项目服务不可用、profile 缺失、项目身份无法确认或凭据失败时，停止数据库操作并报告阻塞；不得回退到直接连接数据库，也不得尝试其他项目的服务。
6. 数据库账号只能拥有元数据探查所需的最小权限。独立服务内部只运行固定的 PostgreSQL catalog 查询，不接受 SQL 字符串参数。
7. MCP adapter 只有 RPC endpoint，不包含 `psycopg`、profile loader、Credential Manager API 或数据库连接代码。

## 快速参考

- project profile：`.agents/database-schema-bootstrap/profiles/<name>.json`，由受信任服务读取
- 全局安装、登录、切换、并发与卸载：[tools/database-schema-bootstrap](../../../tools/database-schema-bootstrap/README.md)
- 独立服务：[mcp/database-schema-bootstrap](../../../mcp/database-schema-bootstrap/README.md)
- MCP 路由说明：[references/mcp-stdio.md](references/mcp-stdio.md)
- profile 字段：[references/config-template.md](references/config-template.md)
- profile 示例：[references/profile.example.json](references/profile.example.json)
- 双项目 cwd 人工发布门禁：[tests/database-schema-bootstrap-cwd-smoke.ps1](../../../tests/database-schema-bootstrap-cwd-smoke.ps1)
- 旧版凭据脚本：[mcp/database-schema-bootstrap/set_db_secret.ps1](../../../mcp/database-schema-bootstrap/set_db_secret.ps1) 仅作兼容，不是新流程入口
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

密码由人工通过控制脚本的隐藏输入在当前 Windows 用户上下文中初始化，AI 不应代为输入或读取密码。人工也可以不带参数运行 `profile add` 进入中文交互向导，一步完成添加、登录和可选的活动切换：

```powershell
$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"
& $dbs profile login -ProjectPath . -Name default
```

## 操作流程

1. 人工先安装全局运行时，并在当前 Git 项目添加、登录和选择 profile。
2. `SessionStart` hook 从事件 `cwd` 确认当前项目后启动或复用独立服务；`active-profile.json` 优先，没有它时仅使用 `default.json`。同项目启动和 `profile use` 使用排他锁，已验证健康的实例会复用；无法验证的旧 PID 不会被自动终止。
3. 确认 MCP 客户端只显示三个白名单工具。
4. 根据任务调用 `list_databases`、`list_tables` 或 `describe_table`。
5. 只使用工具返回的结构事实编写后续建议，不把结构探查扩展为数据查询。
6. 如果 adapter 或本项目服务不可用，报告需要人工配置的非密钥信息；不执行任何直接数据库命令。

卸载时，选择 `config` 或 `runtime` 会在确认前自动扩展为 `config,runtime,state`，以避免留下核心半状态；单独选择 `state` 只停止并清理项目服务状态，不删除 runtime 或 config。`-Repair` 只处理 state 已丢失、runtime 已不存在且仍有边界完整受管配置区块的旧半状态；state 缺失但 runtime 仍存在时会停止并报告。`session-reap` 只处理当前 Git 项目记录的 orphan service process，只有 PID、命令行哈希、进程创建时间、服务脚本、state path 和 project ID 全部匹配时才会终止进程，无法验证的记录会保留并使破坏性核心卸载失败。

项目身份使用绝对路径、词法 `normpath`、Windows 大小写归一化和末尾分隔符裁剪；不使用 `Path.resolve()` 或 `realpath()` 跟随 junction/symlink，因此控制脚本、adapter 和服务端保留相同的路径拼写。`active-profile`（不区分大小写）保留给 `active-profile.json`，profile 写入前会拒绝该名称。

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

当前实现提供 PostgreSQL-only 独立 metadata service、按 Git 项目动态路由的 AI 侧 adapter、实例令牌健康检查、Credential Manager 隔离、固定元数据查询和工具白名单测试。adapter 使用 25 秒端到端单调时钟预算；受管 MCP 工具和 hook 各保留 30 秒外层时限。

尚未用用户实际数据库凭据完成运行时探查验证；因此不要宣称真实 PostgreSQL 连接已经验证成功。真实验证只能通过 MCP 工具完成，不得绕过 MCP 直接执行 SQL。

发布前应运行上述 FakeService 夹具，并从它生成的两个项目分别执行真实 `codex exec -C <project>` 调用，确认各自只返回不同的标记表名；这验证真实客户端 cwd 路由，但不连接 PostgreSQL。

标准用户发布验收应使用非管理员普通用户 token 执行 `profile login`，关闭并重新打开该用户会话后，用同一 credential target 通过实际 metadata service 读取元数据；记录成功结果或完整 Win32 错误码。当前实现保留 `CredWrite` 的 `Persist=2`，除非出现可重复且确认的标准用户失败，不将其降级为 `Persist=1`。

目录分隔、项目状态与 RPC 白名单是行为边界；如果 AI 与服务使用同一 Windows 用户且能读取服务目录、profile 或凭据，不能把它们宣称为绝对安全隔离。生产部署仍应使用独立服务账号、ACL 和禁止 AI 直连 PostgreSQL 的网络策略。
