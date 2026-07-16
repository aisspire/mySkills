---
name: project-docs-workflow
description: Use when a project needs to bootstrap, read, update, consolidate, or repair document-driven development docs, route minimum context through docs/index.md, or resolve drift between code and project documentation. 用于项目需要建立、读取、更新、收敛或修复文档驱动体系、通过 docs/index.md 路由最小上下文，或处理代码与项目文档不一致时。
---

# Project Docs Workflow

## Overview

把项目文档维护成“当前事实 + 渐进式路由”的开发系统。

目标：

- AI 先读短索引，再按任务加载最小上下文。
- 每段重要代码逻辑都能追溯到业务规则、流程或技术约束。
- 文档用业务语言解释代码为什么这样运行，而不是复述类和方法。
- 开发中的未明确决策、妥协、未采用方案和后续触发条件得到增量记录。
- 当前文档保持精炼；详细交付物和历史分析按需读取。

## Progressive Routing

按三层组织和加载文档：

| 层级 | 内容 | 加载规则 |
| --- | --- | --- |
| L0 导航层 | `docs/index.md` | 每次文档驱动任务先读，只放路由和权威来源 |
| L1 当前事实层 | `features/`、`flows/`、`api/`、`data/`、`tests/`、`architecture/` | 只读本次任务相关文件 |
| L2 深入与历史层 | 详细前端 API 文档、`adr/`、`implementation-notes.md`、`old/` | 发生相应问题或需要追溯时再读 |

不要因为某个目录存在就整目录加载。

## Document Layout

推荐结构：

```text
docs/
  index.md
  project.md
  features/
  flows/
  api/
  data/
  tests/
  architecture/
    overview.md
  adr/
  <domain>/<feature>/
    implementation-notes.md
    接口文档.md
  old/
  ai/
```

职责边界：

| 文档 | 回答的问题 | 默认维护时机 |
| --- | --- | --- |
| `index.md` | 这次任务应读什么，权威来源是什么 | 文档入口或状态变化 |
| `project.md` | 项目做什么，有哪些全局约束 | 项目范围或全局规则变化 |
| `features/` | 业务要实现什么，规则和验收是什么 | 功能或业务规则变化 |
| `flows/` | 用户、系统和数据如何流转 | 流程、状态、权限或异常路径变化 |
| `api/` | 有哪些接口，关键请求和返回是什么 | 现有接口地图变旧时局部更新 |
| `data/` | 核心对象、关系、来源和生命周期是什么 | 数据语义或关系变化 |
| `tests/` | 如何验证需求和回归风险 | 验收口径变化 |
| `architecture/` | 模块边界、依赖和技术约束是什么 | 架构影响 |
| `adr/` | 重要且长期有效的决策为什么这样做 | 跨模块或高成本决策 |
| `implementation-notes.md` | 规格未说明时做了什么决定和妥协 | 开发过程中增量追加 |
| 详细接口文档 | 前端如何独立完成联调 | 用户明确要求产出或更新时 |
| `old/` | 过去如何分析、哪些结论已失效 | 仅追溯时读取 |

## 操作规程与项目事实

通用操作规程和项目事实必须分开：

| 位置 | 只记录 |
| --- | --- |
| 本 skill | 通用的文档读取、更新、修复和路由方法 |
| 项目级 `AGENTS.md` | 本项目强制执行的 AI 协作规则、禁区和特殊门禁 |
| `docs/index.md` | 文档导航、权威来源、模块路由和已知 drift |
| `docs/project.md` | 项目目标、范围、角色、术语和全局业务约束 |
| 其他项目文档 | 当前业务、流程、接口、数据、测试和架构事实 |

不要把“开发前读索引”“只加载最小上下文”“何时更新文档”等通用 skill 规则复制到 `project.md` 或普通流程文档中。

不要默认创建“AI 功能变更流程”。只有项目存在区别于本 skill 的真实团队审批、测试、发布或协作流程，并且用户要求记录时，才按需使用 `development-change-flow.md` 模板。该文档描述团队实际流程，不描述 AI 的通用操作方法。

## When to Use

- 建立、读取、维护或修复项目文档体系。
- 开发前需要用 `docs/index.md` 路由最小上下文。
- 开发中需要让需求、流程、数据约束和实现保持对应。
- 文档与代码不一致，需要识别和修复 drift。
- 历史文档过多、当前文档过少，需要收敛当前事实并保留追溯入口。

## When NOT to Use

- 用户明确要求交付完整前端接口文档：使用 `api-doc-generation`。
- 用户只需要一次性代码解释，不要求维护项目文档。
- 用户要求发现真实数据库结构：使用数据库元数据能力。
- 用户只要求更新 README 或做项目收尾。

## Source of Truth

按以下优先级判断当前事实：

1. 用户本次明确规格和已确认业务口径。
2. 当前可运行代码、配置、数据库迁移和实际接口行为。
3. 活跃项目文档。
4. 历史文档和旧方案。

代码与文档冲突时：

- 不静默选择旧文档。
- 在 `docs/index.md` 的 drift 区或相关文档中标出冲突。
- 根据任务性质确认是代码缺陷还是文档过期。
- 修复后只保留一个当前口径；历史原因放入实施记录、ADR 或 `old/`。

## Requirement-to-Code Traceability

重要业务规则使用短而稳定的规则 ID，例如 `ALARM-R01`。

在功能或流程文档中记录：

- 触发条件。
- 业务行为。
- 约束和异常。
- 验收结果。
- 实现范围，例如模块、组件或接口名称。

不要求逐字段证据列、代码行号或长调用链。目标是能从规则找到实现范围，也能从代码变更找到受影响规则。

当前文档不能只剩概览。至少要让不了解源码的人读懂业务目标、主流程、状态、关键分支、权限和业务不变量。

