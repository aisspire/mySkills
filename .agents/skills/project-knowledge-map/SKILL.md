---
name: project-knowledge-map
description: analyze the current working directory as a git-backed software project and produce a high-quality project overview document for future ai development. use when the user wants a project function and structure overview, architecture梳理, codebase knowledge base, implementation map, modification impact guide, or incremental update of an existing project analysis document. supports backend, frontend, full-stack, monorepo, sdk, service, tool, mobile, desktop, and multi-service repositories. requires local files and git only, must not modify project code, and should save the final markdown under docs/ using the required timestamp and commit-hash naming convention.
---

# Project Knowledge Map

## Overview

Use this skill to inspect the current working directory as a software project, determine the project type and architecture from actual code and git history, and generate a durable markdown knowledge-base document for later AI-assisted development.

The final artifact is a markdown file saved under `docs/` and named:

`docs/{YYYY-MM-DD_HH-mm}_{short-hash}_项目文档.md`

Do not change project source code, configuration, dependencies, lockfiles, or git history. Creating or updating the documentation file under `docs/` is allowed only after the user has confirmed how to proceed with the current git state.

## Non-negotiable constraints

- Use only local files and git.
- Do not browse the web.
- Do not edit project code or project configuration.
- Do not auto-commit, stash, reset, or clean the repository.
- Do not pretend a conclusion is confirmed when it is only inferred.
- Prefer actual call paths, configuration wiring, and code responsibilities over directory-name guesswork.
- Focus depth on core modules, core call chains, main flows, and shared infrastructure.
- Keep secondary modules brief.

## Required workflow

Follow this sequence every time.

### 1. Inspect git state first

Run git status before generating the document.

If there are uncommitted changes:
- Tell the user clearly that the project currently has uncommitted modifications.
- Recommend committing first so the document is traceable to a stable version.
- Wait for the user's decision.

If the user chooses to commit first:
- Stop here.
- Resume only after the user indicates the commit is complete.
- Re-check git state before continuing.

If the user refuses or postpones committing:
- Use the latest committed revision as the naming basis.
- Use the latest commit short hash for the filename.
- Add a prominent note at the start of the generated document stating that the working tree has uncommitted changes and the document is based on the latest committed version, so the live code may already differ.

If there are no uncommitted changes:
- Use the current HEAD short hash for the filename.
- Continue without the warning note above.

### 2. Determine naming basis

Use:
- timestamp format: `YYYY-MM-DD_HH-mm`
- git hash: 8-character short hash from the chosen commit basis
- final path: `docs/{timestamp}_{hash}_项目文档.md`

Create `docs/` only if it does not already exist.

### 3. Check for older project-analysis documents

Before drafting, inspect `docs/` for existing project-analysis documents.

Treat a file as relevant when one or more of these is true:
- filename matches the target naming pattern
- filename clearly indicates project overview, project analysis, architecture梳理, 项目文档, knowledge base, or similar purpose
- content is obviously an earlier project-wide analysis document

If relevant older documents exist:
- Find the most recent and most relevant one.
- Read it before drafting the new document.
- Extract its document version hint if possible from filename or opening notes.
- Compare that document's apparent version basis with git history and current code.
- Update incrementally instead of rewriting mechanically.

Focus the incremental review on meaningful changes such as:
- added or removed core modules
- changed main flows or call chains
- changed directory responsibilities
- changed shared capabilities or infrastructure
- changed key entities, schemas, DTOs, interfaces, or contracts
- changed common modification entry points or likely impact surfaces

If no older document exists:
- generate from scratch.

### 4. Build a project understanding before writing

Inspect enough of the repository to classify the project correctly. Do not assume the type in advance.

Actively determine whether the project is primarily:
- backend
- frontend
- full-stack
- monorepo
- multi-service or microservice
- mobile
- desktop
- sdk or library
- tool or cli
- service platform
- hybrid of the above

Use evidence such as:
- repository layout
- package manifests and workspace config
- build and deployment config
- routing or controller entrypoints
- framework bootstrapping
- service composition
- db models and migrations
- tests
- task runners
- docs and README files

Read selectively but sufficiently across:
- README and docs
- root config and workspace files
- important manifests and dependency definitions
- key source directories
- routes/controllers/pages/components
- services/use-cases/domain models/entities/repositories
- middleware/guards/interceptors/filters/events/jobs/queues/schedulers
- schemas/DTOs/VOs/types/contracts
- infra/config/logging/cache/auth/permission integration
- tests when they clarify intended behavior

Separate the code into:
- business core
- shared/common capability
- infrastructure/base layer
- adapters or boundary glue
- tooling/scripts/configuration
- legacy, experimental, or possibly abandoned areas when evidence supports that conclusion

### 5. Analyze with depth priorities

Spend the most effort on:
1. core call chains
2. core modules
3. primary flows
4. shared mechanisms and reusable infrastructure

Do not give every module equal space.

For large repositories, optimize for what later AI development most needs:
- main entrypoints
- business backbone
- high-frequency modification zones
- reusable shared capabilities
- modules with broad downstream impact
- structural spine of the system

### 6. Distinguish evidence levels explicitly

