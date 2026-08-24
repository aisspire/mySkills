# database-schema-bootstrap v2 安装与控制

v2 把“每项目一个 Windows 服务”改为“每运行环境一个本机 gateway”。Windows 与 WSL/Linux 必须分别安装，各自使用独立 runtime、`.venv`、明文 secrets、项目登记和进程；即使两边指向同一源码目录，也不会共享授权身份。

运行时固定在：

```text
$CODEX_HOME/database-schema-bootstrap/
├─ .venv/
├─ adapter/
├─ service/
├─ control/
├─ config/
│  ├─ connections.json
│  ├─ secrets.json
│  └─ projects.json
├─ state/
│  ├─ service.json
│  └─ service.lock
├─ logs/
└─ install-state.json
```

## 安装与升级

要求已有 Python 3.11+。安装器按显式参数、`CODEX_PYTHON`、当前启动解释器的顺序选择 Python；不会安装/升级系统 Python，不调用 `sudo`、`apt` 或全局 pip。

Windows：

```powershell
.\tools\database-schema-bootstrap\install.ps1 `
  -PythonPath 'C:\Path\to\python.exe'
```

WSL/Linux：

```bash
./tools/database-schema-bootstrap/install.sh --python /path/to/python3
```

安装器在 staging runtime 中创建专用 venv，安装 `mcp` 与 `psycopg`，完成 self-check 后才停止旧 daemon 并替换 runtime。升级保留 `config/` 和日志；staging 失败时旧 v2 runtime 与 Codex 配置保持不变。

`--skip-dependency-install` / `-SkipDependencyInstall` 仅用于离线测试。生成的 `install-state.json` 会标记 `incomplete`，adapter、hook 与 `service ensure` 都拒绝启动，不能作为可用安装。

安装器只维护 `~/.codex/config.toml` 中带 installation ID 的区块：

- MCP `command` 固定指向 runtime venv；
- 只启用 `list_databases`、`list_tables`、`describe_table`；
- 注册同步 `SessionStart service ensure --hook`；
- 不注册 `SessionEnd`；
- 不写 `hooks.json` 或其他 Codex 配置。

这些配置与当前 OpenAI 官方说明一致：Codex 支持本地 stdio MCP、`enabled_tools` 白名单和 `config.toml` 内联 hook。[MCP](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) / [Hooks](https://learn.chatgpt.com/docs/hooks)

### v1 边界

v2 不迁移 v1 profile、`credential_target`、`target_tables`、`active-profile` 或 Credential Manager 密码。只要发现 v1 install-state、旧受管区块或无明确所有权的旧 runtime，安装立即停止。

v1 只存在于 Windows/Credential Manager 架构。Windows 用户必须先记录需要重新录入的非秘密连接字段，再人工审查并执行历史全量卸载：

```powershell
.\tools\database-schema-bootstrap\legacy-uninstall-v1.ps1 -All -ConfirmAll
```

这一步会删除旧凭据和项目 profile，不可由 v2 安装器自动代办。如果仅报告 `config.toml` 受管区块已修改，先备份该文件并确认标记边界内没有其他个人配置，再使用强制受管清理：

```powershell
$cfg = "$env:USERPROFILE\.codex\config.toml"
Copy-Item -LiteralPath $cfg -Destination "$cfg.before-dsb-v1-uninstall.bak"

.\tools\database-schema-bootstrap\legacy-uninstall-v1.ps1 `
  -All -ConfirmAll -ForceManaged

# 根据提示精确输入：FORCE DELETE
```

`-ForceManaged` 只放宽对已修改受管项的哈希保护；`config.toml` 仍按唯一、完整且 installation ID 匹配的标记区块删除，不会删除整个文件。`-Repair` 只适用于 install-state 已丢失、runtime 已不存在且仍有完整受管配置区块的半状态，不能用于普通哈希漂移。

