---
name: database-schema-bootstrap
description: Use when a task involves existing database tables, SQL generation, schema understanding, migrations, joins, data debugging, or CRUD work, and accurate progress depends on discovering the real table structure rather than relying on a manual column description.
---

# Database Schema Bootstrap

## Overview

Use this skill to reduce back-and-forth when a request depends on an existing database schema.

Core principle: load one shared config file, resolve a usable Python interpreter, inspect the real table definition through a Python script, then write SQL or implementation advice from discovered facts instead of guessed columns.

## When to Use

- the user wants SQL for existing tables
- the task depends on column names, types, defaults, keys, or indexes
- the request involves joins, migrations, CRUD code, or debugging schema mismatches
- the user knows table names but does not want to handwrite the full structure
- the project may already contain reusable database connection settings

## When NOT to Use

- the schema is brand new and no real database exists yet
- the task is purely conceptual database design
- the user already supplied authoritative DDL and does not need introspection
- the task is unrelated to databases

## Core Rule

Do not guess table structures.

Do not perform write operations during schema discovery. The introspection phase is read-only unless the user explicitly asks for a mutation later.

Before writing SQL, migration steps, data fixes, or root-cause analysis for an existing database:

1. Check whether this skill contains a usable database configuration.
2. If the configuration is still a placeholder or incomplete, ask the user for the connection details and target tables.
3. If the configuration is usable, connect first and inspect the target table definition.
4. Base the rest of the work on the discovered schema, not on assumptions.

## Quick Reference

- Shared config file: [references/database.env.example](references/database.env.example)
- Config field notes: [references/config-template.md](references/config-template.md)
- Python script: [scripts/inspect_schema.py](scripts/inspect_schema.py)
- Python command behavior: use configured `PYTHON_BIN`; if blank, auto-discover a local interpreter
- Missing config: ask only for the missing database fields
- Broken Python environment: stop and ask the user to maintain the environment, then give concrete setup commands
- Discovery priority: Python script first, direct SQL fallback second
- Safety boundary: discovery is read-only

## Required Inputs

Check [references/database.env.example](references/database.env.example) and [references/config-template.md](references/config-template.md) before asking the user anything.

Treat the configuration as missing when any critical field is blank or still uses placeholders such as:

- `__PYTHON_BIN__`
- `__DB_TYPE__`
- `__DB_HOST__`
- `__DB_PORT__`
- `__DB_NAME__`
- `__DB_USER__`
- `__DB_PASSWORD__`
- `__DB_SCHEMA__`
- `__TARGET_TABLES__`

Treat `PYTHON_BIN` differently from database settings:

- if `PYTHON_BIN` is blank or placeholder, try to find Python automatically
- if Python is found but the environment lacks required database drivers, ask the user to maintain that environment
- do not ask the user for a Python path until auto-discovery has failed

When database configuration is missing, ask only for the minimum needed to proceed:

- database type
- connection address or DSN
- database name
- schema name if applicable
- target table name or names
- read-only credential preference if the user has one

## Operating Procedure

### 1. Classify the request

Use this workflow when the task depends on an existing database, for example:

- writing or correcting SQL
- explaining data relationships
- preparing migrations
- debugging bad joins, missing columns, or type mismatches
- generating CRUD code from existing tables
- auditing or validating schema assumptions

If the user is designing a brand-new schema from scratch and no live database exists yet, skip the connection step and gather requirements normally.

### 2. Check the skill configuration

Open [references/database.env.example](references/database.env.example) first, then read [references/config-template.md](references/config-template.md).

If the database fields still contain placeholders, tell the user that the skill is not configured for this project yet and ask only for the missing connection details.

If the file contains project-specific values, use them as the default connection source for this task.

Do not assume the configured connection is safe for write operations. During schema discovery, use the least-privilege or read-only path whenever possible.

### 3. Resolve Python before introspection

Use `PYTHON_BIN` from the shared config when it contains a real value.

If `PYTHON_BIN` is blank or still a placeholder, try a bounded local discovery order:

1. `.venv/Scripts/python.exe` or `.venv/bin/python`
2. `venv/Scripts/python.exe` or `venv/bin/python`
3. `python`
4. `py -3` on Windows

