#!/usr/bin/env bash
# delta.sh — before/after AI-likeness evidence for a de-slop pass.
# Scores BEFORE and AFTER with the same deterministic scorer and prints the drop.
# A pass is proven only when AFTER < BEFORE — the delta is the evidence, not a claim.
#
# Usage: ./scripts/delta.sh before.md after.md
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"

if [[ $# -ne 2 ]]; then
  echo "usage: delta.sh <before-file> <after-file>" >&2
  exit 2
fi

# Minimum fraction of BEFORE's word count that AFTER must retain. A rewrite that
# collapses to (near) nothing scores ~0 and would otherwise launder a PASS out of
# a non-rewrite — the floor makes that impossible.
MIN_RETAIN_PCT=50

# Emit "score wordCount" for a file using the same scorer the gate trusts.
metrics() {
  node -e '
    const { analyze } = require(process.argv[1]);
    const r = analyze(require("fs").readFileSync(process.argv[2], "utf8"));
    process.stdout.write(r.score + " " + r.wordCount + "\n");
  ' "$DIR/score.js" "$1"
}

read -r before before_wc < <(metrics "$1")
read -r after after_wc < <(metrics "$2")
delta=$(( before - after ))

echo "before: $before ($before_wc words)"
echo "after:  $after ($after_wc words)"
echo "delta:  $delta"

# Degenerate AFTER: empty, whitespace-only, or truncated to nothing is not a rewrite.
if [[ "$after_wc" -eq 0 ]]; then
  echo "verdict: FAIL (AFTER is empty/degenerate — not a rewrite, no evidence)" >&2
  exit 2
fi

# Floor: AFTER must retain at least MIN_RETAIN_PCT% of BEFORE's words, so a
# score drop caused by deletion rather than de-slopping cannot report PASS.
if (( after_wc * 100 < before_wc * MIN_RETAIN_PCT )); then
  echo "verdict: FAIL (AFTER kept $after_wc/$before_wc words, under ${MIN_RETAIN_PCT}% floor — collapse, not a rewrite)" >&2
  exit 2
fi

if [[ "$after" -lt "$before" ]]; then
  echo "verdict: PASS (score dropped $delta)"
  exit 0
else
  echo "verdict: FAIL (no drop — de-slop did not reduce measured tells)"
  exit 1
fi
