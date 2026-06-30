---
name: backlog-capture
description: Use when the user explicitly asks to record a deferred feature hook in docs/BACKLOG.md with phrases like "记一下", "未来实现", "以后可能做", "功能暂不实现", "先不做，留个钩子", or "放到 backlog"; do not use for casual brainstorming, inferred future work, or ordinary TODOs.
---

# Backlog Capture

## Overview

Record only explicit deferred-feature hooks in `docs/BACKLOG.md`. Keep each entry to one sentence so the file stays a lightweight reminder, not a feature spec.

## When to Use

Use this skill only when the user clearly asks to preserve a future implementation idea, for example:

- "记一下，未来实现..."
- "这个功能暂不实现，放 backlog"
- "先不做，留个钩子"
- "以后可能做，记录一下"

## When NOT to Use

- Do not record casual brainstorming, weak "以后可以" discussion, or options the user has not asked to save.
- Do not infer future work from code review, implementation tradeoffs, or your own suggestions.
- Do not use this for current-sprint TODOs, bug lists, acceptance criteria, API notes, ADRs, or project rules.
- Do not update `docs/index.md`.

## Workflow

1. Use `docs/BACKLOG.md` at the project root.
2. If the file is missing, create it with only `# BACKLOG` and the first entry.
3. Append one bullet using the current date:
   `- YYYY-MM-DD: <一句话功能钩子>。`
4. Keep the entry as one sentence. Do not add implementation steps, rationale, owners, priority, or acceptance criteria.
5. If the same hook already exists, do not duplicate it; report the existing entry unless the user asked to reword it.
6. After editing, report the path and exact sentence added or reused.

## Entry Examples

```md
- 2026-06-30: 未来可能实现按标签筛选 backlog 条目。
- 2026-06-30: 功能暂不实现第三方登录，仅保留后续扩展钩子。
```
