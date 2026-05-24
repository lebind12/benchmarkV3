#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${BENCHMARK_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT_DIR"

python -m app.workers.daily_sync.cli sync-configured-targets --fallback-defaults "$@"
