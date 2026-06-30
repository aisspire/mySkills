﻿﻿﻿﻿﻿﻿﻿﻿# skills说明

### [`ai-dev-workflow`](.\.agents\skills\ai-dev-workflow)

**推荐使用。** 这是新的 AI 辅助开发工作流 skill set，用于承接部分旧 skill 的职责。

新的 AI 辅助开发工作流 skill set，便于整体迁移发布。内部 skill 保持独立触发，不会每次加载整套内容。

1. `skill-maintenance`：统一 skill 创建、审查、优化、合并、writing 合规、多轮复审和发布确认流程。
2. `project-docs-workflow`：维护文档驱动开发体系，包含 `docs/index.md`、`project.md`、`features/`、`api/`、`data/`、`tests/`、`architecture/`、`flows/`、`adr/`、`ai/` 模板。
3. `project-closeout`：开发后收尾，检查 docs/README 是否需要更新，汇总验证状态，并给出中文 Conventional Commit 建议。
4. `project-rules-maintainer`：记录项目级 AI 规则候选和反复问题，生成 `AGENTS.md` 建议补丁，不直接修改 `AGENTS.md`。
5. `api-doc-generation`：保留为独立重型接口全量核对能力，需要从真实 controller/router/service/DTO/VO/BO 使用链路核对时触发。
6. `backlog-capture`：只在用户明确要求记录未来功能或暂不实现功能时，维护 `docs/BACKLOG.md` 的一句话钩子，不更新 `docs/index.md`。

### [`skills-editor`](.\.agents\skills\skills-editor)

**建议弃用。** 原因：职责已合并到 `ai-dev-workflow/skill-maintenance`，新入口保留了多轮审查、安全风险、writing 合规、When to Use / When NOT to Use 结构和发布确认机制，避免四个子 skill 之间重复触发和维护成本过高。

1. `skill-safety-auditor`：安全审查及优化建议
2. `skill-optimizer`：优化落地
3. `skill-workflow-orchestrator`：将上面两者结合
3. `skill-writing-gate`：参考学习superpower的writing要求把关

### [`api-doc-generation`](.\.agents\skills\api-doc-generation)

**旧路径建议弃用，功能不弃用。** 原因：该能力已复制到 `ai-dev-workflow/api-doc-generation` 并保持独立重型核对定位。后续迁移发布时优先使用新套装内入口，减少根目录重复 skill；需要真实 controller/router/service/DTO/VO/BO 全链路核对时仍应使用这个能力。

面向前端联调的接口文档生成，要求从真实代码中核对接口类型、路径、请求参数、返回参数、字段约束和接口依赖关系，并裁掉复用 BO/DTO 中当前接口未使用的字段

### [`project-knowledge-map`](.\.agents\skills\project-knowledge-map)

**建议弃用。** 原因：一次性生成大型项目知识地图容易变重、变旧，也不符合当前“索引 + 功能文档 + 接口文档 + 数据文档 + 测试文档 + 架构文档 + 流程文档 + ADR”的按需读取思路。后续由 `ai-dev-workflow/project-docs-workflow` 承接文档体系 bootstrap、索引维护和局部更新。

生成项目架构，可辅助ai进行快速认知项目

### [`large-project-ai-guardrails`](.\.agents\skills\large-project-ai-guardrails)

**建议弃用。** 原因：稳定的大项目边界和协作硬规则更适合写进项目级 `AGENTS.md`，不适合作为每次额外触发的 skill。候选规则、反复问题和补丁建议由 `ai-dev-workflow/project-rules-maintainer` 维护。

约束模板

### [`project-norms`](.\.agents\skills\project-norms)

**建议弃用。** 原因：原目标是补充 `AGENTS.md`，但自动记忆不够频繁且容易把一次性偏好固化。新方案改为 `ai-dev-workflow/project-rules-maintainer`：只记录候选规则和反复问题，生成 `AGENTS.md` 建议补丁，不直接修改或静默生效。

项目级习惯规范记忆模板，用于记录用户在特定项目中反复确认的测试、安全、提交、文档、汇报等协作习惯。使用时要求 AI 在被规范约束前先列出本次生效规范、来源、置信度和例外，避免把一次性指令或错误路径依赖偷偷固化为长期规则。

该 skill 与 `large-project-ai-guardrails` 分工不同：`project-norms` 管用户确认过的项目习惯和可纠偏记忆；`large-project-ai-guardrails` 管架构边界、禁改区、所有权和大项目探索规则。

### [`project-post-change-actions`](.\.agents\skills\project-post-change-actions)

**建议弃用。** 原因：开发后收尾已经扩展为“根据文档索引检查更新 docs、判断 README、说明验证状态、给出 commit 建议”的闭环，旧入口只覆盖 post-change checklist。后续由 `ai-dev-workflow/project-closeout` 承接；README 更新能力仍可作为子能力保留或按需单独抽出。

项目修改后的收尾动作模板，例如生成标准 commit 建议、判断 README 是否需要更新，并按项目补充更多动作。

内置子 skill：`subskills/readme-generation`，用于在收尾流程中起草、改写或审核 README。复制 `project-post-change-actions` 时会一起带走；如果需要单独使用 README 生成能力，可以把该子目录复制到普通 skills 目录并作为 `readme-generation` 使用。

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

**保留。** 原因：数据库真实 schema 发现是独立高风险事实核对能力，本轮明确不讨论、不合并。

数据库结构获取





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
