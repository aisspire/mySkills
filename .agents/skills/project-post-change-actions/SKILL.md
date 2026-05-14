---
name: project-post-change-actions
description: Use when files in a software project have been modified and the agent is preparing to finish, hand off, report, or ask for the next step after edits
---

# Project Post-Change Actions

## Overview

This skill is a project-level post-change checklist. Use it after modifying a project so the agent performs the local actions listed here before finishing.

Keep this skill pure: it should only describe what to do after a change, not how to implement the original change.

## When to Use

Use after any project edit, including:

- code changes
- config changes
- test changes
- documentation changes
- build, script, or dependency changes

Do not use when the conversation was read-only and no project files were changed.

## Required Context

Before running the actions, inspect the current change set:

- `git status --short`
- `git diff --stat`
- `git diff --cached --stat` if staged changes exist
- targeted diffs for files that affect README or user-facing behavior

If the project is not a git repository, summarize the files changed during the current session from available context and say that git evidence is unavailable.

## Project Actions

Edit this section per project. The default actions are mandatory unless the user explicitly skips them.

### 1. Draft a Standard Commit

Produce one suggested Chinese commit message based on the current modifications.

Use Conventional Commits by default, but write the summary and body in Chinese:

```text
type(scope): 中文摘要

- 具体改动 1
- 具体改动 2
- 需要时补充验证或文档说明
```

Rules:

- Choose the type from `feat`, `fix`, `docs`, `test`, `refactor`, `chore`, `build`, `ci`, or `perf`.
- Include a scope when the changed area is clear.
- Write the subject and body in Chinese, while keeping the Conventional Commit type and optional scope in English.
- Keep the subject specific and under 72 characters when practical.
- Do not claim tests passed unless the current session actually ran them.
- Do not create a commit unless the user explicitly asks.

Commit scope modes:

- Default mode: draft the commit only for files clearly changed by the current task.
- Staged-only mode: if the user is preparing an actual commit and staged changes exist, prefer a commit draft for staged changes only.
- Full-worktree mode: if the user asks for "all uncommitted changes", "whole worktree", "full commit", or similar wording, draft the commit for all modified, staged, and untracked files shown by `git status --short`.
- If unrelated or pre-existing changes are present but full-worktree mode was not requested, list them separately as possible exclusions instead of mixing them into the default commit draft.

### 2. Propose README Updates

Check whether `README.md` should change because of the current modifications.

**REQUIRED BUNDLED SUB-SKILL:** Load `subskills/readme-generation/SKILL.md` when a README update is recommended, when `README.md` is missing and creation would be useful, or when the user asks to draft/apply the README change. Use the bundled sub-skill to inspect project facts, request missing screenshots/background/safety details, and draft truthful README content. If standalone README work is needed outside this post-change workflow, copy `subskills/readme-generation` to a normal skills directory as `readme-generation`.

Always provide one of these outcomes:

- `README change recommended`: list the exact sections to update and the proposed content at a high level.
- `README change not needed`: explain briefly why the change set does not affect README-level usage, setup, behavior, or documentation.
- `README missing`: say no `README.md` was found and suggest whether creating one is useful.

If a README update is recommended, ask the user whether to apply it. Do not edit `README.md` until the user confirms. If the user confirms, load the bundled README sub-skill and keep the edit scoped to the confirmed README work.

## Adding More Actions

Add project-specific actions below this line. Keep each action concrete and checkable.

Recommended format:

```markdown
### N. Action Name

When this applies:
- condition

Do:
- exact action

Do not:
- boundary
```

## Final Response Requirements

When this skill runs, the final response must include:

- changed-file summary
- suggested standard commit
- README update outcome
- verification status, including commands actually run or explicitly not run

If any required action cannot run, state the blocker and the exact command or information needed to complete it.
