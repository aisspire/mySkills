---
name: project-closeout
description: Use when finishing a software project change and preparing documentation updates, README decisions, verification status, and a Chinese Conventional Commit draft. 用于软件项目修改后的收尾，检查文档更新、README 是否需要调整、验证状态和中文 Conventional Commit 建议。
---

# Project Closeout

## Overview

用于项目修改后的交付闭环。它把“开发后更新文档、判断 README、给出 commit 建议、说明验证状态”统一成一个收尾流程。

它不负责实现原始需求，也不替代 `project-docs-workflow` 的文档体系维护；它负责在结束前检查这些动作是否应该发生。

## When to Use

- 已修改代码、配置、测试、脚本或文档，准备结束任务。
- 用户要求“收尾”“总结”“给 commit”“更新 README”“更新文档”。
- 需要检查本次变更是否影响 `docs/`、README、测试说明或 ADR。
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
- 与用户可见行为、安装方式、API、数据、测试相关的 diff

如果不是 git 仓库，说明 git evidence 不可用，并基于当前会话文件变更收尾。

## Closeout Workflow

### 1. Changed Files

列出本轮相关变更，不要把无关旧改动混入默认总结。

如果存在明显无关的未提交改动：

- 单独列为“可能无关变更”
- 不纳入默认 commit 草稿

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

输出一个中文 Conventional Commit 草稿：

```text
type(scope): 中文摘要

- 具体改动 1
- 具体改动 2
- 验证或文档说明
```

类型从 `feat`、`fix`、`docs`、`test`、`refactor`、`chore`、`build`、`ci`、`perf` 中选择。

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

- 把所有未提交改动都写进 commit 草稿。
- 没有运行测试却写“测试通过”。
- 任何改动都建议更新 README。
- 只更新 README，不更新更贴近事实来源的 `docs/`。
- 把收尾流程变成重新实现需求。
