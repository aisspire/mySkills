# Shared Config Notes

Use [database.env.example](database.env.example) as the single shared config file for this skill.

Fill the copied config file with project-specific values before reusing the skill in a repository.

If any database field is still a placeholder, treat the skill as not configured and ask the user only for the missing details.

If `PYTHON_BIN` is blank or placeholder, do not block immediately. First try bounded local discovery.

## Notes

- `PYTHON_BIN` is optional. When blank, try a local interpreter in `.venv`, `venv`, `python`, or `py -3`
- `DB_TYPE` examples: `mysql`, `postgres`, `sqlite`
- `DB_SCHEMA` is usually needed for PostgreSQL and optional for MySQL
- `DB_DSN` can be used instead of separate host, port, and credential fields when a project stores a full connection string
- `TARGET_TABLES` can be a comma-separated list such as `users,orders,order_items`
- Prefer least-privilege or read-only credentials when schema inspection is enough
- If Python exists but required drivers are missing, ask the user to maintain the environment and provide exact package-install suggestions
