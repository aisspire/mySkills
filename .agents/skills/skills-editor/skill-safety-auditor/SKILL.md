---
name: skill-safety-auditor
description: Use when auditing a skill, prompt, agent instruction, tool policy, or workflow rule for safety, clarity, maintainability, or writing-skills compliance gaps
---

# Skill Safety Auditor

## Overview
用于审查 skill、prompt、agent instruction、工具规则和工作流规则的安全性、鲁棒性、清晰度、可维护性，以及与 `writing-skills` 相关的静态合规缺口。

它负责发现问题、分级、给替代写法，并生成可交给 `skill-optimizer` 的结构化输入。
它不是 orchestrator，也不是完整的 writing 方法论承载者。

## When to Use
- 需要做安全、结构、维护性审查
- 需要识别 prompt injection、数据泄露、工具滥用、规则冲突
- 需要检查 skill 是否存在 writing 合规缺口
- 需要输出结构化审查报告给后续优化器使用

## When NOT to Use
- 只需要直接重写，不需要先出审查报告
- 任务只是润色文案，不涉及规则、边界、结构或可维护性
- 已明确只要 workflow 编排，不需要单独审查

## Core Principles
- 先发现问题，再建议修复
- 区分事实、推断、建议
- 保留原始功能意图，不把“审查”做成“删功能”
- 静态审查不等于动态验证
- `writing-skills` 相关问题只做审查与标注，不伪造 RED/GREEN 已完成

## Quick Reference
- 核心输出：审查结论、风险评分、问题清单、优化建议、测试建议
- 建议路径：`<skill_root>/review/<skill_name>.review.md`
- 需新增输出段：`# writing 合规性判断`
- 无法写文件时：输出完整 Markdown 正文并标注建议保存路径

## What to Check
1. 指令与数据是否分离
2. 外部内容是否被错误提升为高优先级指令
3. 是否存在越权执行、删除、覆写、联网、发消息等高风险动作且无确认
4. 是否写清能做什么、不能做什么、何时拒绝、何时确认、何时承认不确定
5. 是否区分事实、推断、建议，并要求给出依据
6. 是否存在规则冲突、优先级缺失、术语未定义、路径约定不一致
7. 是否过度 SOP 化、过长、低 discoverability、难维护
8. 是否存在 `writing-skills` 静态缺口：
- frontmatter 是否合规
- `description` 是否以 `Use when...` 开头
- `description` 是否只写触发条件
- 是否把流程写进 `description`
- 是否缺少 `Overview` 或核心原则
- 是否缺少 `When to Use`
- 是否缺少 `When NOT to Use`
- 是否缺少 `Quick Reference`（如适合）
- 是否缺少 `Common Mistakes`
- 是否缺少 baseline failure evidence 的明确说明

## Workflow
1. 提取目标、触发条件、输入输出、工具边界、确认机制、失败处理。
2. 做安全与结构审查。
3. 做 writing 静态合规审查。
4. 输出风险等级、问题清单、替代写法和测试建议。
5. 生成 `# 交给 Skill Optimizer 的输入`。

若用户没有提供原文，只给目标描述：
- 先说明“以下审查基于最小草案，不是对正式文件的直接审查”
- 生成最小草案
- 再做自审

## Writing 合规性判断
本段必须单独输出，至少包含：
- frontmatter 判断
- description 判断
- 结构完整度判断
- baseline evidence 判断
- 当前 writing 等级：仅静态合规 / 部分符合 writing-skills / 完整符合 writing-skills
- 证据链状态：已具备 / 尚未具备完整 writing 证据链

默认规则：
- 没有明确 baseline failure evidence 时，不得直接给出“完整符合 writing-skills”
- 只有静态结构修复时，最多标为“仅静态合规”
- 有部分真实证据但链条未闭合时，可标为“部分符合 writing-skills”

## Verification Boundary
- 未运行真实 baseline pressure scenarios 时，只能输出“静态审查结论”
- 不得把文档质量提升写成“已完成 writing-skills 验证”
- 应明确哪些结论仍需 `skill-writing-gate` 或 orchestrator 在后续流程中补充判断

## Output Format
- 所有审查报告必须使用中文撰写；文件路径、技能名、代码标识可保留原文。
# 审查结论
- 总体安全等级：
- 总体评价：
- 最关键的 3 个问题：

# 风险评分
- Prompt Injection：
- 数据泄露：
- 工具误用：
- 结构清晰度：
- 可维护性：

# writing 合规性判断
- frontmatter：
- description：
- 结构要件：
- baseline evidence：
- 当前 writing 等级：
- 证据链状态：
- 说明：

# 问题清单
## 问题 1
- 级别：
- 位置：
- 问题描述：
- 为什么危险：
- 可能触发方式：
- 修复建议：
- 替代写法：

# 优化建议
- 立即修复：
- 结构优化：
- 质量优化：
- 测试补充：

# 建议测试用例
- baseline failure scenario：
- optimized scenario：
- loophole / rationalization scenario：

# 交给 Skill Optimizer 的输入
- 原始 skill 名称：
- 不可丢失功能：
- 必须修复问题：
- 建议新增结构：
- 建议测试：
- 目标输出路径建议：

# 报告文件
- 目标路径：`<skill_root>/review/<skill_name>.review.md`
- 状态：已生成 / 未生成（如未生成，说明原因）

## Common Mistakes
- 只说“有风险”，不给替代写法
- 把所有问题都算安全问题，忽略结构与 discoverability
- 把缺少 baseline evidence 写成“已通过验证”
- 因为发现风险就建议删空核心功能
- 越界替代 orchestrator 做整条流程编排

## Final Rule
目标不是证明“绝对安全”，而是产出一份诚实、可执行、可交接的审查结果。
