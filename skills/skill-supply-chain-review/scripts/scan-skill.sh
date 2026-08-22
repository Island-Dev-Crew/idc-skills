#!/usr/bin/env bash
# Deterministic advisory intake scan. Candidate bytes are never executed.
set -euo pipefail

DIR="${1:-}"
[ -n "$DIR" ] && [ -d "$DIR" ] || {
  printf 'usage: scan-skill.sh <path-to-candidate-skill-dir>\n' >&2
  exit 2
}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3 2>/dev/null || true)"
[ -n "$PYTHON" ] || { printf 'scan refused: python3 is required\n' >&2; exit 2; }
exec "$PYTHON" -I -B "$SCRIPT_DIR/scan-skill.py" "$DIR"
