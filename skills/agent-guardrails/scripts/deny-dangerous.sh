#!/usr/bin/env bash
# Shared shell guard for AI coding agents. Reads hook JSON on stdin, exits 2 to block.
# Single source of truth for patterns: ~/.agents/hooks/dangerous-patterns.txt
# Seatbelt against accidents, NOT a sandbox against a malicious agent.
set -euo pipefail

PATTERNS="${AGENT_HOOKS_PATTERNS:-$HOME/.agents/hooks/dangerous-patterns.txt}"

# Read the whole hook payload.
payload="$(cat)"

# Command location differs per agent: .tool_input.command (Claude/Codex/Devin),
# .toolInput.command (Grok), .command (Cursor, when invoked with the `cursor` arg).
if [ "${1:-}" = "cursor" ]; then
  cmd="$(printf '%s' "$payload" | jq -r '.command // empty' 2>/dev/null || true)"
else
  cmd="$(printf '%s' "$payload" | jq -r '.tool_input.command // .toolInput.command // .command // empty' 2>/dev/null || true)"
fi

# No command found -> nothing to guard; let it through (fail open on parse).
[ -n "$cmd" ] || { printf '%s' "$payload"; exit 0; }

# No patterns file -> fail open, but say so on stderr (a missing denylist must be loud).
if [ ! -f "$PATTERNS" ]; then
  echo "deny-dangerous: patterns file missing at $PATTERNS (guard OPEN)" >&2
  printf '%s' "$payload"; exit 0
fi

# Match the command against every non-comment, non-blank ERE pattern.
while IFS= read -r pat; do
  [ -z "$pat" ] && continue
  case "$pat" in \#*) continue ;; esac
  if printf '%s' "$cmd" | grep -Eq -- "$pat"; then
    echo "BLOCKED by agent guardrails: command matches dangerous pattern: $pat" >&2
    exit 2
  fi
done < "$PATTERNS"

# Allowed. Echo the payload back so pass-through hooks keep working.
printf '%s' "$payload"
exit 0
