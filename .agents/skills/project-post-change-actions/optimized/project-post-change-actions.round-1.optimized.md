---
name: project-post-change-actions
description: Use when files in a software project have been modified and the agent is preparing to finish, hand off, report, or ask for the next step after edits
---

# Project Post-Change Actions

## Overview

This skill is a project-level post-change checklist. Use it after modifying project files so the agent performs the actions listed here before finishing.

Keep this skill pure: it only covers post-change follow-up actions. It does not describe how to implement the original change.

## When to Use

Use after any project file edit, including:

- code changes
- config changes
- test changes
- documentation changes
- build, script, or dependency changes
- generated project artifacts that the user asked to create or update

## When NOT to Use

Do not use when:

- the conversation was read-only and no project files changed
- the user only asked for analysis, review, planning, or explanation
- the only changes were outside the project workspace
- another more specific post-change skill already overrides this one

## Quick Reference

| Step | Required action | Stop condition |
| --- | --- | --- |
| Inspect | Check the actual change set, including untracked files | If git is unavailable, say so |
| Commit draft | Suggest one standard commit message | Never commit or stage unless asked |
| README | Decide whether `README.md` needs an update | If yes, ask before editing |
| Report | Summarize changes, verification, and blocked items | Do not claim unrun checks passed |

## Change Set Rules

Before running the project actions, inspect the current change set:

- `git status --short`
- `git diff --stat`
- `git diff --cached --stat` if staged changes exist
- targeted diffs for files that affect README-level behavior

Treat untracked files from `git status --short` as part of the change set. `git diff --stat` alone is not enough.

If the working tree contains changes that may predate the current task, separate them:

- `Included in this change`: files clearly modified for the current user request.
- `Possibly unrelated`: files whose origin is unclear.

Do not include unrelated or pre-existing changes in the commit draft unless the user explicitly asks for a whole-worktree summary.

If the project is not a git repository, summarize the files changed during the current session from available context and say that git evidence is unavailable.

## Project Actions

Edit this section per project. The default actions are mandatory unless the user explicitly skips them.

### 1. Draft a Standard Commit

Produce one suggested Chinese commit message based on the included current-task modifications.

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
- Mention verification only when the current session actually ran it.
- Do not create, stage, amend, or push a commit unless the user explicitly asks.

Commit scope modes:

- Default mode: draft the commit only for files clearly changed by the current task.
- Staged-only mode: if the user is preparing an actual commit and staged changes exist, prefer a commit draft for staged changes only.
- Full-worktree mode: if the user asks for "all uncommitted changes", "whole worktree", "full commit", or similar wording, draft the commit for all modified, staged, and untracked files shown by `git status --short`.
- If unrelated or pre-existing changes are present but full-worktree mode was not requested, list them separately as possible exclusions instead of mixing them into the default commit draft.

### 2. Propose README Updates

Check whether `README.md` should change because of the current modifications.

README updates are usually relevant when the change affects:

- setup or installation
- commands or scripts
- configuration or environment variables
- public behavior, APIs, workflows, or user-facing features
- the list of available skills, tools, modules, or entry points

Always provide one of these outcomes:

- `README change recommended`: list the exact sections to update and the proposed content at a high level.
- `README change not needed`: explain briefly why the change set does not affect README-level usage, setup, behavior, or documentation.
- `README missing`: say no `README.md` was found and suggest whether creating one is useful.

If a README update is recommended, ask the user whether to apply it and stop before editing `README.md`. Do not edit `README.md` in the same step unless the user has already confirmed that exact update.

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

## Verification Boundary

This skill can require verification reporting, but it does not make checks pass by itself.

- Report commands actually run.
- Report checks intentionally skipped and why.
- Report failed commands with decisive error output.
- Do not claim tests, builds, lint, or README changes happened unless they happened in the current session.

## Final Response Requirements

When this skill runs, the final response must include:

- changed-file summary
- suggested standard commit
- README update outcome
- verification status, including commands actually run or explicitly not run
- blockers, if any, with the exact command or information needed to complete them

If README changes are recommended but not yet confirmed, end with a direct confirmation question and do not edit `README.md`.

## Common Mistakes

- Using `git diff --stat` and missing untracked files.
- Mixing unrelated dirty-worktree changes into the commit draft.
- Editing `README.md` after merely deciding it should change.
- Claiming tests passed because the change looks low risk.
- Turning this post-change checklist into implementation guidance for the original task.
