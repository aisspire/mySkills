# PostgreSQL MCP Profile 说明

项目 profile 放在目标项目根目录：

```text
.agents/database-schema-bootstrap/profiles/default.json
```

它由全局安装运行时中的受信任独立服务读取，AI 侧 MCP adapter 不读取它，也不通过它建立数据库连接。adapter 只会路由到当前 Git 项目的已验证服务实例。

## 推荐 profile

```json
{
  "project": "example-project",
  "db_type": "postgres",
  "host": "db.example.test",
  "port": 5432,
  "database": "app_database",
  "connection_database": "postgres",
  "schema": "public",
  "user": "readonly_metadata_user",
  "credential_target": "database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user",
  "target_tables": ["users", "orders"]
}
```

## 字段

| 字段 | 含义 | 要求 |
| --- | --- | --- |
| `db_type` | 数据库类型 | 必须是 `postgres` |
| `host` | PostgreSQL 主机 | 必填 |
| `port` | PostgreSQL 端口 | 可选，默认 `5432` |
| `database` | 目标业务数据库 | 必填 |
| `connection_database` | `list_databases` 使用的入口数据库 | 必填，通常是 `postgres` |
| `schema` | 目标 schema | 可选，默认 `public` |
| `user` | 元数据账号 | 必填，建议使用最小权限账号 |
| `credential_target` | Windows Credential Manager 目标名称 | 必填，不是密码值 |
| `target_tables` | 人工提示用的表清单 | 可选，不是权限控制 |

旧 profile 中的 `maintenance_database` 可作为 `connection_database` 的兼容别名，但新配置应使用 `connection_database`。

## 密钥处理

不要在 profile 保存密码、`DB_PASSWORD` 或 DSN。密码必须由人工使用隐藏输入写入 Credential Manager：

```powershell
$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"
& $dbs profile login -ProjectPath . -Name default
```

独立服务只在建立 PostgreSQL 连接时读取该目标。密码不会成为 MCP 工具参数、工具结果或日志内容，也不会进入 AI 侧 adapter 进程。profile 的创建、选择和状态查看使用同一个控制入口：`profile add`、`profile use`、`profile list` 和 `status`。

如果 profile 包含明文凭据、DSN、MySQL 配置或 SQLite 配置，独立服务应拒绝启动。