WSL/Linux 没有 v1 legacy 卸载命令。确认 WSL 使用自己的 `${CODEX_HOME:-$HOME/.codex}`，不要指向 Windows 用户 Profile，然后直接安装 WSL/Linux v2：

```bash
printf 'WSL CODEX_HOME=%s\n' "${CODEX_HOME:-$HOME/.codex}"
./tools/database-schema-bootstrap/install.sh --python /path/to/python3
```

## 控制入口

安装后入口：

Windows PowerShell：

```powershell
$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"
```

WSL/Linux：

```bash
dbs="${CODEX_HOME:-$HOME/.codex}/database-schema-bootstrap/control/db-schema-bootstrap.sh"
```

两个包装器都只启动 runtime venv 中的 `control.py`。

### 连接

```text
connection add|list|show|update|set-password|remove
```

添加连接时，非秘密字段可通过参数提供，密码始终由隐藏输入读取两次：

Windows PowerShell：

```powershell
& $dbs connection add erp-prod-ro `
  --host db.example.test `
  --port 5432 `
  --database erp `
  --connection-database postgres `
  --schema public `
  --user metadata_reader
```

WSL/Linux：

```bash
"$dbs" connection add erp-prod-ro \
  --host db.example.test --port 5432 \
  --database erp --connection-database postgres \
  --schema public --user metadata_reader
```

Windows PowerShell 其他连接命令：

```powershell
& $dbs connection list
& $dbs connection show erp-prod-ro
& $dbs connection update erp-prod-ro --host new-db.example.test
& $dbs connection set-password erp-prod-ro
& $dbs connection remove erp-prod-ro --confirm erp-prod-ro
```

WSL/Linux 其他连接命令：

```bash
"$dbs" connection list
"$dbs" connection show erp-prod-ro
"$dbs" connection update erp-prod-ro --host new-db.example.test
"$dbs" connection set-password erp-prod-ro
"$dbs" connection remove erp-prod-ro --confirm erp-prod-ro
```

`list`、`show` 和所有 status 输出只显示 `<redacted>`，不会输出密码。删除仍被任何项目 grant 的 connection 会拒绝；解除全部 grant 后仍要求精确 ID 确认。

### 项目

项目配置固定为：

```text
<git-root>/.agents/database-schema-bootstrap/access.json
```

初始化会生成随机 UUID，并把 `/.agents/database-schema-bootstrap/` 写入 Git 实际 `info/exclude`。文件完全本地，不应提交。

Windows PowerShell：

```powershell
& $dbs project init --project .
& $dbs project grant erp-prod-ro --project .
& $dbs project enable erp-prod-ro --project .
& $dbs project use erp-prod-ro --project .
& $dbs project status --project .
```

WSL/Linux：

```bash
"$dbs" project init --project .
"$dbs" project grant erp-prod-ro --project .
"$dbs" project enable erp-prod-ro --project .
"$dbs" project use erp-prod-ro --project .
"$dbs" project status --project .
```

`grant` 新增 connection ID 时默认 `enabled=false`。启用第一个 ID 会自动设为 active；禁用、撤销当前 active 会清空 active。显式 MCP `connection_id` 必须已启用；省略时使用 active。

Windows PowerShell 项目维护命令：

```powershell
& $dbs project disable erp-prod-ro --project .
& $dbs project revoke erp-prod-ro --project .
& $dbs project rebind --project 'E:\code\new-root' --confirm-old-root
& $dbs project remove --project . --confirm '<project-uuid>'
```

WSL/Linux 项目维护命令：

```bash
"$dbs" project disable erp-prod-ro --project .
"$dbs" project revoke erp-prod-ro --project .
"$dbs" project rebind --project /workspace/new-root --confirm-old-root
"$dbs" project remove --project . --confirm '<project-uuid>'
```

移动项目后使用 `rebind`。旧根仍存在时必须额外确认。每个 clone/worktree、Windows 环境和 WSL 环境都应独立 `project init`。

### 服务

Windows PowerShell：

