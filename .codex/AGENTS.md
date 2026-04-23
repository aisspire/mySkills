# Global working rules

## Output discipline

- Keep execution chatter short.
- Surface errors, failed commands, and blocking environment issues clearly.
- Do not hide stack traces, compiler errors, test failures, or import/path errors.
- Summarize routine retries briefly, but include the final failing command and the decisive error output.
- When blocked by a local environment issue, report:
  1. failing command
  2. root cause
  3. exact fix
  4. exact final command to run

## Encoding

- On Windows, treat project text files as UTF-8 unless the repository instructions explicitly say otherwise.

## Command selection

- Prefer repository entrypoints over ad-hoc commands.
- Never switch Python interpreters on your own.
- Never use the `py` launcher unless the repository instructions explicitly require it.
- Do not probe multiple alternative toolchains unless the first expected path fails.
- After one failed environment probe, report the blocker instead of continuing broad exploration.
