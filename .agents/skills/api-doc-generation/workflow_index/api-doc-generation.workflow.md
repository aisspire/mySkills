# 工作流状态

- 当前模式：真实编排模式（静态阶段）+ 人工补测提示（证据阶段）
- 当前轮次：1
- 最大轮次：1
- 当前候选等级：静态合规
- 发布确认：用户已明确同意正式发布当前优化版
- 正式入口状态：已正式发布到当前 skill 入口目录

# Stage 0：writing gate

- 当前等级：静态合规
- 证据链状态：不完整
- 下一步建议：补 baseline failure evidence 后再进入更高等级判定

# Stage 1：baseline evidence

- 是否存在真实 baseline：否
- 缺什么：RED baseline、GREEN 对照、REFACTOR 漏洞补洞证据
- 是否进入人工补测提示：是

# Stage 2：审查结果

- 风险摘要：无明显安全风险，主要问题是字段证据链和静态结构完整性不足
- writing 缺口摘要：缺 `Quick Reference`、缺显式验证边界、模板关系结构不够硬

# Stage 3：优化结果

- 已静态修复：
  - 补了 `Quick Reference`
  - 补了字段证据链要求
  - 补了 `Verification Status`
  - 强化了模板中的接口关系结构
- 仍需补测：
  - baseline failure evidence
  - with-skill evidence
  - loophole/refactor evidence

# Stage 4：复审结果

- 风险变化：下降
- 新增副作用：无明显新增副作用
- 对核心用途影响：核心用途保持不变，执行约束更强，模板更可复核

# Stage 5：合规判定

- 最终候选等级：静态合规
- 可宣称范围：结构、边界、discoverability、模板完整性已改进
- 不可宣称范围：完整 `writing-skills` 合规、完整 RED -> GREEN -> REFACTOR

# Stage 6：发布确认

- 推荐候选版本：当前工作副本中的 `SKILL.md` 与 `references/output-template.md`
- 拟覆盖正式入口路径：
  - `.agents/skills/api-doc-generation/SKILL.md`
  - `.agents/skills/api-doc-generation/references/output-template.md`
- 用户确认状态：用户已明确要求先正式发布优化后的 skill
- 发布结果：已按当前优化版作为正式入口版本保留

# 最终建议

- 最终报告路径：`<skill_root>/workflow_index/api-doc-generation.workflow.md`
- 最终优化版路径：`<skill_root>/optimized/api-doc-generation.round-1.optimized.md`
- 最终 gate 路径：`<skill_root>/compliance/api-doc-generation.round-1.writing-gate.md`
- 剩余风险：缺真实 baseline/green/refactor 证据
- 下次迭代建议：基于一个真实模块做无 skill / 有 skill 对照测试
