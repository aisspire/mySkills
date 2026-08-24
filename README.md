# README

## skills说明

### [`ai-dev-workflow`](.\.agents\skills\ai-dev-workflow)

**推荐使用。** 这是新的 AI 辅助开发工作流 skill set，用于承接部分旧 skill 的职责。

新的 AI 辅助开发工作流 skill set，便于整体迁移发布。内部 skill 保持独立触发，不会每次加载整套内容。

1. `skill-maintenance`：统一 skill 创建、审查、优化、合并、writing 合规、多轮复审和发布确认流程。
2. `project-docs-workflow`：维护文档驱动开发体系，包含 `docs/index.md`、`project.md`、`features/`、`api/`、`data/`、`tests/`、`architecture/`、`flows/`、`adr/`、`ai/` 模板。
3. `project-closeout`：开发后收尾，检查 docs/README 是否需要更新，汇总验证状态，并给出中文 Conventional Commit 建议。
4. `project-rules-maintainer`：记录项目级 AI 规则候选和反复问题，生成 `AGENTS.md` 建议补丁，不直接修改 `AGENTS.md`。
5. `api-doc-generation`：保留为独立重型接口全量核对能力，需要从真实 controller/router/service/DTO/VO/BO 使用链路核对时触发。
6. `backlog-capture`：只在用户明确要求记录未来功能或暂不实现功能时，维护 `docs/BACKLOG.md` 的一句话钩子，不更新 `docs/index.md`。

### [`ui-frontend-workflow`](.\.agents\skills\ui-frontend-workflow)

**保留。** 原因：UI / UX / 前端工作流是独立领域能力，不参与本轮合并。

自包含的 UI / UX / 前端工作流 skill，触发 UI、前端页面、组件、视觉优化、响应式、可访问性或界面审查相关任务时使用。它按“设计 → 实现 → 审查”的流程工作：先产出产品与设计系统判断，再按项目技术栈落地实现，最后检查 Web/UI 质量、交互状态、可访问性和响应式问题。

该 skill 学习并融合了以下三个 skill 的经验，但可以单独复制使用，不要求同时复制原 skill：

- `frontend-design`
- `ui-ux-pro-max`
- `web-design-guidelines`

为尊重开源社区，已在 skill 内保留可获得的原始许可证副本：`licenses/frontend-design-LICENSE.txt` 和 `licenses/ui-ux-pro-max-LICENSE.txt`；`web-design-guidelines` 本地来源未包含单独 LICENSE 文件，因此在 `THIRD_PARTY_NOTICES.md` 中保留来源和作者信息。

### [`experience-capture`](.\.agents\skills\experience-capture)

**暂不弃用，冻结观察。** 原因：当前体验是记录内容偏多偏杂，但本轮尚未设计替代方案，先不迁移、不删除。

开发经验沉淀 skill，用于在用户要求总结经验、复盘、写到 docs，或一次会话中出现多轮修改、失败返工、跨模块排查时，将过程、问题路由、尝试记录和可复用结论追加到 `docs/experience/<主题>.md`。指定已有文档时会先读取历史内容，再按相似问题追加，不删除旧经历。

### [`functionality-check`](.\.agents\skills\functionality-check)

**保留。** 原因：用于后端功能路径理解和完整性检查，当前没有被新套装完全替代。

功能检查

### [`database-schema-bootstrap`](.\.agents\skills\database-schema-bootstrap)

用于在写 SQL、迁移、字段排查或 CRUD 前读取真实 PostgreSQL schema。AI 只可调用 `list_databases`、`list_tables`、`describe_table`，不得直连数据库、读取密码或执行任意 SQL。

v2 在每个运行环境中安装一个独立常驻 gateway：Windows 与 WSL 分别拥有自己的 runtime、venv、状态和配置，不共享进程或密码。项目只保存本地 `access.json`，中央配置按 `project_id + connection_id` 授权；项目 `enabled` 与 `active` 只控制本地可用性和默认选择。

Windows 与 WSL/Linux 安装命令：

```powershell
.\tools\database-schema-bootstrap\install.ps1 -PythonPath 'C:\Path\to\python.exe'
```

```bash
./tools/database-schema-bootstrap/install.sh --python /path/to/python3
```

安装器要求现有 Python 3.11+，只在运行时内创建 `.venv`，不调用 `sudo`、`apt` 或全局 pip。它只维护 `~/.codex/config.toml` 中自己的 MCP/`SessionStart` 区块，不注册 `SessionEnd`，运行态始终引用专用 venv。

v2 不迁移 v1 profile 或 Credential Manager 凭据。检测到 v1 时安装会停止，必须先人工运行 `legacy-uninstall-v1.ps1` 完整卸载，再重新录入连接和项目授权。

快速开始：

