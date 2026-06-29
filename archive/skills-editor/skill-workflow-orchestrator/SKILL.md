---
name: skill-workflow-orchestrator
description: Use when coordinating multi-round writing gate checks, auditing, optimization, compliance decisions, and explicit publish confirmation for one or more skills, especially when baseline evidence may be incomplete
---

# Skill Workflow Orchestrator

## Overview

用于编排 skill editor / skill governance 工作流，把 `skill-writing-gate`、`skill-safety-auditor`、`skill-optimizer` 串成一条可追踪、可中止、可人工接力的闭环。

它的职责是说明当前进行到哪一阶段、当前候选版最多能宣称到什么等级、以及是否已经获得正式发布授权。

## When to Use

- 需要对一个或多个 skills 做多轮审查、优化、复审和发布判断
- 需要把 `writing-skills` 的门禁逻辑纳入现有工作流
- 需要明确区分静态合规、部分 writing 合规、完整 writing 合规
- 需要在发布前强制要求用户明确确认

## When NOT to Use

- 只做单次审查或单次重写，不需要编排
- 已明确不需要 writing gate 或发布闸门
- 只需要一次性手工文本，不需要轮次管理

## Core Principles

- 候选版不等于已发布
- 优化请求不等于发布授权
- `writing-skills` 是上位方法论，`skill-writing-gate` 是其门禁翻译层
- 没有 baseline failure evidence，不得把候选版标成完整 writing 合规
- 不能真实调度或真实补测时，必须降级为人工接力模式
- 发布前必须说明候选等级，并获得用户的明确确认
- 在 workflow 文件里记录“未确认”不能替代直接向用户发问

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

## Candidate vs Official

必须明确区分：

- 候选版：当前审查和优化得到的版本
- 正式入口：被声明为“已发布”“正式版”“当前生效版”的入口文件

强规则：

- Stage 0 到 Stage 5 只能产生候选版结论
- 只有 Stage 6 获得用户明确发布确认后，才允许宣称“已发布”
- 即使工作过程中直接修改了正式入口路径中的文件，也不能自动视为“已发布”
- “文件已经写入正式目录”与“正式发布”是两件不同的事

## Publish Authorization Rules

只有当用户明确表达以下意图之一时，才能视为获得发布授权：

- 发布
- 正式发布
- 作为正式版
- 按此版生效
- 覆盖正式入口
- 用这版替换当前入口

以下表达不能视为发布授权：

- 优化一下
- 改一下
- 继续完善
- 落盘
- 写到目录里
- 先做这一版

如果意图不明确，一律视为未授权发布。

## Stage Model

### Stage 0: Writing Gate Readiness

使用 `skill-writing-gate` 判断当前状态：

- 当前等级
- 证据链是否完整
- 当前不可宣称的范围
- 下一步最缺什么

### Stage 1: Baseline Evidence Check

检查是否存在真实 baseline failure evidence。

如果没有：

- 明确记录“尚未具备完整 writing 证据链”
- 进入人工补测提示，或继续做静态流程但不得升格为完整 writing 合规

### Stage 2: Safety / Structure Audit

使用 `skill-safety-auditor` 做安全、结构、writing 静态缺口审查。

### Stage 3: Optimization

使用 `skill-optimizer` 产出候选优化版。

要求输出：

- 已静态修复的部分
- 仍需真实验证的部分

### Stage 4: Re-Audit

对候选优化版再次审查，确认：

- 风险是否下降
- 结构是否更清晰
- 是否引入新副作用
- writing 静态缺口是否减少

### Stage 5: Compliance Decision

再次使用 `skill-writing-gate`，对候选版作最终等级判定：

- 静态合规
- 部分 writing 合规
- 完整 writing 合规

强规则：

- 没有真实 baseline failure evidence，不能判为完整 writing 合规
- 环境不支持真实补测时，最多停在静态合规或部分 writing 合规

### Stage 6: Publish Approval

这是强制停机阶段。

发布前必须明确告诉用户：

- 推荐候选版本是什么
- 当前候选版属于什么等级
- 将覆盖哪些正式入口文件
- 当前是否真的允许覆盖

#### Mandatory Stop Rule

