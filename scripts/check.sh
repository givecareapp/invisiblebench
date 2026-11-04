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
if [ -d ../invisiblebench-private/heldout ]; then
  python3 ../invisiblebench-private/scripts/check_heldout_disjoint.py
fi
# The historical source is frozen. Run the exact committed snapshot from a
# neutral temporary checkout so its path-sensitive legacy inventory code does
# not mistake this repository's new `safety/` parent for a benchmark category.
archive_tmp=$(mktemp -d /tmp/givecare-bench-archive.XXXXXX)
trap 'rm -rf "$archive_tmp"' EXIT
git archive HEAD:_archive/5.8.0 | tar -x -C "$archive_tmp"
git -C "$archive_tmp" init -q
git -C "$archive_tmp" add -A
git -C "$archive_tmp" -c user.name='GiveCare archive check' \
  -c user.email='archive-check@givecareapp.com' commit -qm 'frozen archive check'
cd "$archive_tmp"
uv run --locked --extra dev bash ./scripts/check.sh
