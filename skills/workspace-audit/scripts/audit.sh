#!/usr/bin/env bash
# Audit an ICM workspace for path-level drift between the map and the tree.
# Usage: audit.sh <workspace-dir>
# Reports BROKEN CLAIMS (mapped paths missing) and BLIND SPOTS (rooms/files not mapped).
# Heuristic: catches path drift, not semantic drift. Exit 1 iff any drift found.
set -euo pipefail

DIR="${1:?usage: audit.sh <workspace-dir>}"
[ -d "$DIR" ] || { echo "audit: no such dir: $DIR" >&2; exit 2; }

MAPFILES=()
for f in "$DIR/AGENTS.md" "$DIR/CLAUDE.md"; do [ -f "$f" ] && MAPFILES+=("$f"); done
[ "${#MAPFILES[@]}" -gt 0 ] || { echo "audit: no map (AGENTS.md / CLAUDE.md) in $DIR" >&2; exit 2; }

# Concatenate the map with URLs stripped, so a source URL is never mis-read as a path.
map_text="$(cat "${MAPFILES[@]}" | sed -E 's~https?://[^ )]+~~g')"

# ---- Path-like tokens the map references, extracted once as an exact-match index ----
ref_tokens="$(printf '%s\n' "$map_text" \
  | grep -oE '[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+/?' \
  | grep -vE '<|>|\*' | sed -E 's#/$##; s#[.,;:)]+$##' | sort -u || true)"

# ---- Space-in-path detection: a path segment with a space is outside the no-spaces
# convention this tool parses; the regex would shred it into garbage tokens. Surface it
# as a distinct advisory WARNING instead of mis-reporting it as broken/blind drift. ----
spaced_paths="$(printf '%s\n' "$map_text" \
  | grep -oE '[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+ [A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+|\.[A-Za-z0-9]+)' \
  | sed -E 's#[.,;:)]+$##' | sort -u || true)"
# The shredded fragments these spaced paths leak into the index, kept out of broken claims.
# Trimmed the same way as ref_tokens so an excluded fragment matches its trimmed token.
excluded="$(printf '%s\n' "$spaced_paths" \
  | grep -oE '[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+/?' | sed -E 's#/$##; s#[.,;:)]+$##' | sort -u || true)"
is_excluded() { [ -n "$1" ] && grep -qxF "$1" <<< "$excluded"; }
warned=()
while IFS= read -r sp; do [ -n "$sp" ] && warned+=("$sp"); done <<< "$spaced_paths"

# ---- BROKEN CLAIMS: a path-like token the map names but the tree lacks ----
broken=()
while IFS= read -r rel; do
  [ -n "$rel" ] || continue
  is_excluded "$rel" && continue
  [ -e "$DIR/$rel" ] || broken+=("$rel")
done <<< "$ref_tokens"

# ---- BLIND SPOTS: a live room/file the map never mentions ----
# Exact-token membership against ref_tokens — never a substring/regex scan of raw map
# text — so a sibling name (rooms/api vs rooms/api-gateway) can't suppress a real gap.
is_referenced() { grep -qxF "$1" <<< "$ref_tokens"; }
blind=()
# rooms/**/CONTEXT.md not referenced by the map
if [ -d "$DIR/rooms" ]; then
  while IFS= read -r ctx; do
    [ -n "$ctx" ] || continue
    rel="${ctx#"$DIR"/}"
    case "$rel" in *" "*) warned+=("$rel"); continue ;; esac
    room="$(basename "$(dirname "$ctx")")"
    if is_referenced "$rel" || is_referenced "rooms/$room"; then :; else blind+=("$rel"); fi
  done < <(find "$DIR/rooms" -name CONTEXT.md -type f 2>/dev/null | sort || true)
fi
# top-level *.md not referenced (the map files and README are not workspace content)
while IFS= read -r md; do
  [ -n "$md" ] || continue
  base="$(basename "$md")"
  case "$base" in AGENTS.md|CLAUDE.md|README.md) continue ;; esac
  printf '%s' "$map_text" | grep -qF "$base" || blind+=("$base")
done < <(find "$DIR" -maxdepth 1 -name '*.md' -type f 2>/dev/null | sort || true)

echo "== BROKEN CLAIMS (map names a path the tree lacks) =="
if [ "${#broken[@]}" -eq 0 ]; then echo "  none"; else printf '  MISSING: %s\n' "${broken[@]}"; fi
echo ""
echo "== BLIND SPOTS (a live room/file the map never mentions) =="
if [ "${#blind[@]}" -eq 0 ]; then echo "  none"; else printf '  UNMAPPED: %s\n' "${blind[@]}"; fi
echo ""

if [ "${#warned[@]}" -gt 0 ]; then
  echo "== WARNING: path contains a space, outside parser scope (skipped, judge by hand) =="
  printf '%s\n' "${warned[@]}" | sort -u | sed 's/^/  SKIPPED: /'
  echo ""
fi

total=$(( ${#broken[@]} + ${#blind[@]} ))
if [ "$total" -eq 0 ]; then
  if [ "${#warned[@]}" -gt 0 ]; then
    echo "CLEAN on parsed paths — but space-containing paths were skipped (see WARNING); judge those by hand."
  else
    echo "CLEAN — map and tree agree on paths (semantic drift is still yours to judge)."
  fi
  exit 0
else
  echo "DRIFT — ${#broken[@]} broken claim(s), ${#blind[@]} blind spot(s). Fix the map or the tree; do not silence the check."
  exit 1
fi