未获得用户明确“同意发布”前，必须立即停止，不得继续宣称已发布。

未确认时，必须同时满足：

- `发布确认: 待用户回答`
- `正式入口状态: 未发布`
- `下一动作: 直接询问用户是否发布`

禁止动作：

- 不得在最终答复中写“已发布”“正式版”“当前生效版”
- 不得把 workflow 中的“未确认”记录当成确认动作本身
- 不得因为用户要求“优化”就推断为允许发布

#### Mandatory Question Template

到达 Stage 6 且尚未获得发布授权时，必须直接向用户提问：

`是否将当前候选版正式发布到以下入口路径？`

然后列出：

- 候选版本路径
- 正式入口路径
- 当前候选等级

#### Direct-Edit Exception Rule

如果由于当前工作方式，优化动作已经直接改到了正式入口文件：

- 仍然只能视为“正式入口文件已被修改，但尚未获得正式发布确认”
- 不得因此跳过提问
- 必须明确告诉用户“当前只是工作区已更新，不代表已正式发布”

## Mode Selection

先判断当前环境属于哪一种：

- 真实编排模式：可以真实调用相关 skill，且能保存产物
- 人工接力模式：不能真实调用或不能可靠补测/保存

若不能真实运行 baseline pressure tests：

- 必须进入人工补测提示或人工接力模式
- 不得伪造 RED / GREEN 已完成

## Stop Conditions

满足任意一项即可建议停止：

- 当前候选版已达到目标等级，且无关键阻碍
- 连续两轮改进有限
- 继续优化会损害核心用途
- 环境限制导致后续必须人工补测
- 已到 Stage 6 且等待用户发布确认

## Output Format

所有工作流报告必须使用中文撰写；文件路径、技能名、阶段名、代码标识可保留原文。

# 工作流状态

- 当前模式：
- 当前轮次：
- 最大轮次：
- 当前候选等级：
- 发布确认：`待用户回答 / 已同意 / 已拒绝`
- 正式入口状态：`未发布 / 已发布 / 保留现状`
- 下一动作：

# Stage 0: writing gate

- 当前等级：
- 证据链状态：
- 下一步建议：

# Stage 1: baseline evidence

- 是否存在真实 baseline：
- 缺什么：
- 是否进入人工补测提示：

# Stage 2: 审查结果

- 风险摘要：
- writing 缺口摘要：

# Stage 3: 优化结果

- 已静态修复：
- 仍需补测：

# Stage 4: 复审结果

- 风险变化：
- 新增副作用：
- 对核心用途影响：

# Stage 5: 合规判定

- 最终候选等级：
- 可宣称范围：
- 不可宣称范围：

# Stage 6: 发布确认

- 推荐候选版本：
- 候选版本路径：
- 拟覆盖正式入口路径：
- 用户确认状态：
- 发布结果：

# 最终建议

- 最终报告路径：
- 最终优化版路径：
- 最终 gate 路径：
- 剩余风险：
- 下次迭代建议：

## Multi-Skill Rules

- 每个 skill 单独建立轮次记录
- 最后再给汇总视图
- 汇总至少包含：
  - skill 名称
  - 当前最佳版本
  - 当前候选等级
  - 是否建议继续
  - 主要剩余问题

## Manual Handoff Mode

如果不能真实跑 skill 调度或不能真实补测，必须输出：

- 当前停在哪个 stage
- 下一步该交给哪个 skill
- 需要补什么输入
- 建议保存路径
- 可复制的 handoff 模板

不要把“已给出 handoff 包”写成“已完成流程”。

## Common Mistakes

- 跳过 Stage 0 或 Stage 5，直接宣布完整合规
- 没有 baseline evidence 仍标为完整 writing 合规
- 混用 `optimizer/` 和 `optimized/`
- 把候选版写成“已发布”
- 未获得确认就覆盖正式结论
- 用“用户要求优化”替代“用户明确授权发布”
- 在 workflow 中记录“未确认”却没有直接问用户
- 因为文件已经改在正式目录里，就误判为“已经发布”
- 环境不支持真实补测时仍伪造 RED / GREEN 已完成

## Final Rule

这个 skill 的职责是编排、标注、收敛和门禁，不是替代真实 baseline 测试。
