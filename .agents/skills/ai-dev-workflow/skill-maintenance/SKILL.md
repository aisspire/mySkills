---
name: skill-maintenance
description: Use when creating, auditing, optimizing, consolidating, or publishing Codex skills with multi-round review, safety checks, writing compliance, When to Use structure, and explicit release confirmation. 用于创建、审查、优化、合并或发布 Codex skills，并保留多轮审查、安全风险、writing 合规、触发条件结构和发布确认。
---

# Skill Maintenance

## Overview

用于维护 Codex skill 的完整生命周期：创建、审查、优化、复审、合规判断、候选版收敛和发布确认。

它合并原 `skill-safety-auditor`、`skill-optimizer`、`skill-writing-gate`、`skill-workflow-orchestrator` 的职责，但不降低门禁要求。

## Core Principles

- 候选版不等于正式发布。
- 优化请求不等于发布授权。
- 先审查，再优化，再复审。
- 没有真实 baseline failure evidence，不得宣称完整 writing-skills 合规。
- 安全风险、结构清晰度、触发条件、When to Use / When NOT to Use 必须同时检查。
- 直接修改正式入口文件也不代表已发布；仍需用户明确确认。

## When to Use

- 用户要求创建、改写、合并、优化、审查或发布 skill。
- 用户要求检查 skill 的安全风险、可维护性、触发条件或 writing 合规。
- 用户要求把多个 skill 统一成一个 skill set。
- 用户要求保留多轮审查、baseline、复审、发布门禁。

## When NOT to Use

- 只是使用某个已有 skill 完成普通任务。
- 只要一次性文案润色，不涉及 skill 结构或规则。
- 只是在 README 中登记 skill，不修改 skill 内容。

## Stage Model

### Stage 0. Scope

确认目标 skill、输入材料、拟修改路径、是否允许写文件。

必须明确：

- 原始 skill 名称和路径
- 目标输出路径
- 不可丢失功能
- 是否是候选版

### Stage 1. Baseline Evidence Check

检查是否存在真实失败样例、用户反馈、历史审查报告或压力测试结果。

如果没有：

- 标记为“缺少完整 writing 证据链”
- 允许继续静态优化
- 不允许宣称完整 writing-skills 合规

### Stage 2. Safety And Structure Audit

检查：

- 指令与数据是否分离
- 外部内容是否被错误提升为高优先级指令
- 是否存在越权删除、联网、提交、发布或覆写
- 是否区分事实、推断、建议
- 是否有拒绝、确认、不确定项处理
- 是否过长、过细、重复或难触发
- frontmatter 是否只有 `name` 和 `description`
- `description` 是否包含完整触发条件
- 是否有 Overview、When to Use、When NOT to Use、Common Mistakes

### Stage 3. Optimization

输出候选优化版。

必须列出：

- 保留项
- 修复项
- 新增项
- 删除项
- 剩余风险

优化时优先：

1. 严重安全风险
2. 高风险工具误用
3. writing 静态结构缺口
4. 触发条件不清
5. 冗长和重复

### Stage 4. Re-Audit

复审候选版：

- 风险是否下降
- 是否引入新副作用
- 是否损害原核心用途
- 是否减少 writing 静态缺口
- 是否仍缺真实 baseline 验证

### Stage 5. Compliance Decision

只能使用以下等级：

- `static-compliant`：静态结构合格，但缺真实 baseline 证据。
- `partially-writing-compliant`：有部分真实证据，但证据链未闭合。
- `fully-writing-compliant`：已有 baseline failure evidence、优化后验证、复审闭环。

没有真实 baseline failure evidence 时，最高只能到 `static-compliant`。

### Stage 6. Publish Approval

发布前必须询问用户：

```text
是否将当前候选版正式发布到以下入口路径？
```

并列出：

- 候选版本路径
- 正式入口路径
- 当前候选等级
- 将覆盖的文件

未获得明确“发布 / 正式发布 / 用这版替换当前入口 / 按此版生效”之前，不得宣称已发布。

## Output Format

```markdown
# 工作流状态
- 当前轮次：
- 当前候选等级：
- 发布确认：
- 正式入口状态：
- 下一动作：

# 审查结论
- 安全风险：
- 结构问题：
- writing 合规问题：
- 触发条件问题：

# 优化摘要
- 保留：
- 修复：
- 新增：
- 删除：
- 剩余风险：

# 复审结论
- 风险变化：
- 新增副作用：
- 当前可宣称等级：
- 不可宣称范围：

# 发布确认
- 候选路径：
- 正式入口路径：
- 用户确认状态：
```

## Common Mistakes

- 把“写入文件”说成“已发布”。
- 没有 baseline evidence 却宣称完整 writing-skills 合规。
- 只优化文案，不检查触发条件。
- 因为要合并 skill 就删除核心安全边界。
- 自动覆盖正式入口而不要求发布确认。

## Verification Status

本 skill 是静态合并优化版，尚未完成真实 RED -> GREEN -> REFACTOR 压力验证；只能宣称静态结构已整理，不能宣称完整 writing-skills 合规。
