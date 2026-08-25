#!/usr/bin/env bash
# Durable strict entrypoint for Forge-installed hooks. The underlying classifier deliberately
# remains advisory when invoked directly; this wrapper makes the authority-sensitive choice on
# every hook invocation instead of relying on an installer's short-lived process environment.
set -uo pipefail

GUARD_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD_CLASSIFIER="$GUARD_SCRIPT_DIR/block-dangerous-git.sh"
if [ ! -x "$GUARD_CLASSIFIER" ]; then
  echo "block-dangerous-git: strict entrypoint cannot execute classifier (strict guard BLOCK)" >&2
  exit 2
fi
export IDC_GUARD_STRICT=1
exec "$GUARD_CLASSIFIER" "$@"
