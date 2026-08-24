# 全局 MCP 与项目路由

> v1 历史资料：仅用于追溯旧 profile/Credential Manager 架构，不属于正式 v2 skill 路由。

`database-schema-bootstrap` 由三个隔离职责组成：

1. `%USERPROFILE%\.codex\database-schema-bootstrap\service`：受信任的 PostgreSQL metadata service，读取 project profile、Credential Manager 和数据库驱动。
2. `%USERPROFILE%\.codex\database-schema-bootstrap\adapter`：AI 侧 stdio MCP adapter，只读取当前 Git 项目对应的服务状态并调用固定 loopback RPC。
3. `%USERPROFILE%\.codex\database-schema-bootstrap\control`：人工使用的 profile、凭据和服务控制脚本。

安装器把一个带安装 ID 的受管区块写入 `~/.codex/config.toml`。该区块同时包含全局 MCP server 与内联 `SessionStart` hook；不会改写 `hooks.json`。MCP 配置等价于：

```toml
[mcp_servers.database-schema-bootstrap]
command = "<configured python>"
args = ["-B", "<installed runtime>\\adapter\\mcp_server.py", "--timeout", "25"]
enabled_tools = ["list_databases", "list_tables", "describe_table"]
tool_timeout_sec = 30

[[hooks.SessionStart]]
matcher = "^(startup|resume|clear|compact)$"

[[hooks.SessionStart.hooks]]
type = "command"
command = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File <installed runtime>\\control\\db-schema-bootstrap.ps1 session-start"
timeout = 30
```

不要手工把 endpoint、密码、DSN、profile 路径或密码环境变量放入 MCP 配置。adapter 拒绝静态 endpoint，并且只允许 `127.0.0.1` 上由本项目状态文件声明的端口。

## 项目选择与服务状态

项目根由 Git 确认。adapter 的 `--timeout 25` 是一次工具调用的端到端单调时钟预算，而不是每个子步骤各自拥有 25 秒。Git 根发现最多使用当前剩余预算和 5 秒中的较小值；health 检查与实际 metadata RPC 分别使用当时剩余预算。预算耗尽时 adapter 以不含敏感信息的错误失败关闭。`tool_timeout_sec = 30` 与 hook 的 `timeout = 30` 为这一预算保留少量进程与调度余量。

adapter 每次工具调用都会：

1. 获取当前工作目录的 Git 根；无法获取时直接不可用。
2. 使用规范化根路径的 SHA-256 读取 `<installed runtime>/state/projects/<sha>.json`。
3. 校验 state 中的项目根、项目 ID、loopback endpoint、端口和实例令牌。
4. 带令牌请求 `/v1/health`，确认该服务实例仍属于同一项目。
5. 仅在所有校验通过后调用固定 metadata 操作。

服务以 `--port 0` 启动，由系统分配端口；每个项目都有独立端口和令牌。`/v1/health` 不访问数据库。`active-profile.json` 存在时必须使用其中指定 profile；仅在它不存在时自动使用 `default.json`；两者均不存在时 hook 不启动服务。

`SessionStart` 从 hook 事件 stdin 的 JSON 读取 `cwd`，并再次经 Git 根校验；事件中非空但无效的 `cwd` 会失败关闭。人工控制脚本的显式 `-ProjectPath` 优先，且在没有 hook stdin 时仍兼容当前目录。

## 失败处理

缺少 profile、Git 项目身份、状态文件、健康检查、凭据、驱动或 PostgreSQL 权限时：

1. 停止数据库操作并报告需要人工修复的非密钥信息。
2. 不要求用户粘贴密码。
3. 不改用 `psql`、Python、旧 CLI 或任何 SQL。
4. 使用控制脚本修复 profile 或服务后，再调用三项白名单 MCP 工具。
