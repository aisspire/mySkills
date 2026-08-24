# database-schema-bootstrap v2 元数据网关

本目录是受信任的 PostgreSQL-only 服务端源码。安装后，每个 Windows 或 WSL/Linux 环境各自运行一个常驻本机 gateway；AI 侧 stdio adapter 只负责发现当前 Git 根、读取项目本地 `access.json`，并把固定请求转发到该环境的 loopback gateway。

## 运行时职责

gateway 每次请求重新加载并严格校验：

- `config/connections.json`：非秘密 PostgreSQL 连接字段；
- `config/secrets.json`：唯一允许保存明文密码的文件；
- `config/projects.json`：项目根、access 路径和中央 grant；
- `<git-root>/.agents/database-schema-bootstrap/access.json`：项目本地 enabled/active 状态。

访问必须同时满足中央 grant、项目 `enabled=true`、项目 ID、绑定 Git 根和固定 access 路径。未知、禁用、未授权、已删除或缺少 secret 的 connection ID 对外统一为“当前项目连接不可用”。配置未知字段、损坏 JSON 或不支持版本会失败关闭，不保留“最后一次正确配置”。

## RPC

服务只绑定 `127.0.0.1` 的随机端口：

- `GET /v2/health`
- `POST /v2/metadata`
- `POST /v2/control/shutdown`

所有端点都要求运行时随机 token。health 只返回协议版本、installation ID、PID 和随机 process identity，不访问 PostgreSQL。shutdown 只供控制程序使用，不是 MCP 工具。

metadata 请求只接受三种精确 schema：

```json
{
  "version": 2,
  "project_id": "9e526cf7-7781-4f41-a252-3c9f44e90c17",
  "project_root": "/workspace/example",
  "connection_id": "erp-prod-ro",
  "operation": "describe_table",
  "table": "users"
}
```

`list_databases` 与 `list_tables` 不接受 `table`；`describe_table` 必须包含一个未限定 PostgreSQL 标识符。任何额外字段、SQL、DSN、路径或密码都会被拒绝。

## PostgreSQL 边界

gateway 不建立持久连接池。每次请求将选中的非秘密配置与本次 secret 组合，创建一个连接并设置：

- 连接超时 10 秒；
- `statement_timeout=10000`；
- `lock_timeout=3000`；
- `SET TRANSACTION READ ONLY`。

固定查询只读取 `pg_catalog` 和 `information_schema`，返回数据库名、表名、字段、约束和索引；不读取业务行、样例值、行数或执行计划。

## 安全等级

WSL/Linux 安装器将 `config/` 设为 `0700`，`secrets.json` 设为 `0600`；服务发现组/其他用户权限时拒绝启动。Windows v2 继承当前用户 Profile ACL，不自动改写 DACL。

这是防误用软边界，不抵御同一操作系统用户下的恶意进程。需要强隔离时，应使用独立服务账号或远程凭据服务，并限制 AI 运行账号直接访问 PostgreSQL。

安装、控制、升级和卸载见 [tools/database-schema-bootstrap](../../tools/database-schema-bootstrap/README.md)。v1 的 Credential Manager 辅助脚本保留为 [`legacy-set-db-secret-v1.ps1`](legacy-set-db-secret-v1.ps1)，仅用于历史清理，不属于 v2 运行链路。
