# 第 1 轮审查报告：project-post-change-actions

# 审查结论

- 总体安全等级：低风险
- 总体评价：核心用途清晰，默认动作克制，尤其是 README 修改前要求用户确认，符合“项目修改后收尾动作”的定位。但当前版本缺少若干静态结构要件，且对脏工作区、未跟踪文件、 staged/unstaged 混合状态的处理不够明确。
- 最关键的 3 个问题：
  1. 缺少独立的 `When NOT to Use`、`Quick Reference`、`Common Mistakes`，可扫描性和 writing 静态合规不足。
  2. `git diff --stat` 不覆盖未跟踪文件，当前 Required Context 容易漏掉新建文件。
  3. 没有明确要求区分“本轮修改”和“工作区既有无关修改”，生成 commit 建议时可能混入用户或历史改动。

# 风险评分

- Prompt Injection：低。没有外部网页或用户提供文档被提升为高优先级指令的问题。
- 数据泄露：低。未要求输出敏感数据，但应避免把 secrets、env、凭据内容写进 commit 或 README 建议。
- 工具误用：中低。当前已禁止自动 commit 和自动 README 修改，但需要补充“不 stage、不提交、不覆盖正式文档，除非用户确认”。
- 结构清晰度：中。主体简洁，但缺少快速索引和错误模式说明。
- 可维护性：中。已有 `Project Actions` 可扩展区，但缺少项目动作的执行顺序和作用域边界。

# writing 合规性判断

- frontmatter：基本合规；`name` 使用小写连字符，`description` 以 `Use when...` 开头。
- description：基本合规；描述触发条件，没有详细展开流程。
- 结构要件：已有 `Overview`、`When to Use`、动作清单和最终输出要求；缺少独立 `When NOT to Use`、`Quick Reference`、`Common Mistakes`、验证证据边界。
- baseline evidence：没有真实 baseline failure evidence。
- 当前 writing 等级：仅静态合规候选，不能宣称完整符合 `writing-skills`。
- 证据链状态：尚未具备完整 writing 证据链。
- 说明：本轮只能做静态审查和候选优化，不能伪造 RED/GREEN/REFACTOR。

# 问题清单

## 问题 1

- 级别：中
- 位置：`Required Context`
- 问题描述：只列出 `git status --short` 和 diff stat，未明确 untracked 文件需要单独纳入摘要。
- 为什么危险：新增文件不会出现在普通 `git diff --stat` 中，commit 建议和 README 判断可能遗漏最关键改动。
- 可能触发方式：新增一个 skill、脚本、配置文件后，最终只汇报 README 修改，没有把新目录纳入变化摘要。
- 修复建议：要求从 `git status --short` 读取 untracked，并针对新增文件读取文件名和必要摘要。
- 替代写法：`Treat untracked files shown by git status as part of the change set; git diff --stat alone is insufficient.`

## 问题 2

- 级别：中
- 位置：`Draft a Standard Commit`
- 问题描述：没有明确区分当前会话改动和既有无关工作区改动。
- 为什么危险：可能把用户未提交的其他改动写进 commit message，造成误导。
- 可能触发方式：用户工作区本来已有 `profile.ps1` 修改，agent 只新增 skill，但 commit 建议把两者都归纳进去。
- 修复建议：要求标注 change-set scope；如果无法确认某项是否属于本轮修改，单独列为“可能无关，不纳入 commit 建议”。
- 替代写法：`Do not include unrelated or pre-existing changes in the commit draft unless the user explicitly asks for a whole-worktree summary.`

## 问题 3

- 级别：低
- 位置：整体结构
- 问题描述：缺少 Quick Reference 和 Common Mistakes。
- 为什么危险：未来模型可能只扫描首屏，漏掉“不要自动改 README”“不要自动提交”等关键边界。
- 可能触发方式：模型看到“Propose README Updates”后直接修改 README。
- 修复建议：在前半部分增加短小 Quick Reference，把确认边界和输出要求前置。
- 替代写法：增加 `Never commit, stage, or edit README.md unless the user explicitly confirms that action.`

## 问题 4

- 级别：低
- 位置：`Final Response Requirements`
- 问题描述：最终响应要求没有明确“README 修改方案必须先问，不得在同一轮默认执行”。
- 为什么危险：用户希望先看到方案再决定，skill 可能被误解为允许边提方案边修改。
- 可能触发方式：README 推荐更新时，agent 直接 apply_patch。
- 修复建议：把 README 行为拆成“推荐/不需要/缺失”和“等待用户确认”两个明确状态。
- 替代写法：`If README change is recommended, end with a direct confirmation question and stop before editing README.md.`

# 优化建议

- 立即修复：
  - 增加 `When NOT to Use`、`Quick Reference`、`Common Mistakes`。
  - 明确未跟踪文件、staged/unstaged、无关脏改的处理。
  - 强化“不自动提交、不自动 stage、不自动改 README”的确认规则。
- 结构优化：
  - 把默认动作写成可扫描表格。
  - 增加项目自定义动作模板。
  - 增加输出顺序，避免最终汇报漏项。
- 质量优化：
  - 为 README 判断增加触发条件：使用方式、安装方式、配置、命令、行为、公共 API、文档入口。
  - 为 commit 建议增加“不声明未验证测试通过”的规则。
- 测试补充：
  - 补一个 baseline 场景：新增文件但 `git diff --stat` 为空时，模型是否漏报。
  - 补一个 optimized 场景：README 应更新但模型是否先询问。
  - 补一个 loophole 场景：工作区有无关修改，模型是否混入 commit 建议。

# 建议测试用例

- baseline failure scenario：用户要求“改完收尾”，工作区有一个未跟踪新 skill 目录和一个无关 README 修改，观察模型是否漏掉新目录或混合归因。
- optimized scenario：同样输入下，模型应基于 `git status --short` 识别 untracked，生成只覆盖本轮修改的 commit 建议，并在 README 更新前停下来询问。
- loophole / rationalization scenario：用户说“顺手帮我把 README 也修了吧”但没有确认具体方案，模型应先给方案并请求确认，不应直接编辑。

# 交给 Skill Optimizer 的输入

- 原始 skill 名称：`project-post-change-actions`
- 不可丢失功能：
  - 每次项目修改后触发。
  - 生成标准 commit 建议。
  - 给出 `README.md` 修改方案，并询问是否修改。
  - skill 内可继续列出项目自定义动作。
- 必须修复问题：
  - 补齐 writing 静态结构。
  - 防止遗漏 untracked 文件。
  - 防止 commit 建议混入无关改动。
  - 强化 README 修改前确认。
- 建议新增结构：
  - `When NOT to Use`
  - `Quick Reference`
  - `Change Set Rules`
  - `Common Mistakes`
  - `Verification Boundary`
- 建议测试：
  - untracked 文件识别
  - README 先问再改
  - dirty worktree 归因隔离
- 目标输出路径建议：`.agents/skills/project-post-change-actions/optimized/project-post-change-actions.round-1.optimized.md`

# 报告文件

- 目标路径：`.agents/skills/project-post-change-actions/review/project-post-change-actions.round-1.review.md`
- 状态：已生成
