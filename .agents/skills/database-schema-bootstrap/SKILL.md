---
name: database-schema-bootstrap
description: Use when a task depends on real database metadata, including listing databases, listing tables, inspecting table structure, SQL generation, migrations, joins, data debugging, or CRUD work; uses project-level non-secret config and read-only metadata introspection. 用于依赖真实数据库元数据的任务，包括列库、列表、查看表结构、SQL 生成、迁移、关联分析、数据问题排查或 CRUD 开发；使用项目级非密钥配置和只读元数据探查。
---

# Database Schema Bootstrap（数据库结构引导）

## 概览

当任务依赖真实数据库结构，而不是手写或猜测的表描述时，使用这个 skill。

核心原则：从项目级 `.agents` 目录读取非密钥 profile，由脚本从操作系统密钥库读取密码，只探查元数据，再基于真实 schema 事实编写 SQL 或实现建议。

这个 skill 只用于发现元数据：

- 数据库名称
- 表名称
- 表结构、字段、默认值、键、索引，以及数据库支持时的约束信息

不得读取业务行、样例数据、行数，也不得执行任意 SQL。

## 何时使用

- 用户要为已有表编写 SQL
- 任务依赖字段名、类型、默认值、键或索引
- 请求涉及关联查询、迁移、CRUD 代码或 schema 不匹配排查
- 用户想知道有哪些数据库或表
- 项目可能已经有可复用的数据库连接配置

## 何时不要使用

- schema 是全新设计，尚无真实数据库
- 任务只是概念性数据库设计
- 用户已经提供权威 DDL，且不需要连接数据库核对
- 任务要求读取或修改业务数据
- 任务与数据库无关

## 安全边界

不要猜表结构。

不要要求用户把密码粘贴到聊天中。

不要从 AI 可见的文件中读取密码。

元数据发现阶段不得运行 `SELECT *`、抽样查询、行数统计、`INSERT`、`UPDATE`、`DELETE`、`ALTER`、`DROP`，也不得执行用户提供的任意 SQL。

只能使用具备元数据或只读权限的数据库账号。脚本限制能减少误操作，但数据库权限才是最终安全边界。

Windows Credential Manager 可以避免密码通过项目文件和命令输出意外暴露。它不能防御同一 Windows 用户下运行的恶意进程，因此数据库权限仍必须禁止写操作和业务数据读取。

如果项目 profile 包含 `password`、`DB_PASSWORD` 或带密码的 DSN，必须停止使用该配置，并要求用户把密钥迁移到操作系统密钥库。

为已有数据库编写 SQL、迁移步骤、数据修复方案或根因分析前：

1. 检查项目是否存在可用的非密钥 profile。
2. 如果 profile 缺失或不完整，只询问缺失的非密钥字段。
3. 如果 profile 可用，先连接并探查元数据。
4. 后续工作必须基于已发现的 schema，而不是基于假设。

## 快速参考

- 项目 profile 路径：`.agents/database-schema-bootstrap/profiles/default.json`
- 配置字段说明：[references/config-template.md](references/config-template.md)
- profile 示例：[references/profile.example.json](references/profile.example.json)
- Python 脚本：[scripts/inspect_schema.py](scripts/inspect_schema.py)
- 密钥初始化脚本：[scripts/set_db_secret.ps1](scripts/set_db_secret.ps1)
- 命令：`list-databases`、`list-tables`、`describe --table <name>`
- 配置缺失：只询问缺失的非密钥字段
- Python 环境损坏：停止并要求用户维护环境，同时给出具体修复命令
- 安全边界：只读元数据；不读取数据行、行数，不执行任意 SQL 或写操作

## 必要输入

询问用户前，先阅读 [references/config-template.md](references/config-template.md) 和 [references/profile.example.json](references/profile.example.json)。

项目 profile 必须放在 skill 目录外，避免链接安装或更新 skill 时覆盖项目配置：

```text
.agents/database-schema-bootstrap/profiles/default.json
```

必填 profile 字段：

- `db_type`: `mysql`, `postgres`, or `sqlite`
- `sqlite_path`：SQLite 使用
- `host`、`database`、`user`、`credential_target`：MySQL 或 PostgreSQL 使用
- `connection_database` 或 `maintenance_database`：PostgreSQL 执行 `list-databases` 时用于先连接的维护库，通常填 `postgres`
- `schema`：数据库引擎使用 schema 且目标 schema 已知时填写

可选字段：

- `port`
- `target_tables`：人工工作流中的默认表列表

`credential_target` 必须按项目隔离，建议包含 project、engine、host、database 和 user，例如 `database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user`。永远不要向用户索要密码值。要求用户通过 [scripts/set_db_secret.ps1](scripts/set_db_secret.ps1) 初始化该目标。

## 操作流程

### 1. 判断请求类型

当任务依赖已有数据库时使用此流程，例如：