Throughout the document, distinguish among:
- confirmed from code or config
- inferred from code structure or usage patterns
- currently uncertain
- recommended for human confirmation

Never present an inference as a confirmed fact.

### 7. Write and save the document

Write the final markdown directly to the required path under `docs/`.

Do not stop at an outline. Produce a complete, high-value document.

After writing the file, tell the user the saved path only. No extra summary is required unless the user asks.

## Required document structure

Use this structure unless the project shape requires a small adaptation. Keep section names explicit and searchable.

# 项目功能与结构总览文档

## 0. 文档说明
Include:
- generation time
- repository root or analyzed scope when knowable
- naming git hash basis
- whether uncommitted changes existed
- whether an older document was used as baseline
- evidence note about confirmed vs inferred vs uncertain content

## 1. 项目概述
Cover:
- main purpose
- likely target users or business scenario
- core value
- main problem currently solved
- judged project type and evidence
- judged architecture shape and evidence

## 2. 核心功能总览
For each core module, explain:
- module name
- purpose
- sub-capabilities
- external capability it provides
- main code locations
- core dependencies
- relation to other modules
- why it is core
- where to look first for future changes
- likely impact radius of common modifications

Secondary modules may be shorter but still定位清楚.

## 3. 系统结构与模块分层
Adapt to the actual project. Explain the real layering or modular shape, such as:
- request or interaction entry layer
- business handling layer
- data access layer
- model/entity/domain layer
- middleware/guard/filter/interceptor layer
- config and infrastructure layer
- events/jobs/queues/schedulers/message handlers
- frontend route/component/state structure when present
- service-to-service boundaries when present

## 4. 目录结构与职责说明
Explain responsibilities, collaboration, and category of key directories or modules.
Do not dump a bare tree without commentary.
Call out when an area appears to be:
- business core
- shared capability
- infrastructure
- adapter or glue
- tooling/config
- legacy or possibly abandoned

## 5. 核心链路与主流程
This is a priority section.
Describe major end-to-end flows step by step. Examples include:
- request entry to response
- login/auth/permission flow
- create/query/update/delete flow for the main business object
- file upload/download flow
- event, queue, callback, cron, or sync flow
- primary business closure from entry to persistence/output

For each flow, note:
- start point
- key modules crossed
- data flow
- state transitions when visible
- shared mechanisms used
- extension points
- high-risk modification points
- likely upstream/downstream impact

## 6. 通用能力 / 公共机制 / 高复用基础设施
This is a priority section.
Summarize reusable or high-impact capabilities such as:
- auth and permission
- config management
- data access abstraction
- orm/repository/query layer
- api or sdk wrappers
- validation
- exception handling
- logging and monitoring
- cache
- message or event system
- scheduling
- middleware mechanisms
- plugin mechanisms
- common base classes, utils, hooks, helpers, service bases

For each capability, explain:
- what problem it solves
- main entrypoints
- dependent modules
- when future work should reuse it
- impact radius if changed

## 7. 数据模型 / 核心实体 / 领域对象（如适用）
When present, summarize:
- core entities/models/schemas
- relationships
- rough business meaning of important fields when inferable
- input/output objects vs persistence objects vs domain objects
- likely impact of entity changes

## 8. 面向后续 AI 开发的定位与修改指引
Make this practical.
Tell later AI:
- what to read first before new feature work
- where to start tracing for API logic changes
- where to inspect for data logic changes
- what shared capabilities to reuse first
- which modules are highly coupled or high impact
- which features span multiple directories and require cross-checking
- what locations form the system backbone
- what are common extension points
- what are common risk points
- what modification types usually affect which modules
- suggested search paths for quick requirement localization

## 9. 旧文档增量更新说明（如适用）
If an older document was used, include:
- which older document was referenced
- major updates vs that baseline
- which updates came from git-visible changes
- which updates came from improved interpretation of the codebase
- what still needs human confirmation

## 10. 风险、缺失与推断说明
Call out:
- partially unconfirmed functions
- naming/responsibility mismatch
- hidden conventions
- suspected abandoned code
- scattered shared capabilities
- changes likely to cause large ripple effects

Split clearly into:
- confirmed
- inferred
- uncertain
- recommended for human confirmation

## 11. 后续 AI 开发快速索引
Provide a compact, searchable index mapping:
- common request types
- suggested first modules/directories to inspect
- representative entry files/services/entities
- reusable existing capabilities
- likely impact radius

## Output quality rules

- Explain not only what exists, but how pieces collaborate.
- Prefer code-backed facts over naming assumptions.
- Connect functionality that is spread across multiple directories.
- Mention impact range when giving modification guidance.
- Keep language professional, precise, restrained, and easy to scan.
- Avoid empty statements and jargon padding.
- When the project is large, begin with a high-level framing and then drill down.

## Interaction rules

- Before writing the final document, finish the repository inspection, git-state handling, naming-basis decision, and old-document check.
- When uncommitted changes exist, do not continue past inspection until the user decides whether to commit first.
- Once the user has confirmed how to proceed, continue automatically and save the markdown file.
- Do not produce a chat summary instead of the file.
- After completion, return the saved file path.
