#!/usr/bin/env bash
# POSIX convenience wrapper. The Python installer owns all copy semantics and
# the signed integrity preflight; this wrapper must never become a bypass.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$ROOT/scripts/install.py" --repo-root "$ROOT" \
  install --verify-integrity "$@"
