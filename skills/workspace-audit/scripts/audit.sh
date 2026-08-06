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

# ---- BROKEN CLAIMS: a path-like token the map names but the tree lacks ----
broken=()
while IFS= read -r p; do
  [ -n "$p" ] || continue
  rel="${p%/}"
  [ -e "$DIR/$rel" ] || broken+=("$rel")
done < <(printf '%s\n' "$map_text" \
  | grep -oE '[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+/?' \
  | grep -vE '<|>|\*' | sort -u || true)

# ---- BLIND SPOTS: a live room/file the map never mentions ----
blind=()
# rooms/**/CONTEXT.md not referenced by the map
if [ -d "$DIR/rooms" ]; then
  while IFS= read -r ctx; do
    [ -n "$ctx" ] || continue
    rel="${ctx#"$DIR"/}"; room="$(basename "$(dirname "$ctx")")"
    printf '%s' "$map_text" | grep -qE "$rel|rooms/$room" || blind+=("$rel")
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

total=$(( ${#broken[@]} + ${#blind[@]} ))
if [ "$total" -eq 0 ]; then
  echo "CLEAN — map and tree agree on paths (semantic drift is still yours to judge)."
  exit 0
else
  echo "DRIFT — ${#broken[@]} broken claim(s), ${#blind[@]} blind spot(s). Fix the map or the tree; do not silence the check."
  exit 1
fi