```powershell
.\tools\database-schema-bootstrap\install.ps1 -PythonPath 'C:\Path\to\python.exe'

$dbs = "$env:USERPROFILE\.codex\database-schema-bootstrap\control\db-schema-bootstrap.ps1"
& $dbs connection add erp-ro --host db.example.test --database erp --user metadata_reader
& $dbs project init --project .
& $dbs project grant erp-ro --project .
& $dbs project enable erp-ro --project .
& $dbs project use erp-ro --project .

# 新开 Codex 会话后使用 list_databases / list_tables / describe_table
```

WSL/Linux 使用同一控制核心：

```bash
$CODEX_HOME/database-schema-bootstrap/control/db-schema-bootstrap.sh connection list
```

密码通过隐藏输入写入 runtime 的 `config/secrets.json`。这是面向同一用户环境的防误用软边界，不抵御同用户恶意进程；密码不会进入命令参数、环境变量、日志、状态或 MCP 请求。`enabled=false` 也不是保密机制。

普通卸载保留连接、秘密和项目 access；`--all`/`-All -ConfirmAll` 才删除这些不可恢复数据。详细说明见 [安装与控制指南](./tools/database-schema-bootstrap/README.md)、[服务端说明](./mcp/database-schema-bootstrap/README.md) 和 [v2 架构](./docs/architecture/database-schema-bootstrap-v2.md)。v2 skill 已正式发布到 [database-schema-bootstrap/SKILL.md](./.agents/skills/database-schema-bootstrap/SKILL.md)，当前 writing 等级为 `static-compliant`。





## codex使用建议

在根目录`.codex`文件夹中，存放了两个配置文件

`config.toml`用来指定python目录，这个适合放在项目级目录下

另外，用户级目录可以添加下面的内容来规范python

```toml
[shell_environment_policy]
set = {PYTHONUTF8 = "1",PYTHONIOENCODING = "utf-8",CODEX_PYTHON = "D:\\Anaconda\\python.exe"}
```

`AGENTS.md`用来进行规范，这里主要是减少报错占用token，并规范报错格式，这个适合放在用户级目录下

# 安装

﻿推荐配合[`fzf`](https://github.com/junegunn/fzf)进行使用

推荐优先使用仓库内置安装器，它会自动完成 `fzf` 检查、`profile.ps1` 模板注入以及旧函数替换。

使用步骤（win11powershell）

1. 安装`fzf`

   ```powershell
   winget install fzf
   ```

2.  克隆当前项目

   ```powershell
   git clone git@github.com:aisspire/mySkills.git
   # git clone https://github.com/aisspire/mySkills.git
   ```

3. 在仓库根目录执行安装器

   直接运行批处理入口：

   ```powershell
   .\installer.bat
   ```

   如果你想手动调用 PowerShell 安装脚本，也可以执行：

   ```powershell
   powershell -NoProfile -ExecutionPolicy Bypass -File .\src\install.ps1 -RepoRoot .
   ```

4. 重启 PowerShell

   安装器会把托管代码块写入当前用户的 PowerShell profile，并将模板中的 `$skillsDir` 自动替换为当前仓库路径。

5. 在你想要添加技能的项目根目录执行 `getskill`

   `getskill` 会通过 `fzf` 搜索可用 skill，并默认以目录 junction 的形式链接到当前项目的 `.\.agents\skills` 目录。候选项分为两类：

   - `[skill]`：包含 `SKILL.md` 的单个 skill 目录。
   - `[set]`：顶层配套目录，目录自身不含 `SKILL.md`，但下面包含多个 skill。

   `fzf` 使用多选模式。直接按 Enter 会链接当前高亮项；使用 Tab 可以选择多个 `[skill]` 或 `[set]` 后批量链接。输入父目录名时，顶层 `[set]` 会优先出现在对应叶子 `[skill]` 前面，适合安装 `skills-editor`、`superpowers`、`pua` 这类配套技能目录。

   默认链接使用 Windows 目录 junction（等价于 `mklink /J`），比目录符号链接（`mklink /D`）更适合本地 skill 目录，因为通常不需要管理员权限或开发者模式。链接模式便于后续更新：仓库内 skill 更新后，项目里的链接会直接看到新内容。

   如果需要保留旧版复制行为，执行：

   ```powershell
   getskill -c
   ```

   `-c` 会把选中的 skill 或 set 复制到当前项目，后续不会跟随仓库内源目录更新。

## 规范与安装器说明

- `installer.bat` 是推荐入口，适合直接双击或在终端里运行。
- `src/install.ps1` 负责实际安装逻辑，包括检查 `fzf`、定位 PowerShell profile、写入托管代码块以及替换旧版函数。
- `profile.ps1` 是安装模板，安装器会从这个模板中自动提取函数名，并在写入前清理用户 profile 中同名的旧模板函数。
- `规范.md` 约束了 `profile.ps1` 的函数命名和结构：`getskill` 是唯一公开例外，其余函数必须使用 `GS-` 前缀，且必须保持扁平顶层定义，不能嵌套、不能设置别名。单个 skill 和配套 skill set 都通过 `getskill` 选择，不新增 `getskills` 等公开入口。
- 如果后续修改 `profile.ps1` 中的 helper 函数，优先保持安装器基于模板自动同步，不要回退到手写函数名列表。
