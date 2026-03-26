# Project document checklist

Use this checklist as a final pass before saving the markdown file.

## Must verify
- Git status was checked first.
- The commit-hash basis in the filename matches the chosen rule.
- The document filename follows `docs/{YYYY-MM-DD_HH-mm}_{hash}_项目文档.md`.
- If uncommitted changes existed and the user chose not to commit, the document begins with the required warning.
- `docs/` old documents were inspected before drafting.
- The document distinguishes confirmed, inferred, and uncertain information.
- Core flows and shared mechanisms were analyzed more deeply than secondary modules.
- The document contains practical modification guidance for later AI work.

## Common failure modes
- Over-describing directory names without tracing code relationships.
- Treating guesses as facts.
- Spending too much space on low-value utility folders.
- Ignoring older analysis documents in `docs/`.
- Forgetting to describe impact radius for common modifications.
- Producing only a summary instead of a durable project knowledge base.