- 列出可用数据库
- 列出可用表
- 查看表定义
- 编写或修正 SQL
- 解释数据关系
- 准备迁移
- 排查错误关联、缺失字段或类型不匹配
- 基于已有表生成 CRUD 代码
- 审计或验证 schema 假设

如果用户是在从零设计新 schema，且没有真实数据库，则跳过连接步骤，按普通需求澄清流程处理。

### 2. 检查项目配置

查找 `.agents/database-schema-bootstrap/profiles/default.json`。

如果文件缺失，要求用户基于 [references/profile.example.json](references/profile.example.json) 创建配置，并通过 [scripts/set_db_secret.ps1](scripts/set_db_secret.ps1) 初始化密码。

如果 profile 存在但关键字段缺失，只询问缺失的非密钥字段。

如果 profile 包含明文凭据，不要使用它。要求用户移除明文密钥，并将密码存入 Windows Credential Manager。

### 3. 探查前确认 Python 环境

使用当前项目中 assistant 正常可用的 Python 运行时。

如果 Python 存在但环境不可用，例如缺少 `psycopg`、`psycopg2`、`pymysql` 或 `mysql-connector-python` 等数据库驱动，停止并要求用户维护环境。给出明确修复建议，例如：

- 使用项目虚拟环境，并把数据库驱动安装到该环境。
- PostgreSQL 使用 `python -m pip install psycopg[binary]`。
- MySQL 使用 `python -m pip install pymysql` 或 `python -m pip install mysql-connector-python`。
- 如果项目锁定依赖，更新项目 lockfile 或环境声明，不要临时全局安装。

### 4. 优先使用 Python 脚本探查 schema

项目元数据访问可用后，先探查数据库元数据，再继续后续工作。

支持的命令：

- `list-databases`：只列出数据库名称
- `list-tables`：只列出表名称
- `describe --table <name>`：只返回表结构

如果数据库引擎能直接提供 `CREATE TABLE`，优先获取真实建表语句。如果不能直接获取，则收集字段、默认值、索引、主键、外键和约束等等价元数据。

只有在有助于后续任务时，才向用户总结已发现的 schema。

除非出现以下情况，否则不要要求用户手动枚举所有字段：

- 数据库访问不可用
- Python 环境不可用且用户尚未修复
- 凭据失败
- Python 环境缺少必要驱动且用户尚未修复
- 权限阻止元数据探查
- 目标还不是真实数据库

此步骤中避免任何读取数据行的查询和所有变更命令。发现 schema 不代表可以读取或修改数据。

### 5. 基于真实 schema 继续

探查后：

- 所有 SQL 都使用已发现的字段名和类型
- 需要时说明缺失索引、可空性、默认值和约束
- 如果探查结果不完整，明确说明仍存在的不确定性

## 输出规范

必须询问连接信息时，只询问非密钥字段，并保持请求简短具体。

当 Python 环境不可用时，直接说明需要用户维护环境，并给出具体恢复路径，不要泛泛而谈。

成功探查 schema 后，优先使用类似表述：

- “我先使用项目元数据探查脚本核对了数据库结构。”
- “我先检查了数据库元数据。”
- “schema 显示这些字段和约束。”
- “下面的 SQL 基于已发现的表结构。”

这样可以明确答案来自真实数据库结构，而不是猜测。

## 兜底规则

如果项目 profile 不可用：

1. 告诉用户确切缺失路径。
2. 只询问非密钥连接字段。
3. 要求用户单独初始化操作系统密钥。

如果凭据、网络、驱动或权限阻止访问：

1. 报告失败命令。
2. 说明根因。
3. 给出精确修复方式。
4. 给出修复后应重新运行的完整命令。

如果数据库访问不可行，先要求用户提供 DDL 输出作为人工替代。只有 DDL 也不可用时，才要求用户提供最小手动描述：

- 字段名和类型
- 主键
- 索引
- 外键

schema 未知时，不要假装已经知道。

## 常见错误

- 把密码存入 `.agents/database-schema-bootstrap/profiles/*.json`
- 把项目配置放进 `.agents/skills/database-schema-bootstrap`
- 多个项目共用 `database-schema-bootstrap/default` 这类泛化 `credential_target`
- 要求用户在聊天中粘贴凭据
- 未尝试探查就要求用户列出所有字段
- 脚本报告缺少驱动或环境不可用后仍继续
- 基于猜测字段名或猜测外键编写 SQL
- 为简单 schema 发现使用高权限连接
- 在同一步骤混合 schema 发现、数据读取或数据变更
- 探查只返回部分元数据时仍把结果描述为完全确定

## 验证状态

此版本已有单元测试覆盖项目级配置路径、明文密钥拒绝、mock 凭据读取、CLI 子命令和 SQLite 仅元数据探查。

此版本尚未使用只读凭据连接真实 MySQL 或 PostgreSQL 服务器验证，因此不要宣称这些引擎已完成完整运行时验证。

## 探查参考

使用 [references/schema-introspection.md](references/schema-introspection.md) 查看不同数据库引擎获取 `CREATE TABLE` 或等价元数据的方式。
