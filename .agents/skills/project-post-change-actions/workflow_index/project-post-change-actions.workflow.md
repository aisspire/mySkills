# 工作流状态

- 当前模式：真实编排模式中的静态流程；未运行真实 baseline pressure tests
- 当前轮次：1
- 最大轮次：1
- 当前候选等级：静态合规
- 发布确认：`待用户回答`
- 正式入口状态：`未发布`
- 下一动作：直接询问用户是否发布候选优化版到正式入口

# Stage 0: writing gate

- 当前等级：静态合规候选
- 证据链状态：缺少 baseline、green、refactor 真实证据
- 下一步建议：先做静态优化；不得宣称完整 writing 合规

# Stage 1: baseline evidence

- 是否存在真实 baseline：否
- 缺什么：
  - 未使用 skill 时的失败输出
  - 使用优化版后的对照输出
  - loophole/refactor 复验记录
- 是否进入人工补测提示：是；本轮仅保留补测建议，不伪造证据

# Stage 2: 审查结果

- 风险摘要：
  - 总体低风险。
  - 主要风险是工具证据遗漏和行为边界不够硬，而不是安全越权。
  - 需要防止自动改 README、自动提交、混入无关改动。
- writing 缺口摘要：
  - 缺 `When NOT to Use`、`Quick Reference`、`Common Mistakes`。
  - 缺 baseline evidence。
  - 缺对 staged/untracked/dirty worktree 的明确处理。
- 审查报告路径：`.agents/skills/project-post-change-actions/review/project-post-change-actions.round-1.review.md`

# Stage 3: 优化结果

- 已静态修复：
  - 增加 `When NOT to Use`。
  - 增加 `Quick Reference`。
  - 增加 `Change Set Rules`。
  - 增加 `Verification Boundary`。
  - 增加 `Common Mistakes`。
  - 明确 untracked 文件不能被 `git diff --stat` 替代。
  - 明确 README 修改前必须确认。
  - 明确 commit 建议不应混入无关改动。
- 仍需补测：
  - baseline failure scenario。
  - with-skill green scenario。
  - loophole/refactor scenario。
- 优化版路径：`.agents/skills/project-post-change-actions/optimized/project-post-change-actions.round-1.optimized.md`

# Stage 4: 复审结果

- 风险变化：
  - 工具误用风险下降。
  - README 误改风险下降。
  - commit 建议混入无关改动的风险下降。
- 新增副作用：
  - 候选版比原版更长，但仍保持单文件、可扫描。
  - 对“当前任务改动”的判断仍依赖模型根据上下文归因，无法完全自动化保证。
- 对核心用途影响：
  - 核心用途保持不变。
  - “每次项目修改后执行项目列出的动作”这一定位更清楚。

# Stage 5: 合规判定

- 最终候选等级：静态合规
- 可宣称范围：
  - 静态结构已优化。
  - 关键行为边界已补强。
  - 已生成候选版、审查报告、writing gate 报告和 workflow 记录。
- 不可宣称范围：
  - 不可宣称完整 writing 合规。
  - 不可宣称已通过真实压力测试。
  - 不可宣称已正式发布。
- gate 路径：`.agents/skills/project-post-change-actions/compliance/project-post-change-actions.round-1.writing-gate.md`

# Stage 6: 发布确认

- 推荐候选版本：`.agents/skills/project-post-change-actions/optimized/project-post-change-actions.round-1.optimized.md`
- 候选版本路径：`.agents/skills/project-post-change-actions/optimized/project-post-change-actions.round-1.optimized.md`
- 拟覆盖正式入口路径：`.agents/skills/project-post-change-actions/SKILL.md`
- 用户确认状态：待用户回答
- 发布结果：未发布

# 最终建议

- 最终报告路径：`.agents/skills/project-post-change-actions/review/project-post-change-actions.round-1.review.md`
- 最终优化版路径：`.agents/skills/project-post-change-actions/optimized/project-post-change-actions.round-1.optimized.md`
- 最终 gate 路径：`.agents/skills/project-post-change-actions/compliance/project-post-change-actions.round-1.writing-gate.md`
- 剩余风险：
  - 缺真实 RED/GREEN/REFACTOR 证据。
  - 对“本轮修改 vs 历史无关修改”的区分仍可能需要人工判断。
  - 项目自定义动作越多，后续需要检查动作之间是否冲突。
- 下次迭代建议：
  - 补 3 个 pressure scenarios 后再做第二轮优化。
  - 如果项目有固定 README 章节结构，可把 README 更新方案模板进一步项目化。
