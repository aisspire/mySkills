# 项目 Profile 说明

每个项目使用 [profile.example.json](profile.example.json) 作为模板。

复制到：

```text
.agents/database-schema-bootstrap/profiles/default.json
```

该文件必须放在 `.agents/skills/database-schema-bootstrap` 外部。安装后的 skill 可能通过链接指向共享源仓库，并会独立于每个项目更新；项目配置不能被 skill 更新覆盖。

## 密钥处理

不要在 profile 中保存密码。

profile 必须通过 `credential_target` 引用 Windows Credential Manager 中的密钥。使用下面的命令初始化：

```powershell
.\.agents\skills\database-schema-bootstrap\scripts\set_db_secret.ps1 -Target "database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user"
```

初始化脚本会用隐藏输入提示用户输入密码。不要把密码作为命令参数传入。

`credential_target` 必须按项目定制，建议至少包含 project、engine、host、database 和 user，避免多个项目复制同一个目标后互相覆盖或读取错误密码。

这可以避免密码通过文件、提示词和脚本输出意外暴露。它不能替代数据库侧的只读或仅元数据权限控制。

如果 profile 包含以下内容，视为无效配置：

- `password`
- `DB_PASSWORD`
- 带密码的 DSN
- 任何其他明文凭据字段

## 字段

字段名使用 JSON 的 snake_case 写法。比如实际字段是 `connection_database`，不是 `connectionDatabase`。

| 字段 | 含义 | 什么时候填 | 示例 |
| --- | --- | --- | --- |
| `db_type` | 数据库类型。 | 必填。 | `postgres`、`mysql`、`sqlite` |
| `host` | MySQL 或 PostgreSQL 主机。 | MySQL/PostgreSQL 使用。 | `db.example.test` |
| `port` | 端口。 | 可选；不填则使用驱动默认值。 | `5432`、`3306` |
| `database` | 目标业务数据库名。`list-tables`、`describe` 和后续 SQL 主要面向这个库。MySQL 中它也基本等同于 schema 名。 | MySQL/PostgreSQL 做列表或查表结构时填写。MySQL 只做 `list-databases` 时可以临时不填。 | `app_database` |
| `connection_database` | PostgreSQL `list-databases` 之前必须先连接的入口库。它不是业务库，只是连接入口。 | PostgreSQL 想列出所有数据库，且 DSN 没有自带库名时填写。通常填 `postgres`。MySQL 不填。 | `postgres` |
| `maintenance_database` | `connection_database` 的兼容别名。 | 老配置可用；新配置优先写 `connection_database`。 | `postgres` |
| `schema` | 数据库内部命名空间筛选。PostgreSQL 常见值是 `public`。MySQL 通常不需要单独填，因为 `database` 已经是筛选范围。 | PostgreSQL 表不在 `public`，或只想限制到某个 schema 时填写。不确定可先不填。 | `public` |
| `user` | 元数据或只读数据库用户。 | MySQL/PostgreSQL 使用。 | `readonly_metadata_user` |
| `credential_target` | Windows Credential Manager 目标名称。profile 保存的是这个名称，不是密码。 | MySQL/PostgreSQL 必填。必须按项目、引擎、主机、库和用户隔离。 | `database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user` |
| `sqlite_path` | SQLite 数据库文件路径。 | 仅 SQLite 使用。 | `data/app.sqlite` |
| `target_tables` | 默认关注表清单。它只是给 AI 或人工流程的提示，不是连接目标，也不是密码 target。当前 `describe` 命令仍需要显式传 `--table`。 | 可选。知道本次常查哪些表时填写；不确定就删除或留空。 | `["users", "orders"]` |

最容易混淆的关系：

- `database`：真正要工作的业务库。
- `connection_database`：PostgreSQL 列库时临时连接的入口库，常填 `postgres`。
- `schema`：业务库里面的命名空间，PostgreSQL 常见是 `public`。
- `credential_target`：密码在 Windows Credential Manager 里的名字。
- `target_tables`：默认关注表清单，不控制连接。

优先使用最小权限凭据。数据库用户应无法写入数据或修改 schema。

如果 Python 存在但缺少必要驱动，要求用户维护环境，并提供明确的包安装建议。
