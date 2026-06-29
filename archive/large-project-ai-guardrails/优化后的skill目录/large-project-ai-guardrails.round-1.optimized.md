---
name: large-project-ai-guardrails
description: Use when starting work in a large, unfamiliar, or high-risk repository such as a monorepo, legacy codebase, or multi-service project where the AI needs project-specific boundaries, ownership rules, and safe exploration steps before making broad changes
---

# Large Project AI Guardrails

## Overview

这是一个面向大仓库的项目级 guardrails 模板。真正使用前，至少先填完前六个部分。任何没有仓库证据支撑的占位符，都应该删除或替换。

## When to Use

- 仓库体量大，你对它还不熟，或者它由多个 package、app、service 组成。
- 当前任务可能扩展成迁移、全局清理、架构调整或跨模块改动。
- 项目里存在隐藏约束，例如生成代码、代码所有权、发布规则或敏感目录。
- 你希望 AI 在做大范围修改前，先遵守项目自己的边界和协作规则。

## When Not to Use

- 仓库很小，而且所有权边界很清楚。
- 任务只是一个上下文明确的单文件小修复。
- 项目里已经有更新、更具体的 repo guardrails skill。

## Quick Start

1. 先填写 `Project Snapshot`、`Safe Change Zones`、`No-Touch Zones`、`Verification Commands`。
2. 把所有 `TODO(project)` 替换成真实仓库信息。
3. 删除不适用于当前项目的章节。
4. 保持首屏简短且具体，因为后续模型可能只会先扫这一屏。

## Required Inputs

- 仓库形态：monorepo、service、app、library、infra 或混合结构。
- 主要目录、包边界、入口点。
- 哪些区域由特定团队或维护者负责。
- 哪些文件是生成的、外部同步的、镜像的或 vendored。
- 哪些检查是必须通过的，例如 lint、test、build、deploy、review。

## Non-Goals

- 完整的架构文档。
- 通用编码规范手册。
- 仓库 README 的替代品。
- 某个具体需求的实施方案。

## Project Snapshot

- 仓库类型：`TODO(project)`
- 主要语言：`TODO(project)`
- 核心根目录：`TODO(project)`
- 风险最高的区域：`TODO(project)`
- 生成代码或外部代码：`TODO(project)`
- 必须保护的公共 API 或契约：`TODO(project)`

## Safe Change Zones

- 适合做局部修改的低风险路径：`TODO(project)`
- 常见安全任务：`TODO(project)`
- 推荐优先扩展的接入点：`TODO(project)`

## No-Touch Zones

- 修改前必须先获得确认的路径：`TODO(project)`
- 由生成流程或外部系统维护的文件：`TODO(project)`
- 不能随意变更的共享契约：`TODO(project)`
- 涉及 infra、billing、auth、security、release，必须先征得明确同意的区域：`TODO(project)`

## Working Rules

### Scope Control

- 先做能满足当前请求的最小改动。
- 未获批准前，不要把任务外扩成清理、重命名或架构调整。
- 遇到仓库级别的批量编辑需求，先停下来确认。

### Read Before Write

- 修改前先看最近的 README、配置、测试和 ownership 线索。
- 修改共享接口前，先确认调用方和影响面。
- 尽量依赖仓库内证据，而不是凭经验猜。

### Ownership and Approval

- 变更 public API、schema、auth、infra、build、release、deploy 行为前先确认。
- 进入其他团队负责的区域前先确认。
- 删除、移动、批量重生成文件前先确认。

### Editing Boundaries

- 优先做增量修改或严格局部修改。
- 除非用户明确要求，否则尽量保持现有模式。
- 不要把大范围格式化或清理混入无关任务。

## Verification Commands

- Lint：`TODO(project)`
- 定向测试：`TODO(project)`
- Build 或 typecheck：`TODO(project)`
- Smoke check：`TODO(project)`

## Risk Prompts

- 这次修改是否碰到了共享接口、公共契约或发布路径？
- 是否触碰了生成文件、镜像文件、外部同步文件或 owner 保护区域？
- 我是否把一个局部请求扩展成了仓库级清理？
- 我是否在修改前检查了最近的测试、配置和文档？

## Completion Checklist

- 关键 `TODO(project)` 都已填完。
- 安全区域和禁区都写清楚了。
- 审批门槛是具体的，不是抽象描述。
- 验证命令是可执行的。
- 首屏足够短、足够具体、足够项目化。

## Optional Project Notes

- 常见坑点：`TODO(project)`
- 常用本地命令：`TODO(project)`
- 评审要求：`TODO(project)`
- 发布或部署注意事项：`TODO(project)`
