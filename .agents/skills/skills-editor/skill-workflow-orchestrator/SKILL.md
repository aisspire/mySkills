---
name: skill-workflow-orchestrator
description: Use when coordinating multi-round writing gate checks, auditing, optimization, compliance decisions, and publish approval for one or more skills, especially when baseline evidence may be incomplete
---

# Skill Workflow Orchestrator

## Overview
用于编排 skill editor / skill governance 工作流，把 `skill-writing-gate`、`skill-safety-auditor`、`skill-optimizer` 串成一条可追踪、可中止、可人工接力的闭环。

它是主要集成点。它负责说明当前进行到哪一步、当前最多能宣称到哪一级合规、还能不能发布。

## When to Use
- 需要对一个或多个 skills 做多轮审查、优化、复审和发布判断
- 需要把 `writing-skills` 方法门禁集成进现有工作流
- 需要明确区分静态合规、部分 writing 合规、完整 writing 合规
- 需要在发布前强制用户确认

## When NOT to Use
- 只做单次审查或单次重写，不需要编排
- 已明确不需要 writing gate 或发布门禁
- 只想要一次性的手工文本，不需要轮次管理

## Core Principles
- 候选版不等于已发布
- `writing-skills` 是上位方法论，`skill-writing-gate` 是其门禁翻译层
- 没有 baseline failure evidence，不得把候选版标为完整 writing 合规
- 不能真实调度或真实补测时，必须降级为人工接力模式
- 发布前必须说明候选等级，并获得明确确认

## Collaboration Skills
默认协作对象：
- `skill-writing-gate`
- `skill-safety-auditor`
- `skill-optimizer`

## Unified Directory Rules
统一使用以下目录：
- 审查报告：`<skill_root>/review/<skill_name>.round-N.review.md`
- 优化版：`<skill_root>/optimized/<skill_name>.round-N.optimized.md`
- writing gate：`<skill_root>/compliance/<skill_name>.round-N.writing-gate.md`
- 流程索引：`<skill_root>/workflow_index/<skill_name>.workflow.md`

不得再使用 `optimizer/`。

## Stage Model

### Stage 0：Writing Gate Readiness
使用 `skill-writing-gate` 判断当前状态：
- 当前等级
- 证据链是否完整
- 当前不可宣称的范围
- 下一步最缺什么

### Stage 1：Baseline Evidence Check
检查是否存在真实 baseline failure evidence。
如果没有：
- 明确记录“尚未具备完整 writing 证据链”
- 进入人工补测提示，或继续做静态流程但不升格为完整 writing 合规

### Stage 2：Safety / Structure Audit
使用 `skill-safety-auditor` 做安全、结构、writing 静态缺口审查。

### Stage 3：Optimization
使用 `skill-optimizer` 产出候选优化版。
要求输出：
- 已静态修复的部分
- 仍需真实验证的部分

### Stage 4：Re-Audit
对候选优化版再次审查，确认：
- 风险是否下降
- 结构是否更清晰
- 是否引入新副作用
- writing 静态缺口是否减少

### Stage 5：Compliance Decision
再次使用 `skill-writing-gate`，对候选版作最终等级判定：
- 静态合规
- 部分 writing 合规
- 完整 writing 合规

强规则：
- 没有真实 baseline failure evidence，不能判为完整 writing 合规
- 环境不支持真实补测时，最多停在静态合规或部分 writing 合规

### Stage 6：Publish Approval
发布前必须明确告诉用户：
- 推荐版本是什么
- 当前属于哪一类候选版本
- 将覆盖哪些正式入口文件
- 当前是否真的允许覆写

未得到明确确认前：
- `发布确认: 未同意`
- `正式入口状态: 未覆写`

## Mode Selection
先判断当前环境属于哪一种：
- 真实编排模式：可以真实调用相关 skill，且能保存产物
- 人工接力模式：不能真实调用或不能可靠补测 / 保存

若不能真实运行 baseline pressure tests：
- 必须进入人工补测提示或人工接力模式
- 不得伪造 RED / GREEN 已完成

## Stop Conditions
满足任意一项即可建议停止：
- 当前候选版已达到目标等级，且无关键阻塞
- 连续两轮改进有限
- 继续优化会损害核心用途
- 环境限制导致后续必须人工补测

## Output Format
- 所有工作流报告必须使用中文撰写；文件路径、技能名、阶段名、代码标识可保留原文。
# 工作流状态
- 当前模式：
- 当前轮次：
- 最大轮次：
- 当前候选等级：
- 发布确认：
- 正式入口状态：

# Stage 0：writing gate
- 当前等级：
- 证据链状态：
- 下一步建议：

# Stage 1：baseline evidence
- 是否存在真实 baseline：
- 缺什么：
- 是否进入人工补测提示：

# Stage 2：审查结果
- 风险摘要：
- writing 缺口摘要：

# Stage 3：优化结果
- 已静态修复：
- 仍需补测：

# Stage 4：复审结果
- 风险变化：
- 新增副作用：
- 对核心用途影响：

# Stage 5：合规判定
- 最终候选等级：
- 可宣称范围：
- 不可宣称范围：

# Stage 6：发布确认
- 推荐候选版本：
- 拟覆写正式入口路径：
- 用户确认状态：

# 最终建议
- 最终报告路径：
- 最终优化版路径：
- 最终 gate 路径：
- 剩余风险：
- 下次迭代建议：

## Multi-Skill Rules
- 每个 skill 单独建轮次记录
- 最后再给汇总视图
- 汇总至少包含：
- skill 名称
- 当前最佳版本
- 当前候选等级
- 是否建议继续
- 主要剩余问题

## Manual Handoff Mode
如果不能真实跨 skill 调度或不能真实补测，必须输出：
- 当前停在哪个 stage
- 下一步该交给哪个 skill
- 需要补什么输入
- 建议保存路径
- 可复制的 handoff 模板

不要把“已给出 handoff 包”写成“已完成流程”。

## Common Mistakes
- 跳过 Stage 0 或 Stage 5，直接宣布完整合规
- 没有 baseline evidence 仍标为完整 writing 合规
- 混用 `optimizer/` 与 `optimized/`
- 把候选版写成“已发布”
- 未获确认就覆写正式 `SKILL.md`
- 环境不支持真实补测时仍伪造 RED / GREEN 已完成

## Final Rule
这个 skill 的职责是编排、标注、收敛和门禁，不是替代真实 baseline 测试。
