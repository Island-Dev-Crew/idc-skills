#!/usr/bin/env bash
# Claude Code PreToolUse guard: blocks destructive git commands before they run.
# Reads hook JSON on stdin, exits 2 (with a stderr message) to block.
set -euo pipefail

cmd="$(cat | jq -r '.tool_input.command // .command // empty' 2>/dev/null || true)"
[ -n "$cmd" ] || exit 0

# Destructive git operations agents should not perform without explicit human action.
DANGEROUS=(
  'git[[:space:]]+push'
  'git[[:space:]]+reset[[:space:]]+.*--hard'
  'git[[:space:]]+clean[[:space:]]+-[a-zA-Z]*f'
  'git[[:space:]]+branch[[:space:]]+-D'
  'git[[:space:]]+checkout[[:space:]]+\.'
  'git[[:space:]]+restore[[:space:]]+\.'
)

for pat in "${DANGEROUS[@]}"; do
  if printf '%s' "$cmd" | grep -Eq -- "$pat"; then
    echo "BLOCKED: you do not have authority to run destructive git commands (matched: $pat)." >&2
    echo "If this is intended, the human runs it." >&2
    exit 2
  fi
done

exit 0
