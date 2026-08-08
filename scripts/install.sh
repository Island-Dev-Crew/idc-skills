#!/usr/bin/env bash
# Distribute every island across the four fleet skill folders and validate frontmatter.
# Canonical: ~/.agents/skills/  (Claude + Pi are symlinks → auto-covered when symlinked,
#   or independent copies → distributed to directly; the script detects which).
# Independent copy: ~/.hermes/skills/
# See skills/idc-skill-authoring/SKILL.md §8 for the layout and traps.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SKILLS_DIR="$ROOT/skills"
AGENTS="$HOME/.agents/skills"
HERMES="$HOME/.hermes/skills"

echo "== validate frontmatter =="
fail=0
for skill in "$SKILLS_DIR"/*/SKILL.md; do
  folder="$(basename "$(dirname "$skill")")"
  name="$(awk -F': *' '/^name:/{print $2; exit}' "$skill" | tr -d '[:space:]')"
  if [ "$name" != "$folder" ]; then
    echo "  FAIL $folder: frontmatter name '$name' != folder"; fail=1
  fi
done
[ "$fail" -eq 0 ] && echo "  ok — every name matches its folder" || { echo "aborting: fix frontmatter first"; exit 1; }

echo "== distribute =="
mkdir -p "$AGENTS" "$HERMES"
canonical_real="$(cd "$AGENTS" && pwd -P)"
# Canonical + Hermes always get written. Claude/Pi are auto-covered ONLY when they are
# symlinks resolving into the canonical tree; when they are independent directories
# (a real setup on some machines) they must be distributed to directly, or they go stale.
targets=("$AGENTS" "$HERMES")
for s in "$HOME/.claude/skills" "$HOME/.pi/agent/skills"; do
  [ -e "$s" ] || continue
  if [ "$(cd "$s" && pwd -P)" = "$canonical_real" ]; then
    echo "  $s → symlinked to canonical, auto-covered"
  else
    targets+=("$s"); echo "  $s → independent copy, distributing directly"
  fi
done
for skill in "$SKILLS_DIR"/*/; do
  name="$(basename "$skill")"
  for t in "${targets[@]}"; do rsync -a --delete "$skill" "$t/$name/"; done
  echo "  installed $name"
done

echo "== verify byte counts across the fleet (every seat must match, symlinked or copied) =="
for name in "$SKILLS_DIR"/*/; do
  n="$(basename "$name")"
  for p in "$AGENTS" "$HOME/.claude/skills" "$HOME/.pi/agent/skills" "$HERMES"; do
    if [ -f "$p/$n/SKILL.md" ]; then
      printf "  %-22s %-26s %s bytes\n" "$n" "$p" "$(wc -c < "$p/$n/SKILL.md")"
    fi
  done
done

echo "== done. Hermes snapshots skills at session start — restart Hermes to see new ones. =="
