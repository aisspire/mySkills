# Rule Schema

Use this schema for `.agents/project-norms/rules.yaml`.

```yaml
version: 1
updated_at: YYYY-MM-DD
rules:
  - id: short-kebab-case-id
    status: active
    confidence: confirmed
    source: user-confirmed
    scope: verification
    rule: One concrete norm that can be applied or rejected.
    exceptions:
      - Concrete exception where this rule must not be applied blindly.
    evidence:
      - date: YYYY-MM-DD
        type: user-confirmed
        note: Short reason or quoted summary, not a long transcript.
    last_reviewed: YYYY-MM-DD
```

Use this schema for `.agents/project-norms/changelog.md` entries:

```markdown
## YYYY-MM-DD - rule-id

- action: added | updated | deprecated | conflict-marked | resolved
- durable: true | false
- reason:
- previous summary:
- new summary:
```

## Allowed Values

`status`:

- `active`: may apply when confidence allows.
- `conflict`: do not apply; ask or resolve first.
- `deprecated`: retained for audit only.

`confidence`:

- `confirmed`: user explicitly confirmed the durable norm.
- `repo-evidence`: repository docs or config prove the norm.
- `observed`: candidate only; do not apply as a hard constraint.
- `uncertain`: ambiguous; ask before applying.

`source`:

- `user-confirmed`
- `repo-evidence`
- `conversation-observed`
- `correction`

Suggested `scope` values:

- `verification`
- `security`
- `git`
- `docs`
- `reporting`
- `architecture`
- `dependencies`
- `release`

## Required Rule Quality

Each active rule must be:

- specific enough to act on
- scoped to the smallest useful area
- paired with exceptions when it weakens verification, safety, or review
- traceable to user confirmation or repository evidence
- updated with a changelog entry whenever it changes

Do not store secrets, private credentials, long transcripts, or sensitive business data in norm files.
