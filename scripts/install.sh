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
exec "$PYTHON" -I -B "$LAUNCHER" --repo-root "$ROOT" --config "$CONFIG" \
  install -- --verify-integrity "$@"
