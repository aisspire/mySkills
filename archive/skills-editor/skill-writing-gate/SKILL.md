---
name: skill-writing-gate
description: Use when deciding whether a skill can be labeled static compliant, partially writing-skills compliant, or fully writing-skills compliant, especially when baseline evidence may be missing
---

# Skill Writing Gate

## Overview
这个 skill 是 `writing-skills` 在 skill editor / skill governance 体系中的桥接门禁。

它不负责重写 skill，也不负责整条工作流编排。它只负责回答一件事：当前这个 skill，最多可以被诚实地标注到哪一级合规状态。

它的作用是防止把“静态文档修好”误写成“已经完整满足 writing-skills”。

## When to Use
- 需要判断某个 skill 当前属于静态合规、部分 writing 合规还是完整 writing 合规
- 需要检查是否具备 baseline failure evidence
- 需要在发布前告诉用户候选版本当前的真实状态
- 需要给 `skill-workflow-orchestrator` 一个明确 gate 结论

## When NOT to Use
- 只是润色文案，不涉及 writing 方法论判定
- 只是做单次安全审查或单次文本重写
- 已明确不需要 `writing-skills` 视角

## Core Principles
- `writing-skills` 是上位方法论；本 skill 只做门禁翻译，不重复整套正文
- 没有 baseline failure evidence，不得声称“完整符合 writing-skills”
- 文档质量提升不等于完成 RED -> GREEN -> REFACTOR
- 判定必须区分静态改进、流程改进、待补测试
- 不得伪造测试完成、子代理结果或压力验证

## Quick Reference
- 当前等级：静态合规 / 部分 writing 合规 / 完整 writing 合规
- 证据链状态：完整 / 不完整
- 建议路径：`<skill_root>/compliance/<skill_name>.round-N.writing-gate.md`
- orchestrator 必经节点：Stage 0 和 Stage 5
- 无法验证时：降级为人工补测提示，不升格为完整 writing 合规

## Classification Rules

### 静态合规
满足以下静态要求，但缺少完整证据链：
- frontmatter 基本合规
- description 以 `Use when...` 开头，且只描述触发条件
- 结构更清晰，边界更明确
- 不伪造写入、执行、测试或发布状态

### 部分 writing 合规
满足静态合规，并且至少具备以下之一，但仍不完整：
- 有 baseline failure 记录，但没有 with-skill 复验
- 有部分 GREEN 证据，但没有清晰 baseline 对照
- 有 RED / GREEN，但缺少 loophole / rationalization / refactor 证据
- 有明确测试设计与证据占位，但未真正补测完成

### 完整 writing 合规
必须同时满足：
- 已满足静态合规
- 有真实 baseline failure evidence
- 有 with-skill 改善或通过证据
- 有 refactor / loophole 补洞证据
- 证据可追踪，能说明场景、观察结果、缺口和结论

## Required Evidence
完整 writing 合规至少需要以下证据包：
- RED：未使用该 skill 时，模型如何失败，失败时说了什么，在哪些压力下违反规则
- GREEN：引入该 skill 后，同类场景下如何改善
- REFACTOR：发现的新 loophole、补丁内容、复验结果
- Traceability：场景名称、日期或轮次、输入摘要、结论边界

缺任何一项，都不能升格为“完整 writing 合规”。

## Output Format
- 所有 writing gate 报告必须使用中文撰写；文件路径、技能名、等级名、代码标识可保留原文。
# writing gate 结论
- 当前等级：
- 证据链状态：
- 可宣称范围：
- 不可宣称范围：
- 下一步建议：

# gate 明细
- frontmatter：
- description：
- 结构：
- discoverability：
- baseline evidence：
- green evidence：
- refactor evidence：

# 待补测试
- 缺失的 baseline：
- 缺失的 green：
- 缺失的 refactor：
- 建议补测方式：

# 文件状态
- 目标路径：`<skill_root>/compliance/<skill_name>.round-N.writing-gate.md`
- 状态：已生成 / 未生成（如未生成，说明原因）

## Common Mistakes
- 把“写得更规范”直接当成“完整符合 writing-skills”
- 只有测试计划，没有真实 failure evidence
- 只有 baseline，没有 with-skill 复验
- 只有一次顺利输出，就当作 refactor 已完成
- 没有证据链，却用很自信的措辞升格结论

## Final Rule
缺少真实 baseline failure evidence 时，最多只能判为：
- 静态合规
- 或部分 writing 合规

不能判为“完整 writing 合规”。
