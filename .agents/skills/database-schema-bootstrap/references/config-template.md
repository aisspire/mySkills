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

- `db_type`：`mysql`、`postgres` 或 `sqlite`
- `host`：MySQL 或 PostgreSQL 的数据库主机
- `port`：可选端口
- `database`：数据库名称
- `connection_database` 或 `maintenance_database`：PostgreSQL `list-databases` 连接入口库，通常填 `postgres`；MySQL 列库不需要该字段
- `schema`：需要时填写 PostgreSQL schema 或 MySQL database/schema 名称
- `user`：元数据或只读数据库用户
- `credential_target`：Windows Credential Manager 目标名称
- `sqlite_path`：SQLite 数据库路径
- `target_tables`：可选默认表列表，用于已知目标表的工作流

优先使用最小权限凭据。数据库用户应无法写入数据或修改 schema。

如果 Python 存在但缺少必要驱动，要求用户维护环境，并提供明确的包安装建议。
