#!/usr/bin/env bash
set -euo pipefail
# Historical state reader. New work uses harness-run.sh.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  exec "$REPO_ROOT/.venv/bin/python" "$SCRIPT_DIR/work-flow.py" "$@"
fi
exec python3 "$SCRIPT_DIR/work-flow.py" "$@"
