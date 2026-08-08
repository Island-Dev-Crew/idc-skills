#!/usr/bin/env bash
# duel-verdict.sh — the mechanical governor of a skill duel.
# It decides the swap in code so no tie can be narrated into a win. It enforces
# the two invariants a fair duel rests on:
#   (1) identical gauntlet — both contestants were scored over the SAME case ids;
#   (2) strict-beat, tie-to-incumbent — the challenger displaces the incumbent
#       ONLY on a strictly higher mean; a tie or a loss keeps the incumbent.
# Inputs: two TSV result files, one row per case:  <case-id>\t<score>
# Usage:  duel-verdict.sh <incumbent.tsv> <challenger.tsv>
set -euo pipefail

INC=${1:?incumbent results tsv}
CHA=${2:?challenger results tsv}
[ -f "$INC" ] || { echo "no such file: $INC" >&2; exit 2; }
[ -f "$CHA" ] || { echo "no such file: $CHA" >&2; exit 2; }

# case-id set from column 1 — the identical-gauntlet check
ids() { cut -f1 "$1" | sort; }
if ! diff <(ids "$INC") <(ids "$CHA") >/dev/null; then
  echo "UNFAIR: case-id sets differ — this is not one identical gauntlet; no verdict" >&2
  exit 3
fi

# score-axis check — every column-2 cell must be a real number in [0,1], or a
# forged/out-of-range score could flip the enforced strict-beat gate on a claim.
scores_ok() {
  awk -F'\t' '
    { c=$2
      if (c !~ /^-?[0-9]+(\.[0-9]+)?$/) { print "non-numeric score: " c > "/dev/stderr"; bad=1; exit }
      if (c+0 < 0 || c+0 > 1)          { print "out-of-range score: " c > "/dev/stderr"; bad=1; exit }
    }
    END{ exit bad }
  ' "$1"
}
for f in "$INC" "$CHA"; do
  if ! scores_ok "$f"; then
    echo "UNFAIR: $f carries a non-numeric or out-of-[0,1] score; no verdict" >&2
    exit 3
  fi
done

mean() { awk -F'\t' '{s+=$2; n++} END{ if (n==0) print "0"; else printf "%.6f", s/n }' "$1"; }
IM=$(mean "$INC")
CM=$(mean "$CHA")

# strict-beat, tie-to-incumbent — decided here, never in prose
if awk -v i="$IM" -v c="$CM" 'BEGIN{ exit !(c > i) }'; then
  echo "incumbent_mean=$IM challenger_mean=$CM verdict=SWAP"
  echo "challenger strictly beat the incumbent — displace the seat"
else
  echo "incumbent_mean=$IM challenger_mean=$CM verdict=NO-SWAP"
  echo "tie or loss — incumbent keeps the seat"
fi
