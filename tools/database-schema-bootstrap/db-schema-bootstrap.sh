#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
runtime_root=$(CDPATH= cd -- "$script_dir/.." && pwd)
python_path="$runtime_root/.venv/bin/python"
if [ ! -x "$python_path" ]; then
    echo "The dedicated database-schema-bootstrap venv is unavailable." >&2
    exit 1
fi
exec "$python_path" -B "$script_dir/control.py" --runtime-root "$runtime_root" "$@"
