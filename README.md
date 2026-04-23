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

   `getskill` 会通过 `fzf` 搜索可用 skill，并复制到当前项目的 `.\.agents\skills` 目录。搜索过程中如果某个目录下已经存在 `SKILL.md`，会把该目录视为一个完整 skill，并停止继续向下递归，避免把 skill 内部子目录误当成独立 skill。

## 规范与安装器说明

- `installer.bat` 是推荐入口，适合直接双击或在终端里运行。
- `src/install.ps1` 负责实际安装逻辑，包括检查 `fzf`、定位 PowerShell profile、写入托管代码块以及替换旧版函数。
- `profile.ps1` 是安装模板，安装器会从这个模板中自动提取函数名，并在写入前清理用户 profile 中同名的旧模板函数。
- `规范.md` 约束了 `profile.ps1` 的函数命名和结构：`getskill` 是唯一公开例外，其余函数必须使用 `GS-` 前缀，且必须保持扁平顶层定义，不能嵌套、不能设置别名。
- 如果后续修改 `profile.ps1` 中的 helper 函数，优先保持安装器基于模板自动同步，不要回退到手写函数名列表。