If auto-discovery finds a working interpreter, continue with that interpreter and mention that the configured Python path was missing.

If no usable interpreter is found, ask the user to provide or maintain the Python runtime path.

If Python exists but the environment is unsuitable, for example because a required driver such as `psycopg`, `psycopg2`, `pymysql`, or `mysql-connector-python` is missing, stop and ask the user to maintain the environment. Give concrete setup guidance such as:

- "Use the project virtualenv and install the database driver there."
- "`python -m pip install psycopg[binary]` for PostgreSQL."
- "`python -m pip install pymysql` or `python -m pip install mysql-connector-python` for MySQL."
- "If the project pins dependencies, update its lockfile or environment spec instead of installing ad hoc globally."

### 4. Prefer Python-based schema introspection over user-written descriptions

Once connection details are available, inspect the target table definitions before continuing.

Preferred order:

1. Run [scripts/inspect_schema.py](scripts/inspect_schema.py) with the shared config file and target tables.
2. Get the actual `CREATE TABLE` statement if the engine exposes it directly.
3. If `CREATE TABLE` is not directly available, gather equivalent metadata for columns, defaults, indexes, primary keys, foreign keys, and constraints.
4. Summarize the discovered schema back to the user only when it helps the next step.

Do not ask the user to manually enumerate every column unless:

- database access is unavailable
- Python auto-discovery failed and no interpreter was provided
- credentials fail
- the Python environment is missing required drivers and the user has not fixed it yet
- permissions block introspection
- the target is not a real database yet

During this step, avoid `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `DROP`, or any other mutating command. Schema discovery is not a license to change data or structure.

### 5. Continue with the real schema

After introspection:

- use the discovered column names and types in all SQL
- call out missing indexes, nullability, defaults, and constraints when relevant
- mention any uncertainty that remains because introspection was partial

## Output Discipline

When you had to ask the user for connection details, keep the request short and concrete.

When `PYTHON_BIN` was missing but auto-discovery worked, say that explicitly.

When the Python environment is unsuitable, be direct that the user must maintain it, then give a concrete recovery path instead of hand-waving.

When you were able to inspect the schema, prefer language like:

- "I used the configured schema-introspection script first."
- "I inspected the table definition first."
- "The schema shows these columns and constraints."
- "The SQL below is based on the discovered table structure."

This makes it clear that the answer comes from the database shape, not from guesswork.

## Fallback Rules

If connection details are unavailable or access fails:

1. Tell the user what exact information is still missing.
2. Ask for either a usable connection string or the output of the table DDL.
3. If the user cannot provide access, ask for the minimum manual substitute:
   - column names and types
   - primary key
   - indexes
   - foreign keys

Do not pretend the schema is known when it is not.

If Python runtime resolution fails:

1. Say whether `PYTHON_BIN` was missing, invalid, or auto-discovery failed.
2. Ask the user to provide a valid interpreter path or to repair the project environment.
3. Give a concrete suggestion:
   - "Activate the project virtualenv and re-run the script with that interpreter."
   - "Install the required driver into the interpreter you want this skill to use."
   - "Update `PYTHON_BIN` in the shared config file once the environment is ready."

## Common Mistakes

- treating a placeholder-filled shared config file as a valid runtime configuration
- asking the user for every column before attempting introspection
- asking for a Python path before trying bounded auto-discovery
- continuing after the script reports missing drivers or an unsuitable environment
- writing SQL against guessed column names or guessed foreign keys
- using a high-privilege connection for simple schema discovery
- mixing schema discovery with data mutation in the same step
- describing the discovered schema as certain when introspection returned only partial metadata

## Verification Status

This version has been statically improved for clarity, discoverability, and safer behavior boundaries.

It has not yet been proven through the full `writing-skills` RED -> GREEN -> REFACTOR loop with recorded baseline failure evidence and pressure-scenario validation.

## Introspection Reference

Use [references/schema-introspection.md](references/schema-introspection.md) for engine-specific ways to obtain `CREATE TABLE` statements or equivalent metadata.
