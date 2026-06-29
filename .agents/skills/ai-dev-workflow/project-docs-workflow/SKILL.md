---
name: project-docs-workflow
description: Use when bootstrapping, reading, updating, or repairing a document-driven AI development system with docs/index.md, project.md, features, api, data, tests, architecture, flows, adr, and docs/ai templates. 用于建立、读取、更新或修复文档驱动的 AI 开发体系，包括索引、项目背景、功能、接口、数据、测试、架构、流程、ADR 和 AI 协作文档。
---

# Project Docs Workflow

## Overview

用于把项目文档组织成“索引 + 分区 + 局部更新”的 AI 开发上下文系统。

核心目标不是生成一篇巨大的项目知识地图，而是让 AI 每次按 `docs/index.md` 找到本次任务需要的最小上下文，并在修改后只更新相关文档。

## Document Layout

推荐结构：

```text
docs/
  index.md
  project.md
  features/
  api/
  data/
  tests/
  architecture/
    overview.md
  flows/
    ai_feature_change_flow.md
  adr/
  ai/
    rule_candidates.md
    agents_patch_suggestions.md
```

职责边界：

| 路径 | 职责 |
| --- | --- |
| `index.md` | 地图：文档导航、模块索引、任务路由、权威来源 |
| `project.md` | 项目背景：目标、范围、角色、技术栈、当前阶段 |
| `features/` | 要做什么：功能需求、业务规则、验收口径 |
| `api/` | 怎么通信：前端够用的接口契约 |
| `data/` | 数据是什么：实体、字段、来源、生命周期 |
| `tests/` | 怎么验收：测试点、回归点、手工检查清单 |
| `architecture/` | 系统怎么组织：模块边界、依赖、部署、技术约束 |
| `flows/` | 事情怎么流转：用户流程、业务流程、AI 开发流程 |
| `adr/` | 为什么这么决定：重要决策、取舍、后果 |
| `ai/` | AI 协作规则候选和 `AGENTS.md` 建议补丁 |

## When to Use

- 用户要建立项目文档体系、文档索引或 AI 开发上下文。
- 用户要按功能、接口、数据、测试、架构、流程、ADR 拆分文档。
- 开发前需要根据 `docs/index.md` 读取最小相关上下文。
- 开发中发现代码与文档不一致，需要记录或修复 drift。
- 开发后需要更新相关项目文档，但不需要完整收尾报告。

## When NOT to Use

- 用户要求重型接口全量核对，此时使用 `api-doc-generation`。
- 用户要求数据库真实 schema 发现，此时使用 `database-schema-bootstrap`。
- 用户只要求代码修改且没有文档上下文要求。
- 用户只要求 README 更新，此时可使用 README 子能力或 `project-closeout`。

## Bootstrap Workflow

当项目缺少文档体系时：

1. 检查是否已有 `docs/`、README、架构说明、接口说明。
2. 创建缺失的目录和模板。
3. 先写短的 `docs/index.md` 和 `docs/project.md`。
4. 固定创建：
   - `docs/architecture/overview.md`
   - `docs/flows/ai_feature_change_flow.md`
5. 只为当前已知模块创建必要文档，不要批量生成空文件。

模板位于 `assets/templates/`，按需读取或复制。

## Pre-Change Workflow

开发前：

1. 读取 `docs/index.md`。
2. 根据任务类型选择最小文档集合：
   - 功能变化：`features/` + `tests/`
   - 接口变化：`api/` + `features/` + `data/`
   - 数据变化：`data/` + `architecture/overview.md`
   - 流程变化：`flows/` + `features/`
   - 架构变化：`architecture/` + `adr/`
3. 对照代码确认文档是否过期。
4. 发现 drift 时标记，不要把旧文档当事实。

## API Docs Boundary

`docs/api/<module>.md` 只要求前端够用：

- 接口用途
- 方法和路径
- 请求参数
- 返回字段
- 前端调用顺序
- 不确定项

不要把它写成后端全量字段考古。需要 controller/router/service/DTO/VO/BO 全链路核对时，使用独立 `api-doc-generation`。

## Post-Change Workflow

修改后：

1. 根据实际变更更新相关文档。
2. 更新 `docs/index.md` 中的模块导航和状态。
3. 如果做了重要技术取舍，新增或更新 `adr/`。
4. 如果影响 AI 开发流程或规则候选，交给 `project-rules-maintainer`。
5. 如果进入交付收尾，交给 `project-closeout` 处理 README、验证状态和 commit 建议。

## Common Mistakes

- 每次把整个 docs 目录塞进上下文。
- 把 `docs/api/` 写成后端全量实现文档。
- 只生成文档，不维护 `docs/index.md`。
- 架构文档写成超长总文档，没有 `architecture/overview.md` 入口。
- 文档与代码冲突时不标记 drift。

## Template Index

- `assets/templates/index.md`
- `assets/templates/project.md`
- `assets/templates/feature.md`
- `assets/templates/api.md`
- `assets/templates/data.md`
- `assets/templates/test.md`
- `assets/templates/architecture-overview.md`
- `assets/templates/flow.md`
- `assets/templates/ai-feature-change-flow.md`
- `assets/templates/adr.md`