```powershell
& $dbs service ensure
& $dbs service start
& $dbs service status
& $dbs service stop
```

WSL/Linux：

```bash
"$dbs" service ensure
"$dbs" service start
"$dbs" service status
"$dbs" service stop
```

`SessionStart` 使用 `service ensure --hook`。无 Git 根、无 access 文件或无 enabled ID 时直接成功跳过，不启动 daemon。多个并发 hook 使用 `state/service.lock` 收敛为一个进程。

服务以随机端口绑定 `127.0.0.1`，stdout/stderr 只写 runtime 日志。停止只调用 token 保护的 `/v2/control/shutdown`；状态损坏、health 身份不一致或 PID 无法验证时不会强杀，而是记录 orphan，并阻止破坏性升级/卸载。

## 明文秘密与软边界

`config/secrets.json` 是唯一允许保存明文密码的位置。密码不会进入：

- 命令参数或环境变量；
- `connections.json`、`projects.json`、access 或 install/service state；
- 日志、MCP 请求、MCP 输出。

WSL/Linux 配置目录为 `0700`，secrets 为 `0600`；权限变宽时服务拒绝启动。Windows 继承当前用户 Profile ACL，v2 不自动改写 DACL。

该设计只能防误用，不抵御同一用户下的恶意进程。`enabled=false` 也不是 connection ID 的保密措施。强隔离需要独立服务账号或远程凭据服务。

## 卸载

先打印清单：

Windows PowerShell：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -InventoryOnly
```

WSL/Linux：

```bash
./tools/database-schema-bootstrap/uninstall.sh --inventory-only
```

普通卸载移除受管 Codex 区块、程序、venv、state 和 logs，但保留 connections、secrets、项目登记和项目 access：

Windows PowerShell：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -Confirm
```

WSL/Linux：

```bash
./tools/database-schema-bootstrap/uninstall.sh --confirm
```

只有完整清理才删除不可恢复数据：

Windows PowerShell：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -All -ConfirmAll
```

WSL/Linux：

```bash
./tools/database-schema-bootstrap/uninstall.sh --all --confirm-all
```

删除 secrets、connections、项目登记或 access 前必须审查 inventory。卸载只删除清单记录、仍在 runtime/project 边界内且未修改的受管文件；修改项和未知文件默认保留并报告。无法验证的存活 daemon/orphan 会阻止 runtime/state 删除。

## 验证

Windows PowerShell 标准库测试：

```powershell
python -B -m unittest tests.test_database_schema_bootstrap -v
```

WSL/Linux 标准库测试：

```bash
python3 -B -m unittest tests.test_database_schema_bootstrap -v
```

完整门禁必须使用安装器新建且依赖完整的 venv，以覆盖 MCP SDK 工具枚举。

Windows PowerShell：

```powershell
$venvPython = "$env:USERPROFILE\.codex\database-schema-bootstrap\.venv\Scripts\python.exe"
& $venvPython -B -m unittest tests.test_database_schema_bootstrap -v
```

WSL/Linux：

```bash
"${CODEX_HOME:-$HOME/.codex}/database-schema-bootstrap/.venv/bin/python" \
  -B -m unittest tests.test_database_schema_bootstrap -v
```

双项目真实 Codex cwd 冒烟：

Windows PowerShell：

```powershell
.\tests\database-schema-bootstrap-cwd-smoke.ps1
```

WSL/Linux：

```bash
./tests/database-schema-bootstrap-cwd-smoke.sh
```

夹具只启动一个 FakeGateway，同时给两个临时 Git 项目分配不同 project/connection ID，并打印两条 `codex exec -C` 命令。两个结果必须分别返回自己的 marker 表名。

真实 PostgreSQL 发布验收只能通过三个 MCP 工具完成；禁止用 `psql` 或 Python 直连替代。Windows 普通用户与 WSL 普通用户都完成安装、启动、复用、停止、升级和卸载门禁前，不宣称跨平台发布完成。
