---
name: project-norms
description: Use when a repository has project-specific norms, remembered user preferences, repeated local conventions, verification exceptions, security expectations, or correction-driven rules that should be declared before influencing AI behavior
---

# Project Norms

## Overview

This skill manages repository-specific norms from explicit user confirmation, repository evidence, and correction history.

Core rule: before any norm affects behavior, declare the active norms, source, confidence, scope, and exceptions. Unconfirmed observations are advisory only.

## When to Use

Use this skill when:

- The user says "remember this", "以后都这样", "这个项目默认", "项目规范", or similar.
- The repository contains `.agents/project-norms/rules.yaml`.
- A project task may be affected by local testing, security, git, documentation, reporting, dependency, release, or architecture habits.
- The user corrects the agent and wants that correction to influence future work in this project.
- Another project-level skill may apply and local norms should be declared first.

## When NOT to Use

Do not use this skill when:

- The user gives a one-off instruction without asking to remember it.
- There is no norm file and no request to create or update one.
- A rule is already enforced mechanically by formatter, linter, tests, or repository config.
- The rule belongs in stable architecture ownership docs instead of behavior memory.

## Storage

Default repository storage:

```text
.agents/project-norms/
  rules.yaml
  observations.md
  changelog.md
```

Skill references:

- Read `references/rule-schema.md` before creating or editing `rules.yaml`.
- Read `references/declaration-template.md` before declaring norms to the user.

Create storage files only when the user explicitly asks to start project norm tracking or confirms that a rule should be remembered.

## Norm Levels

- `confirmed`: the user explicitly confirmed this as a project norm. It may constrain behavior.
- `repo-evidence`: the repository documents this norm. It may constrain behavior if the evidence is cited.
- `observed`: the agent noticed a repeated pattern. It must be listed as a candidate only.
- `uncertain`: the rule is ambiguous. Ask before using it.
- `conflict`: current guidance conflicts with older guidance. Do not apply until resolved.
- `deprecated`: preserved for audit history, not applied.

## Required Workflow

### 1. Load

Check whether `.agents/project-norms/rules.yaml` exists. If it exists, read it before making project behavior decisions.

If `observations.md` exists, read only relevant recent entries when the current task touches the same scope.

### 2. Declare

Before applying any norm, write a short declaration:

- active norms relevant to this turn
- source path or evidence
- confidence and scope
- exceptions
- current-turn overrides
- observed candidates that are not active
- conflicts or uncertainty that will not be applied

If no norms apply, say so briefly.

### 3. Apply

Apply only norms with `status: active` and confidence `confirmed` or `repo-evidence`.

Do not apply observed, uncertain, conflict, or deprecated entries. Mention them only as candidates or open questions.

Apply each norm only inside its declared `scope`. If a norm must cross scope boundaries, ask or require explicit evidence.

### 4. Current-Turn Overrides

Current user instructions override stored project norms for this turn.

Do not store a current-turn override as a durable norm unless the user explicitly says to remember it. If the override contradicts an active norm, declare the conflict and ask whether the stored norm should be changed when the durable intent is unclear.

### 5. Update

Do not silently learn. A norm may be added to `rules.yaml` only when the user clearly confirms durable intent, such as:

- "记住这条"
- "以后这个项目都这样"
- "这是项目规范"
- "把这条加入项目规范"

Repeated behavior without explicit confirmation may be written to `observations.md`, but it remains non-binding.

Every rules update must add a `changelog.md` entry with:

- date
- rule id
- action: added, updated, deprecated, conflict-marked, or resolved
- reason
- whether the change is durable or current-turn only

### 6. Correct

When the user says a norm is wrong:

- Stop applying it immediately for the current turn.
- Mark the rule as `conflict` or `deprecated`, or update it if the replacement is explicit.
- Add a `changelog.md` entry with the date, changed rule id, and reason.
- On future turns, declare the conflict instead of applying the old habit.

## Observation Format

Use `observations.md` for candidates only:

```markdown
## YYYY-MM-DD - candidate-id

- scope:
- observed pattern:
- evidence summary:
- why it is not confirmed:
- suggested confirmation question:
```

Never treat this file as an authority source.

## Priority

When rules conflict, use this order:

1. System and developer instructions.
2. Current user instruction.
3. Repository files and explicit project docs.
4. `project-norms` confirmed rules.
5. Observations and inferred habits.

Current explicit user instructions override older project norms for the current turn. They do not automatically rewrite stored norms unless the user says to remember the change.

## Safety Boundaries

Project norms cannot authorize:

- destructive git or filesystem actions without explicit current approval
- hiding errors, stack traces, failed commands, or unverified claims
- skipping required safety review for auth, permissions, secrets, migrations, billing, or data deletion
- treating an observed habit as confirmed
- rewriting repository history or publishing changes without current approval

Verification skip rules must include exceptions for high-risk changes. If an exception is missing and the task touches security, data, auth, permissions, migrations, build, release, or shared contracts, ask or run targeted verification instead of skipping by habit.

## Quick Reference

| Situation | Action |
| --- | --- |
| `rules.yaml` exists | Read and declare relevant active norms before behavior is constrained |
| User says "remember" | Add or update a confirmed rule and changelog |
| User gives a one-off override | Follow it for this turn, do not store it |
| Repeated preference observed | Record in `observations.md`, not `rules.yaml` |
| User corrects a norm | Stop using it, update status, write changelog |
| Norm conflicts with current request | Follow current request for this turn and ask whether to update stored norms |
| Norm is uncertain | Declare uncertainty and ask before applying |

## Common Mistakes

- Treating one successful past behavior as a durable norm.
- Saying "project usually skips tests" without listing risk exceptions.
- Applying a norm before declaring it.
- Hiding candidates from the user, which prevents correction.
- Mixing architecture boundaries into behavior memory. Use `large-project-ai-guardrails` for stable architecture and ownership rules.
- Letting a stale rule survive after the user corrects it.
- Storing current-turn overrides as durable norms without explicit confirmation.

## Baseline Evidence Status

This skill is statically structured for writing quality, but it has not completed a full RED/GREEN/REFACTOR pressure-test cycle. Do not claim full writing-skills compliance until baseline failure evidence and with-skill verification have been recorded.
