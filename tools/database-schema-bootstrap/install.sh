#!/usr/bin/env sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
launcher=${CODEX_PYTHON:-python3}
exec "$launcher" -B "$script_dir/install.py" "$@"
