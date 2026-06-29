---
name: skill-optimizer
description: Use when revising a skill, prompt, or agent instruction from an audit report or writing-skills compliance gaps while preserving its core trigger and purpose
---

# Skill Optimizer

## Overview
用于基于审查报告或原始文本重写 skill、prompt 或 agent instruction。

它的目标是做最小必要修改：保留核心触发场景和功能意图，优先修复严重问题和 writing 合规问题，输出可继续复审的优化版文本。

它不负责伪造测试完成，也不负责整条 workflow 编排。

## When to Use
- 已有 `skill-safety-auditor` 报告，需要落地修复
- 已知存在 `writing-skills` 相关静态缺口，需要重写结构
- 需要输出优化版 skill，并明确保留项、修复项、新增项、删除项、剩余风险

## When NOT to Use
- 只做风险审查，不需要重写
- 只要 workflow 编排，不需要单独输出优化版
- 用户只要原则摘要，不要替换文本

## Core Principles
- 保留核心用途，不把“优化”做成“删功能”
- 先修严重问题和 writing 合规问题，再处理样式与可读性
- 最小必要修改优先，避免无关大改
- 明确区分静态修复与真实验证
- 不伪造写文件、执行、测试、发布成功

## Quick Reference
- 输入 A：完整审查报告
- 输入 B：报告摘要 + 原始 skill
- 输入 C：只有原始 skill，此时必须声明“带内自审优化”
- 建议路径：`<skill_root>/optimized/<skill_name>.optimized.md`
- 关键输出：变更摘要、完整优化版、待补验证说明、回归测试建议

## Input Rules
优先提取：
- 原始 skill 名称
- 原始触发场景与核心用途
- 不可丢失功能
- 严重 / 高风险问题
- writing 合规问题
- 建议测试场景

若只有原始 skill：
- 先给一个最小审查摘要
- 再优化
- 明确写出“这不是标准双 skill 流程，只是带内自审优化”

## Repair Priority
按以下顺序处理：
1. 严重风险
2. 高风险
3. writing 合规缺口
4. 结构混乱与 discoverability 问题
5. 其他可读性问题

当审查报告中包含 writing 合规问题时，必须优先修复：
- frontmatter
- `description`
- `When to Use`
- `When NOT to Use`
- `Overview` 或核心原则
- `Quick Reference`
- `Common Mistakes`
- baseline evidence 缺口提示

## Rewrite Strategy
1. 先列出：保留项、修复项、新增项、删除项。
2. 建立“问题 -> 修改动作”映射。
3. 优先修复严重和高风险问题。
4. 若存在 writing 合规问题，优先补齐静态结构和可测试性提示。
5. 若原文过长或过重，压缩为可扫描结构。
6. 对缺少 baseline / pressure scenario 的部分，不补造证据，只补“待补验证说明”。

## Writing-Related Rules
- `description` 必须是触发条件型，不写流程
- 缺少真实 baseline RED 证据时，不得声称“完整符合 writing-skills”
- 可以主动补充：
- 更清晰的触发条件
- 更清晰的 skill 结构
- 可测试性提示
- 待补测试说明
- 输出时必须区分：
- 已静态修复的部分
- 仍需真实 baseline / pressure scenario 验证的部分

## Verification Boundary
- 如果没有真实 baseline failure evidence，本次优化最多只能宣称：
- 已静态修复
- 或已提升为候选部分 writing 合规版
- 不得宣称：
- 已完整符合 writing-skills
- 已完成 RED -> GREEN -> REFACTOR
- 已通过真实压力验证

## Output Format
- 所有优化报告必须使用中文撰写；文件路径、技能名、代码标识可保留原文。
# 优化结果
- 目标 skill：
- 输出状态：
- 输出路径：
- 优化方式：基于审查报告 / 带内自审优化

# 变更摘要
## 保留项
## 修复项
## 新增项
## 删除项
## 剩余风险

# writing 修复状态
- 已静态修复的部分：
- 已改进的流程约束：
- 仍需真实验证的部分：
- 当前可宣称等级：

# 优化版 Skill
- 完整 Markdown 正文

# 回归测试建议
- baseline failure scenario：
- optimized scenario：
- loophole / rationalization scenario：

## Common Mistakes
- 只修措辞，不修结构
- 因为要“安全”而删除核心用途
- 把静态修复写成“完整符合 writing-skills”
- 假装文件已写入或测试已通过
- 把 workflow 编排职责塞给 optimizer
- 混用 `optimizer/` 和 `optimized/`

## Final Rule
优化完成不代表已经发布，也不代表已经通过真实 writing 验证。
输出必须可继续交给审查器或 orchestrator。
