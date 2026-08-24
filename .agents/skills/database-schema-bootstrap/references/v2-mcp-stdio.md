# v2 stdio MCP 与本机 gateway 路由

Codex 启动用户级 stdio adapter。adapter 不导入 psycopg 或 gateway 服务代码，也不读取中央 connections/secrets/projects。

每次工具调用都会：

1. 用 Git 确认当前项目根。
2. 严格读取固定路径 `access.json`，选择 enabled 的显式 ID 或 active。
3. 读取全局 `state/service.json`，校验 v2、loopback endpoint、端口、token、installation ID、PID 和 process identity。
4. 调用 `/v2/health` 验证同一身份；health 不访问 PostgreSQL。
5. state/health 不可用时，通过安装 runtime 的 venv 执行一次 `service ensure --hook`，然后只重试一次。
6. 把固定 v2 metadata 请求转发到 `127.0.0.1` gateway。

adapter 的 25 秒是 Git、ensure、health 和 metadata 的总预算；Codex MCP/hook 外层 timeout 为 30 秒。

## SessionStart

SessionStart hook 从事件 stdin 的 `cwd` 确认 Git 根。无 access 或无 enabled ID 时成功跳过，不启动 gateway。并发 hook 由全局文件锁收敛为一个 daemon；不配置 SessionEnd，因此服务持续运行，直到人工 stop、升级或卸载。

Codex 官方支持 stdio/Streamable HTTP MCP、`enabled_tools` 和 `config.toml` 内联 hooks：

- [MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
- [Hooks](https://learn.chatgpt.com/docs/hooks)

## 失败关闭

不得通过 MCP 配置、工具参数或环境变量提供 endpoint、token、配置路径、DSN 或密码。adapter 只接受受管 runtime 的动态 state，并且只转发三项固定 operation。
