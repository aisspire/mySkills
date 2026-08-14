# database-schema-bootstrap 受信任元数据服务

本目录是全局 PostgreSQL MCP 运行时的服务端源码。它读取项目 profile、从 Windows Credential Manager 读取密码、加载 `psycopg`，并且只执行固定的 PostgreSQL catalog 元数据查询。

AI 侧 adapter 不导入本目录，不读取 profile、Credential Manager 或数据库驱动。安装后服务源码会复制到 `%USERPROFILE%\.codex\database-schema-bootstrap\service`；不要把源码仓库路径配置为 Codex MCP 的运行路径。

## 运行方式

请通过 [`tools/database-schema-bootstrap`](../../tools/database-schema-bootstrap/README.md) 的安装器和控制脚本运行。安装器在 `~/.codex/config.toml` 注册一个全局 stdio MCP adapter，并配置 `SessionStart` hook；hook 只会为当前 Git 项目路由并启动服务。

新的凭据入口统一为：

```powershell
$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"
& $dbs profile login -ProjectPath . -Name default
```

仓库中的 `set_db_secret.ps1` 仅保留给旧部署兼容使用，不再作为新安装或登录流程入口；它不会改变控制脚本保留的 `CredWrite Persist=2` 语义。

项目 profile 保持在：

```text
<项目根>/.agents/database-schema-bootstrap/profiles/<name>.json
```

每个项目会有独立的动态 loopback 端口、ready-state 文件和实例令牌。服务固定绑定 `127.0.0.1`，`/v1/health` 不访问数据库且需要实例令牌；`POST /v1/metadata` 同样需要令牌。服务不会接收密码、DSN、profile 路径或任意 SQL 作为 MCP 工具参数。

ready-state 使用 token 所有权删除：停止中的旧服务只会删除仍持有相同 `instance_token` 的状态，不会删掉较新实例的记录。控制脚本仅在旧进程命令行同时匹配已安装服务脚本、状态路径、项目 ID 与当前实例令牌时才会终止它；损坏状态、缺失 PID 或无法验证的进程只会触发状态恢复，未知 PID 不会被自动终止。ownership 校验失败的存活 PID 会记录到 `install-state.json.orphan_service_processes`，其中包含命令行 SHA-256 和进程创建时间；`session-reap` 只有完整身份匹配才会回收，无法验证的记录会保留。

受控服务管理器启动的等价形态如下（由控制脚本生成，不建议手动复制令牌）：

```text
<python> -B <installed-runtime>\service\server.py \
  --config <项目 profile> --port 0 \
  --instance-token <随机令牌> \
  --ready-state <installed-runtime>\state\projects\<项目 SHA-256>.json \
  --project-id <项目 SHA-256> --project-root <规范化项目根>
```

## RPC 契约

服务只接受下列固定操作：

```json
{"operation":"list_databases"}
{"operation":"list_tables"}
{"operation":"describe_table","table":"users"}
```

不接受 `sql`、`query`、`dsn`、`password` 或额外字段。响应只包含 schema 元数据，不返回业务行、样例数据、行数或执行计划。

## 安全边界

1. adapter 仅提供 `list_databases`、`list_tables`、`describe_table` 三项工具。
2. adapter 无法确认当前 Git 项目、找不到匹配状态或健康令牌不匹配时必须失败关闭；不得连接其他项目或退回直连数据库。
3. profile 禁止明文密码和 DSN；密码只由 `profile login` 通过隐藏输入写入 Credential Manager。
4. 同一 Windows 用户下可读目录不是绝对安全隔离。生产部署仍需独立服务账号、ACL、最小权限 PostgreSQL 账号，以及禁止 AI 账号直连 PostgreSQL 的网络与认证策略。

项目身份在控制脚本、adapter 和服务端之间统一为绝对路径的词法规范化结果：执行 `normpath`、Windows 大小写归一化和末尾分隔符裁剪，但保留 junction/symlink 拼写，不跟随 `resolve()`/`realpath()`。

卸载和旧半状态修复由 `tools/database-schema-bootstrap/uninstall.ps1` 负责：选择 `config` 或 `runtime` 会自动扩展为 `config,runtime,state`；`state` 单独选择只清理服务状态；`-Repair` 不重建凭据，`session-reap` 不会强杀无法完全验证身份的 orphan 进程。
