#!/usr/bin/env bash
# POSIX convenience wrapper. The external freshness launcher owns release
# authorization; the Python installer owns content-bound copy semantics.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="${IDC_SKILLS_FRESHNESS_LAUNCHER:-}"
CONFIG="${IDC_SKILLS_FRESHNESS_CONFIG:-}"
PYTHON="${IDC_SKILLS_FRESHNESS_PYTHON:-}"
if [[ -z "$LAUNCHER" || -z "$CONFIG" || -z "$PYTHON" ]]; then
  echo "install refused: set IDC_SKILLS_FRESHNESS_PYTHON, IDC_SKILLS_FRESHNESS_LAUNCHER, and IDC_SKILLS_FRESHNESS_CONFIG to externally pinned absolute paths" >&2
  exit 2
fi
if (( BASH_VERSINFO[0] < 3 || (BASH_VERSINFO[0] == 3 && BASH_VERSINFO[1] < 2) )); then
  echo "install refused: Bash 3.2 or newer is required" >&2
  exit 2
fi
"$PYTHON" -I -B "$ROOT/scripts/verify_runtime_requirements.py" \
  --contract "$ROOT/runtime-requirements.json" >/dev/null
exec "$PYTHON" -I -B "$LAUNCHER" --repo-root "$ROOT" --config "$CONFIG" \
  install -- --verify-integrity "$@"
