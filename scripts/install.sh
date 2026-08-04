#!/usr/bin/env bash
# Distribute every island across the four fleet skill folders and validate frontmatter.
# Canonical: ~/.agents/skills/  (Claude + Pi are symlinks → auto-covered)
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
for skill in "$SKILLS_DIR"/*/; do
  name="$(basename "$skill")"
  rsync -a --delete "$skill" "$AGENTS/$name/"
  rsync -a --delete "$skill" "$HERMES/$name/"
  echo "  installed $name"
done

echo "== verify byte counts across the fleet (Claude/Pi symlinks must match) =="
for name in "$SKILLS_DIR"/*/; do
  n="$(basename "$name")"
  for p in "$AGENTS" "$HOME/.claude/skills" "$HOME/.pi/agent/skills" "$HERMES"; do
    if [ -f "$p/$n/SKILL.md" ]; then
      printf "  %-22s %-26s %s bytes\n" "$n" "$p" "$(wc -c < "$p/$n/SKILL.md")"
    fi
  done
done

echo "== done. Hermes snapshots skills at session start — restart Hermes to see new ones. =="
