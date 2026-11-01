#!/usr/bin/env bash
# Check the active development slice, then the unchanged historical project.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
# Sandboxes mount the default caches read-only; fall back under TMPDIR so the gate runs anywhere.
for pair in "UV_CACHE_DIR:${HOME}/.cache/uv" "XDG_DATA_HOME:${HOME}/.local/share"; do
  var=${pair%%:*}; dir=${pair#*:}
  if [ -z "${!var:-}" ] && ! { mkdir -p "$dir" 2>/dev/null && [ -w "$dir" ]; }; then
    export "$var=${TMPDIR:-/tmp}/gc-bench-${var,,}"
  fi
done
uv run --locked ruff check task.py grader.py report.py review_packet.py run.py tests
uv run --locked pytest tests -q
python3 -m unittest discover -s evals/tests
if [ -d private/heldout ]; then python3 private/scripts/check_heldout_disjoint.py; fi
cd _archive/5.8.0
exec uv run --locked --extra dev bash ./scripts/check.sh
