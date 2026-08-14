# 全局 PostgreSQL MCP 运行时

本目录是 `database-schema-bootstrap` 的安装、控制与卸载入口。仓库是源码与升级来源；安装后的运行时始终位于：

```text
%USERPROFILE%\.codex\database-schema-bootstrap\
├─ adapter\
├─ service\
├─ control\
├─ state\projects\
├─ state\locks\
├─ logs\
└─ install-state.json
```

adapter 只暴露 `list_databases`、`list_tables`、`describe_table`。它不读取 profile、Credential Manager、数据库驱动或 PostgreSQL 参数；无法确认当前 Git 项目、找不到本项目状态、状态与健康令牌不匹配时会直接不可用，绝不回退到直连数据库或其他项目的服务。

## 安装与升级

在本仓库根目录执行。优先显式指定解释器；未指定时安装器只读取 `CODEX_PYTHON`，不会自行查找或切换 Python。

```powershell
.\tools\database-schema-bootstrap\install.ps1 -PythonPath 'C:\Path\to\python.exe'
```

安装器会：

- 复制 adapter、受信任服务和控制脚本到用户级运行时，不创建 junction；
- 安装服务与 adapter 的依赖；
- 在 `~/.codex/config.toml` 写入一个带安装 ID 的完整受管区块，包含全局 MCP 与内联 `SessionStart` hook；
- 保留所有非受管 TOML 内容，不修改 `hooks.json`。

重复执行同一命令即为升级。若发现重复区块、边界不完整、安装清单异常、受管区块或受管运行时文件被编辑，安装器会停止而不是覆盖它们。

离线或测试时可加 `-SkipDependencyInstall`；这不会安装依赖，之后应使用不带该开关的安装命令完成依赖安装。

## 项目 profile 与登录

在目标 Git 项目内操作，或通过 `-ProjectPath` 指明项目目录。profile 保存在项目自身：

```text
<项目根>/.agents/database-schema-bootstrap/profiles/<name>.json
```

```powershell
$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"

& $dbs profile add -ProjectPath . -Name default `
  -DatabaseHost db.example.test -Database app_database `
  -ConnectionDatabase postgres -DatabaseUser readonly_metadata_user

& $dbs profile login -ProjectPath . -Name default
& $dbs profile list -ProjectPath .
& $dbs profile use -ProjectPath . -Name default
& $dbs status -ProjectPath .
```

`profile login` 会以隐藏输入读取密码，并只写入当前 Windows 用户的 Credential Manager。密码不会作为参数、profile 字段、日志、MCP 输入或配置内容出现。

**中文交互向导**：不带参数运行 `profile add` 会进入交互模式，逐步提示输入主机、端口、数据库、用户和密码（隐藏输入、两次确认），一步完成保存与登录，最后询问是否立即设为活动 profile 并启动服务：

```powershell
& $dbs profile add -ProjectPath .
```

参数化调用（`-DatabaseHost ... -Database ... -DatabaseUser ...`）仍然可用，两种方式等价；交互向导同样不会把密码写入 profile、日志或命令参数。

删除项目下的 profile（含凭据与服务状态，中文交互选择）：

```powershell
& $dbs profile remove -ProjectPath .          # 列出并选择要删除的 profile
& $dbs profile remove -ProjectPath . -Name default   # 或直接指定名称
```

profile 名仅允许字母、数字、点、下划线和连字符；`active-profile`（不区分大小写）保留给 `active-profile.json`，拒绝发生在创建 profile 目录或文件之前。`profile add` 不会自动启动服务；`profile use` 仅重启该项目的服务实例。`profile use`、hook 与 adapter 都要求确认 Git 根目录，不能确认时失败关闭。

## 默认规则、并发与状态

服务选择规则固定为：

1. 若 `<项目根>/.agents/database-schema-bootstrap/profiles/active-profile.json` 存在，使用其中声明的 profile；该记录无效或目标 profile 缺失时失败关闭。
2. 仅在 `active-profile.json` 不存在时自动使用 `default.json`。
3. 两者均不存在时不启动服务，MCP adapter 不可用。

`SessionStart` hook 在每个会话开始时只处理当前 Git 项目。hook 事件的 JSON `cwd` 会先经 Git 根校验；非空但无效的事件路径失败关闭。人工调用时显式 `-ProjectPath` 优先，没有 hook stdin 时仍使用当前目录。

每个项目按规范化根路径的 SHA-256 获得独立状态文件、系统分配的 loopback 端口和随机实例令牌，因此多个项目可并行运行，不共享活动 profile 或端口。路径规范化使用绝对路径、词法 `normpath`、Windows 大小写归一化和末尾分隔符裁剪，保留 junction/symlink 拼写，不调用 `Path.resolve()` 或 `realpath()`。`/v1/health` 不访问数据库，并要求实例令牌。`SessionStart`、启动、停止、重启，以及 `profile use` 的“切换 profile + 重启”在同一项目排他锁与 25 秒生命周期预算内执行：已验证健康的实例会复用；并发 hook 只会观察到该实例，不会并发拉起第二个服务。不同项目可并行启动，安装清单的读改写另有全局锁，因此两边的 `service_state_files` 记录都会保留。

