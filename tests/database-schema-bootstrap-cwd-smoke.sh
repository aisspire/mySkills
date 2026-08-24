#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root=${1:-${CODEX_HOME:-$HOME/.codex}/database-schema-bootstrap}
python_path="$runtime_root/.venv/bin/python"
exec "$python_path" -B "$script_dir/database_schema_bootstrap_cwd_smoke.py" --runtime-root "$runtime_root"