## Pre-Change Workflow

1. 读取 `docs/index.md`。
2. 根据任务选择最小集合：

| 变化 | 优先读取 |
| --- | --- |
| 功能或规则 | `features/` + 相关 `flows/` + `tests/` |
| 接口语义 | `api/` + `features/` + `flows/`，必要时 `data/` |
| 数据语义 | `data/` + `features/`，必要时 `architecture/overview.md` |
| 状态或流程 | `flows/` + `features/` + `tests/` |
| 架构 | `architecture/` + 相关 `adr/` |
| 历史决策 | 当前文档仍不能解释时再读 `implementation-notes`、`adr/`、`old/` |

3. 对照代码确认文档是否仍然有效。
4. 列出本次会影响的规则 ID、流程、接口和数据对象。
5. 若任务规格没有覆盖关键决定，准备增量记录 `implementation-notes.md`。

## During Development

持续维护当前事实，不等到结束后凭记忆补写：

- 业务规则变化：更新 `features/`。
- 流程、状态、权限、异常路径变化：更新 `flows/`。
- 数据关系或生命周期变化：更新 `data/`。
- 验收口径变化：更新 `tests/`。
- 规格外决定、妥协、未采用方案：追加 `implementation-notes.md`。
- 长期、跨模块、高成本决策：新增或更新 ADR。

实施记录只记“为什么和取舍”，不记 routine 命令流水。

功能、流程、API 摘要和数据文档维护“当前正确版本”，直接修正文；历史差异留给 Git、实施记录或 ADR，不在活文档中层层堆叠旧口径。

## API Documentation Boundary

### Compact API Map

`docs/api/<module>.md` 是给 AI 和开发者快速路由的接口地图，至少包含：

- 接口名称、方法、路径和用途。
- 请求对象或关键请求字段。
- 返回类型、数据层级和关键返回字段。
- 所属业务流程链接。
- 已知兼容性或不一致。

它不需要逐字段后端考古，也不需要完整请求/响应示例。

普通开发不要自动启动重型接口文档生成。若接口地图中的事实因代码变更而过期，只局部更新受影响内容。

### Frontend Delivery Document

只有用户明确要求“产出、更新、交付接口文档或前端联调文档”时，才使用 `api-doc-generation` 创建或更新详细文档。

详细接口文档应记录版本和差异；项目接口地图只保留当前摘要并链接到详细文档。

## Business Flow Documentation

流程文档用自然语言先说明：

- 目标和参与者。
- 前置条件。
- 主流程。
- 分支和失败路径。
- 状态变化。
- 数据传递。
- 权限和业务不变量。

按复杂度选图，不为画图而画图：

| 场景 | 推荐表达 |
| --- | --- |
| 简单线性流程 | 编号步骤 |
| 三步以上且有分支 | Mermaid `flowchart` |
| 多角色、跨服务、异步交互 | Mermaid `sequenceDiagram` |
| 明确状态和非法迁移 | Mermaid `stateDiagram-v2` |
| 三个以上实体或复杂关系 | Mermaid `erDiagram` |

图只表达关系；业务目的、约束和边界仍用自然语言说明。

## Data Documentation

数据文档优先描述业务语义：

- 核心实体及职责。
- 关键字段含义和来源。
- 实体关系。
- 创建、更新、删除、归档和快照规则。
- 权限、租户、唯一性和一致性约束。

不要默认复制完整表结构。需要真实 schema 时再读取数据库元数据。

## Decisions and Historical Material

使用不同载体记录不同决策：

| 内容 | 位置 |
| --- | --- |
| 本次规格未说明的局部决定 | `implementation-notes.md` |
| 未采用方案、妥协、技术债、重拾条件 | `implementation-notes.md` |
| 长期稳定、跨模块或难以回退的决定 | `adr/` |
| 明确延期且用户要求记录的功能 | `docs/BACKLOG.md` |
| 已失效的大量分析和旧方案 | `old/` |

历史文档必须标明“历史/已被替代”和当前文档链接，不得进入默认任务路由。

整理历史材料时不要把当前文档压缩成几句摘要。应删除重复分析，但保留当前有效的业务规则、流程分支、状态和约束。

## Post-Change Workflow

1. 更新受影响的当前文档，不批量重写无关文件。
2. 更新 `docs/index.md` 的链接、状态或 drift。
3. 检查每个代码行为变化是否能对应到业务规则或流程。
4. 检查规格外决定是否已经进入实施记录。
5. 只有明确要求时才生成或更新完整前端 API 文档。
6. 说明哪些事实已由代码确认，哪些仍依赖部署、外部系统或业务确认。

## Resources

按任务读取或复制 `assets/templates/`：

- `index.md`
- `project.md`
- `feature.md`
- `flow.md`
- `api.md`
- `data.md`
- `test.md`
- `architecture-overview.md`
- `implementation-notes.md`
- `adr.md`

项目有特殊审批、测试、发布或协作流程时，才使用可选模板：

- `development-change-flow.md`

## Common Mistakes

- 每次加载整个 `docs/`。
- 用一篇超长文档同时服务 AI、开发者、前端和历史追溯。
- 把通用 skill 操作规程复制进 `project.md` 或项目流程文档。
- 默认创建只描述 AI 如何维护文档的流程文件。
- 功能文档只有模块介绍，没有可验证业务规则。
- 流程文档只列 Controller 方法，没有用户目标、状态和异常。
- `docs/api/` 只有路径，没有请求和返回摘要。
- 普通代码修改自动生成重型前端接口文档。
- 每个字段都附代码位置，造成文档噪声和维护负担。
- 把历史分析继续当当前口径。
- 只记录最终方案，不记录未采用方案、妥协和重拾条件。
