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

## PowerShell

- This workspace is opened from WSL/bash. When running PowerShell scripts or tests, use Windows PowerShell via:

  `powershell.exe -NoProfile -ExecutionPolicy Bypass`

- Do not use bare `powershell`; it is not available on PATH in this shell.

- Quote Windows-style relative paths when passing them through bash. For example:

  `powershell.exe -NoProfile -ExecutionPolicy Bypass -File '.\tests\profile-skill-search.tests.ps1'`

- If `powershell.exe` fails with a WSL interop or sandbox error, request approval to run it outside the sandbox instead of trying unrelated toolchains.

- Avoid nested unescaped double quotes in `powershell.exe -Command "..."`.

- For `rg` regex patterns containing `|`, always use single quotes:
   `rg -n 'foo|bar|baz' 'path'`

- Prefer direct commands over wrapping PowerShell inside PowerShell.
