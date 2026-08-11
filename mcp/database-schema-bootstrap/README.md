# database-schema-bootstrap 独立服务

这里是数据库元数据服务的受信任部分。它独立于 AI 侧的 MCP adapter，负责：

- 读取项目 PostgreSQL profile；
- 从 Windows Credential Manager 读取密码；
- 使用 `psycopg` 连接 PostgreSQL；
- 只执行固定的 PostgreSQL catalog 元数据查询。

AI 侧不应启动或导入本目录中的服务代码。MCP adapter 只知道 loopback endpoint 和三个工具名：

- `list_databases`
- `list_tables`
- `describe_table`

## 启动

在与服务账号相同的 Windows 用户上下文中安装依赖并写入凭据：

```powershell
D:\Anaconda\envs\xcyl\python.exe -m pip install -r E:\code\skills\mcp\database-schema-bootstrap\requirements.txt
E:\code\skills\mcp\database-schema-bootstrap\set_db_secret.ps1 -Target "database-schema-bootstrap/example-project/postgres/db.example.test/app_database/readonly_metadata_user"
```

由人工、Windows Service 或其他受控进程单独启动服务：

```powershell
D:\Anaconda\envs\xcyl\python.exe E:\code\skills\mcp\database-schema-bootstrap\server.py `
  --config E:\code\xcyl-voltflow\.agents\database-schema-bootstrap\profiles\default.json `
  --port 8765
```

服务固定绑定 `127.0.0.1`，不会把 PostgreSQL 账号、密码或 profile 作为 MCP 工具参数接收。

## RPC 契约

服务只接受 `POST /v1/metadata`，请求体严格限定为：

```json
{"operation":"list_databases"}
{"operation":"list_tables"}
{"operation":"describe_table","table":"users"}
```

不接受 `sql`、`query`、`dsn`、`password` 或任意额外字段。服务响应只返回 schema 元数据，不返回业务行、样例数据、行数或执行计划。

## 隔离要求

目录分隔本身不是操作系统安全边界。要让 AI 无法通过代码绕过本服务，生产部署还必须满足：

1. 服务由独立账号或受控 Windows Service 启动；
2. AI 运行账号没有 PostgreSQL 凭据、profile 和服务部署目录的读取权限；
3. AI 运行环境没有直连 PostgreSQL 的网络和认证路径；
4. AI 侧只启动 `.agents/skills/database-schema-bootstrap/mcp_server.py`，不负责启动本服务。

在同一用户、同一可读工作区内运行时，这个目录只能提供代码结构和行为约束，不能宣称为绝对安全隔离。