状态文件损坏、PID 缺失、PID 被复用或进程身份无法验证时，控制脚本只替换受管状态并启动新实例，绝不终止未知 PID。停止时发现 PID 存活但 ownership 校验失败，会把 PID、project root、project ID、state path、service script、实例令牌、命令行 SHA-256、进程创建时间、观察时间和原因追加到 `install-state.json` 的可选 `orphan_service_processes` 集合；当前实例的 `service_state_files` 记录也绑定同一实例令牌。`session-start` 会尝试安全回收当前项目的记录，失败不阻止新实例启动但保留记录；`session-reap` 返回 `Reaped`、`Stale` 或 `Unverified`，无法验证的 PID 不会被强杀。服务登记回收按 state path 与实例令牌精确匹配；旧版本 orphan 记录缺少令牌且当前 state 文件仍存在时会保守保留登记，避免删除复用同一路径的新实例记录。只有旧进程的命令行同时匹配已安装服务脚本、状态路径、项目 ID 和当前实例令牌时，才会停止不健康实例再重启。服务退出也仅删除仍由自己令牌拥有的状态，因此旧实例不会删掉新实例状态。

受管 MCP 配置固定把 adapter 设为 `--timeout 25` 的端到端调用预算，并设定 `tool_timeout_sec = 30`、`SessionStart` hook `timeout = 30`。adapter 会把剩余预算分配给 Git、health 和 metadata RPC；预算耗尽时失败关闭。

## 发布前 cwd 冒烟门禁

不连接 PostgreSQL 的双项目人工验证夹具位于仓库 `tests` 目录。它会创建两个没有 profile 的临时 Git 项目，为各自项目状态写入 token 保护的 loopback FakeService，并打印两条真实 Codex 客户端命令：

```powershell
.\tests\database-schema-bootstrap-cwd-smoke.ps1
```

保持脚本运行，在两个终端分别执行其输出的 `codex exec -C <project>` 命令。两次调用应分别只返回各自的 `cwd_smoke_project_a_table` 和 `cwd_smoke_project_b_table`。按 Enter 后，夹具只终止自身进程并只删除仍匹配自身 token 的状态文件。该门禁验证的是 adapter 实际 cwd 路由，不会建立 PostgreSQL 连接。

运行时不构成对同一 Windows 用户中恶意进程的绝对隔离。生产环境仍应使用受控服务账号、ACL、最小权限 PostgreSQL 账号，以及禁止 AI 运行账号直连数据库的网络策略。

## 卸载

先查看完整清理清单并交互选择类别：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1
```

`-All` 选择所有已验证的受管项，仍要求最后一次确认：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -All
```

自动化场景可使用显式确认开关：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -All -ConfirmAll
```

`config` 或 `runtime` 任一核心类别会在确认前自动扩展为 `config,runtime,state`，并打印扩展结果；这样不会先删 runtime/state 再留下受管 config。单独选择 `state` 只停止并清理项目服务状态，保留 runtime、`install-state.json` 和 Codex config：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -CodexHome $env:USERPROFILE\.codex -Categories state -ConfirmAll
```

核心清理发现受管 config/runtime/state 修改、越界或无法验证时默认整组中止。只有 `-ForceManaged -ConfirmForceManaged` 才允许删除修改的受管项；所有 state/runtime/`-All` 清理都会先回收当前安装记录的 orphan service process，仍有 `Unverified` 记录时保留完整兜底状态并中止。选中的 credentials 阶段会在停止服务或删除 config/runtime/state/profile 之前执行；`ERROR_NOT_FOUND` 可安全重试并视为成功，其他 Win32/ACL 错误会立即中止并保留这些受管文件与服务状态。

旧安装若 state 已丢失但 runtime 仍存在，`-Repair` 只报告并停止，不猜测 runtime 内容；若 state 缺失、runtime 已不存在且 config 中仍有边界完整的受管区块，`-Repair` 只移除该区块，不读取或重建数据库凭据：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -CodexHome $env:USERPROFILE\.codex -Repair -ConfirmAll
```

需要人工回收当前 Git 项目的已记录 orphan 时：

```powershell
& $dbs session-reap -ProjectPath .
```

普通卸载与 `-All` 都保留被编辑的受管区块、哈希不匹配的文件、未记录 profile、未由本工具记录的凭据、源码仓库和项目 skill 源码。只有 `-All -ForceManaged` 且再次确认后，才会按完整受管边界删除已编辑的项：

```powershell
.\tools\database-schema-bootstrap\uninstall.ps1 -All -ForceManaged
```

## 故障处理

- `Python is not configured`：重新运行安装器并提供 `-PythonPath`，或设置 `CODEX_PYTHON`；随后重跑安装命令。
- `current path is not inside a Git worktree`：从项目 Git 根目录运行控制命令，或使用正确的 `-ProjectPath`；随后执行 `& $dbs status -ProjectPath <项目>`。
- `No active database metadata service`：先添加并选择该项目 profile，再重开 Codex 会话或执行 `profile use`。
- 服务启动后仍不可用：运行 `& $dbs status -ProjectPath <项目>`，检查 `%USERPROFILE%\.codex\database-schema-bootstrap\logs`；不要改用 `psql`、Python 或任意 SQL 直连。
