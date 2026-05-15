# Declaration Template

Use this before any project norm affects behavior.

```text
本次使用的项目规范：
- [confidence][scope] rule summary
  来源：path-or-evidence#rule-id
  例外：exception summary

本轮覆盖：
- current user instruction overrides stored rule summary

候选但未生效的观察：
- [observed][scope] candidate summary

不确定或冲突：
- [conflict][scope] conflict summary; 本轮不会套用该规则。
```

If there are no active norms:

```text
本次没有发现需要套用的已确认项目规范。
```

Keep the declaration short. List only norms relevant to the current task.

## Declaration Rules

- Do not list the entire norm file when only one or two rules apply.
- Do not apply `observed`, `uncertain`, `conflict`, or `deprecated` rules.
- If a current user instruction overrides a stored norm, say that the current instruction wins for this turn.
- If the user corrects the declaration, update the stored norm or record the correction before continuing when a file update is appropriate.
- If there is no current-turn override, omit the `本轮覆盖` section.
