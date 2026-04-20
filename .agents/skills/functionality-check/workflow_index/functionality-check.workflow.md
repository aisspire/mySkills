# 工作流状态
- 当前模式：人工接力模式下的静态 workflow
- 当前轮次：1
- 最大轮次：1
- 当前候选等级：静态合规
- 发布确认：未同意
- 正式入口状态：已覆盖正式 `SKILL.md`

# Stage 0：writing gate
- 当前等级：静态合规
- 证据链状态：不完整
- 下一步建议：补 baseline / green / refactor 证据

# Stage 1：baseline evidence
- 是否存在真实 baseline：否
- 缺什么：未带 skill 时的失败样例
- 是否进入人工补测提示：是

# Stage 2：审查结果
- 风险摘要：低风险，主要是静态结构与 discoverability 优化
- writing 缺口摘要：缺 baseline evidence，description 和结构需收紧

# Stage 3：优化结果
- 已静态修复：
  - 收紧 description
  - 增加快速参考
  - 明确主动调用触发条件
  - 补齐 review / compliance / workflow_index 目录产物
- 仍需补测：
  - baseline failure evidence
  - with-skill improved evidence
  - loophole/refactor evidence

# Stage 4：复审结果
- 风险变化：结构与 discoverability 风险下降
- 新增副作用：无
- 对核心用途影响：无负面影响，主用途更明确

# Stage 5：合规判定
- 最终候选等级：静态合规
- 可宣称范围：
  - 已完成静态审查与静态优化
  - 已补齐 workflow 痕迹
- 不可宣称范围：
  - 完整 writing-skills 合规
  - 已完成真实 RED / GREEN / REFACTOR

# Stage 6：发布确认
- 推荐候选版本：`E:\code\skills\.agents\skills\functionality-check\SKILL.md`
- 拟覆盖正式入口路径：`E:\code\skills\.agents\skills\functionality-check\SKILL.md`
- 用户确认状态：本轮请求已要求跑 workflow 优化，未额外请求发布到其他位置

# 最终建议
- 最终报告路径：`E:\code\skills\.agents\skills\functionality-check\workflow_index\functionality-check.workflow.md`
- 最终优化版路径：`E:\code\skills\.agents\skills\functionality-check\optimized\functionality-check.round-1.optimized.md`
- 最终 gate 路径：`E:\code\skills\.agents\skills\functionality-check\compliance\functionality-check.round-1.writing-gate.md`
- 剩余风险：缺真实 pressure scenario 证据
- 下次迭代建议：补一轮 baseline / green / loophole 对照验证
