---
name: project-closeout
description: Use before the final response after modifying code/config/tests/docs, including follow-up fixes, to prepare documentation checks, README decisions, verification status, and a non-optional Chinese Conventional Commit draft. 用于软件项目修改后的最终回复前收尾，包括二次修正，检查文档更新、README 是否需要调整、验证状态，并强制给出中文 Conventional Commit 建议。
---

# Project Closeout

## Overview

用于项目修改后的交付闭环。它把“开发后更新文档、判断 README、给出 commit 建议、说明验证状态”统一成一个收尾流程。

它不负责实现原始需求，也不替代 `project-docs-workflow` 的文档体系维护；它负责在结束前检查这些动作是否应该发生。

## When to Use

- 已修改代码、配置、测试、脚本或文档，准备结束任务。
- 用户要求“收尾”“总结”“给 commit”“更新 README”“更新文档”。
- 需要检查本次变更是否影响 `docs/`、README、测试说明或 ADR。
- 当前任务结束有未提交内容。
- 需要交付一个中文 Conventional Commit 草稿。

## When NOT to Use

- 当前回合没有文件修改。
- 用户只是在讨论方案，不需要交付收尾。
- 用户明确要求不要检查文档或 README。

## Required Evidence

优先检查：

- `git status --short`
- `git diff --stat`
- `git diff --cached --stat`（如有 staged changes）
- 本轮实际修改文件
- 当前未提交的相关完整 diff，而不只是最近一次小修小改
- 与用户可见行为、安装方式、API、数据、测试相关的 diff

如果不是 git 仓库，说明 git evidence 不可用，并基于当前会话文件变更收尾。

## Completion Gate

只要当前任务产生、修改或继续修正了代码、配置、测试、脚本或文档，最终回复前必须执行本 skill 的收尾检查。

如果存在当前任务相关的未提交变更，`Commit 建议` 是必填项。不要因为用户没有再次明确要求 commit、只是第二轮小修、或者已经给过一次总结，就省略 commit 草稿。

如果最终回复无法给出 commit 草稿，必须说明阻塞原因；不能静默省略。

## Closeout Workflow

### 1. Changed Files

列出本轮相关变更，不要把无关旧改动混入默认总结。但若是在旧改动上的改动，则需要给出全量的commit信息，而不是对旧改动的改动commit信息。

如果当前轮是在修正前一轮不合格、未完成或未提交的改动，必须回看这些文件的未提交相关变更，并按最终要提交的完整 commit 信息总结。不要只根据当前轮最新小改生成 commit 草稿。

如果存在明显无关的未提交改动：

- 单独列为“可能无关变更”
- 不纳入默认 commit 草稿
- 但如果某个旧改动被本轮继续修改、修正或补全，应视为相关变更，纳入完整 commit 信息

Commit draft coverage rule: include complete commit information for relevant uncommitted changes; do not draft only from the latest small edit.

Commit advice mandatory rule: when relevant uncommitted changes exist, the final response must include a Commit recommendation.

### 2. Docs Update Check

根据变更判断是否需要更新：

- `docs/index.md`
- `docs/project.md`
- `docs/features/`
- `docs/api/`
- `docs/data/`
- `docs/tests/`
- `docs/architecture/`
- `docs/flows/`
- `docs/adr/`
- `docs/ai/`

如果需要更新，调用或遵循 `project-docs-workflow` 的边界，只更新相关最小文档。

### 3. README Decision

必须给出一个结果：

- `README change recommended`
- `README change not needed`
- `README missing`

只有当变更影响安装、使用、配置、公开能力、截图、限制、兼容性或贡献流程时，才建议更新 README。

用户未明确确认前，不要自动改 README。

### 4. Verification Status

列出实际运行过的验证命令和结果。

不要声称测试通过，除非本轮真的运行并看到通过输出。

如果未运行验证，说明原因和建议最终命令。

### 5. Commit Draft

输出一个中文 Conventional Commit 草稿。默认应覆盖当前未提交的相关变更完整意图，而不是只覆盖当前轮最后一次编辑：

```text
type(scope): 中文摘要

- 具体改动 1
- 具体改动 2
- 验证或文档说明
```

类型从 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`、`build`、`ci`、`perf` 中选择。

当存在多轮修正时，commit 摘要和 bullet 应描述最终成型的功能、修复和文档变化；不要写成“修正上次遗漏”“补一点文案”这类只反映当前小改的内容。

如果本次最终回复包含“变更摘要”“验证状态”或类似收尾内容，却没有 `Commit 建议`，视为收尾失败。

不要自动创建 commit，除非用户明确要求。

## Final Response Format

```markdown
# 变更摘要

# 文档更新

# README 判断

# 验证状态

# Commit 建议
```

## Common Mistakes

- 完成实现后只汇报变更和验证，没有给出 Commit 建议。
- 把所有未提交改动都写进 commit 草稿。
- 二次修正时只写当前小改，没有汇总被修正文件的完整未提交相关变更。
- 没有运行测试却写“测试通过”。
- 任何改动都建议更新 README。
- 只更新 README，不更新更贴近事实来源的 `docs/`。
- 把收尾流程变成重新实现需求。
