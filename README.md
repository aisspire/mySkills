﻿﻿﻿﻿﻿﻿﻿﻿# skills说明

### [`skills-editor`](.\.agents\skills\skills-editor)

1. `skill-safety-auditor`：安全审查及优化建议
2. `skill-optimizer`：优化落地
3. `skill-workflow-orchestrator`：将上面两者结合
3. `skill-writing-gate`：参考学习superpower的writing要求把关

### [`api-doc-generation`](.\.agents\skills\api-doc-generation)

面向前端联调的接口文档生成，要求从真实代码中核对接口类型、路径、请求参数、返回参数、字段约束和接口依赖关系，并裁掉复用 BO/DTO 中当前接口未使用的字段

### [`project-knowledge-map`](.\.agents\skills\project-knowledge-map)

生成项目架构，可辅助ai进行快速认知项目

### [`large-project-ai-guardrails`](.\.agents\skills\large-project-ai-guardrails)

约束模板

### [`project-norms`](.\.agents\skills\project-norms)

项目级习惯规范记忆模板，用于记录用户在特定项目中反复确认的测试、安全、提交、文档、汇报等协作习惯。使用时要求 AI 在被规范约束前先列出本次生效规范、来源、置信度和例外，避免把一次性指令或错误路径依赖偷偷固化为长期规则。

该 skill 与 `large-project-ai-guardrails` 分工不同：`project-norms` 管用户确认过的项目习惯和可纠偏记忆；`large-project-ai-guardrails` 管架构边界、禁改区、所有权和大项目探索规则。

### [`project-post-change-actions`](.\.agents\skills\project-post-change-actions)

项目修改后的收尾动作模板，例如生成标准 commit 建议、判断 README 是否需要更新，并按项目补充更多动作。

内置子 skill：`subskills/readme-generation`，用于在收尾流程中起草、改写或审核 README。复制 `project-post-change-actions` 时会一起带走；如果需要单独使用 README 生成能力，可以把该子目录复制到普通 skills 目录并作为 `readme-generation` 使用。

### [`ui-frontend-workflow`](.\.agents\skills\ui-frontend-workflow)

自包含的 UI / UX / 前端工作流 skill，触发 UI、前端页面、组件、视觉优化、响应式、可访问性或界面审查相关任务时使用。它按“设计 → 实现 → 审查”的流程工作：先产出产品与设计系统判断，再按项目技术栈落地实现，最后检查 Web/UI 质量、交互状态、可访问性和响应式问题。

该 skill 学习并融合了以下三个 skill 的经验，但可以单独复制使用，不要求同时复制原 skill：

- `frontend-design`
- `ui-ux-pro-max`
- `web-design-guidelines`

为尊重开源社区，已在 skill 内保留可获得的原始许可证副本：`licenses/frontend-design-LICENSE.txt` 和 `licenses/ui-ux-pro-max-LICENSE.txt`；`web-design-guidelines` 本地来源未包含单独 LICENSE 文件，因此在 `THIRD_PARTY_NOTICES.md` 中保留来源和作者信息。

### [functionality-check](.\.agents\skills\functionality-check)

功能检查

### [`database-schema-bootstrap`](.\.agents\skills\database-schema-bootstrap)

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

   `getskill` 会通过 `fzf` 搜索可用 skill，并复制到当前项目的 `.\.agents\skills` 目录。候选项分为两类：

   - `[skill]`：包含 `SKILL.md` 的单个 skill 目录。
   - `[set]`：顶层配套目录，目录自身不含 `SKILL.md`，但下面包含多个 skill。

   `fzf` 使用多选模式。直接按 Enter 会复制当前高亮项；使用 Tab 可以选择多个 `[skill]` 或 `[set]` 后批量复制。输入父目录名时，顶层 `[set]` 会优先出现在对应叶子 `[skill]` 前面，适合复制 `skills-editor`、`superpowers`、`pua` 这类配套技能目录。

## 规范与安装器说明

- `installer.bat` 是推荐入口，适合直接双击或在终端里运行。
- `src/install.ps1` 负责实际安装逻辑，包括检查 `fzf`、定位 PowerShell profile、写入托管代码块以及替换旧版函数。
- `profile.ps1` 是安装模板，安装器会从这个模板中自动提取函数名，并在写入前清理用户 profile 中同名的旧模板函数。
- `规范.md` 约束了 `profile.ps1` 的函数命名和结构：`getskill` 是唯一公开例外，其余函数必须使用 `GS-` 前缀，且必须保持扁平顶层定义，不能嵌套、不能设置别名。单个 skill 和配套 skill set 都通过 `getskill` 选择，不新增 `getskills` 等公开入口。
- 如果后续修改 `profile.ps1` 中的 helper 函数，优先保持安装器基于模板自动同步，不要回退到手写函数名列表。
