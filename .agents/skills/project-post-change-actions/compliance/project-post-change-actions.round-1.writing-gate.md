# writing gate 结论

- 当前等级：静态合规
- 证据链状态：不完整
- 可宣称范围：
  - 已完成一轮静态审查。
  - 已产出候选优化版。
  - 候选版修复了结构、触发边界、README 确认机制、untracked 文件识别、dirty worktree 归因隔离等静态问题。
- 不可宣称范围：
  - 不可宣称完整符合 `writing-skills`。
  - 不可宣称已完成 RED -> GREEN -> REFACTOR。
  - 不可宣称候选版已通过真实压力场景验证。
- 下一步建议：
  - 如需升格为部分或完整 writing 合规，补真实 baseline failure evidence、with-skill 复验、loophole/refactor 记录。
  - 如只需要当前可用版本，可在用户明确确认后发布候选优化版到正式入口。

# gate 明细

- frontmatter：合规。`name` 使用小写连字符；`description` 以 `Use when...` 开头，并聚焦触发条件。
- description：合规。没有把完整流程写进 description。
- 结构：候选版已补齐 `Overview`、`When to Use`、`When NOT to Use`、`Quick Reference`、`Change Set Rules`、`Verification Boundary`、`Common Mistakes`。
- discoverability：良好。包含 project、post-change、README、commit、modified files、handoff 等触发关键词。
- baseline evidence：缺失。没有真实记录“未使用 skill 时模型如何失败”。
- green evidence：缺失。没有真实记录“使用候选版后同类场景如何改善”。
- refactor evidence：缺失。当前只有基于静态审查的问题修复，没有真实 loophole 复验记录。

# 待补测试

- 缺失的 baseline：
  - 工作区存在 untracked 新文件，观察未使用 skill 时模型是否只看 `git diff --stat` 并漏报。
  - 工作区存在本轮修改和历史无关修改，观察未使用 skill 时模型是否混入 commit 建议。
  - README 需要更新时，观察未使用 skill 时模型是否直接编辑 README。
- 缺失的 green：
  - 使用候选版后，模型应识别 untracked 文件。
  - 使用候选版后，模型应隔离无关 dirty worktree 改动。
  - 使用候选版后，模型应在 README 修改前停下来询问。
- 缺失的 refactor：
  - 找一个“用户暗示顺手修改 README，但未确认具体内容”的场景，确认候选版是否仍会误改。
  - 找一个“用户要求 whole-worktree summary”的场景，确认候选版是否允许按用户要求包含全部改动。
- 建议补测方式：
  - 准备 3 个小型临时仓库状态，分别覆盖 untracked、dirty worktree、README confirmation。
  - 对比无 skill 与有 skill 的最终输出。
  - 保存输入、输出、观察结论后再进入下一轮优化。

# 文件状态

- 目标路径：`.agents/skills/project-post-change-actions/compliance/project-post-change-actions.round-1.writing-gate.md`
- 状态：已生成
