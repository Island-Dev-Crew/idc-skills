#!/usr/bin/env bash
# Scaffold an ICM workspace skeleton: root map + one room per name + inbox/evidence.
# Usage: scaffold.sh <workspace-dir> "room1 room2 room3"
# The deterministic skeleton only — the agent fills in routing/naming/process judgment.
set -euo pipefail

DIR="${1:?usage: scaffold.sh <workspace-dir> \"room1 room2 ...\"}"
ROOMS="${2:?usage: scaffold.sh <workspace-dir> \"room1 room2 ...\"}"
NAME="$(basename "$DIR")"

# Room names must be a single flat [A-Za-z0-9_-] segment: no slashes, dots, or
# leading dash (blocks path traversal) and no collision with the reserved
# top-level dirs this script also creates.
for r in $ROOMS; do
  if [[ ! "$r" =~ ^[A-Za-z0-9_][A-Za-z0-9_-]*$ ]]; then
    echo "error: invalid room name '$r' — must start with [A-Za-z0-9_] then [A-Za-z0-9_-]* (no '/', '.', leading '-', or spaces)" >&2
    exit 1
  fi
  case "$r" in
    inbox|evidence|rooms)
      echo "error: '$r' is a reserved top-level name and cannot be used as a room name" >&2
      exit 1
      ;;
  esac
done

mkdir -p "$DIR/rooms" "$DIR/inbox" "$DIR/evidence"

# CLAUDE.md — redirect so every seat routes through one map
cat > "$DIR/CLAUDE.md" <<EOF
Read AGENTS.md in this folder and follow it. (This project routes every seat through one map.)
EOF

# AGENTS.md — the map stub (fill in the routing table + naming + enforcement)
{
  echo "# $NAME — the map"
  echo
  echo "## Start here"
  echo "You are in $NAME. Read this map, find your task in the routing table, read ONLY"
  echo "what it names, then act. Do not read a room you were not routed to."
  echo
  echo "## Floor plan"
  for r in $ROOMS; do echo "rooms/$r/   — <one line: what work happens here>"; done
  echo "inbox/      — raw capture waiting to be distilled"
  echo "evidence/   — evidence-packets and verdicts (do not edit by hand)"
  echo
  echo "## Naming conventions"
  echo "- <declare the file-naming convention per room, so the next session finds files without a database>"
  echo
  echo "## Routing"
  echo "| When the task is…    | Read                       | Skip | Skills |"
  echo "|----------------------|----------------------------|------|--------|"
  for r in $ROOMS; do echo "| <task for $r>        | rooms/$r/CONTEXT.md         | ...  | ...    |"; done
  echo "| anything NOT listed  | return to this map         |      |        |"
  echo
  echo "## Enforcement"
  echo "Advisory: this map has no hook — an agent honors the routing by reading it. State"
  echo "any enforced boundary (e.g. a deep-modules lint over rooms/) explicitly; never imply"
  echo "the routing is mechanically enforced when it is not."
} > "$DIR/AGENTS.md"

# One CONTEXT.md per room
for r in $ROOMS; do
  mkdir -p "$DIR/rooms/$r"
  {
    echo "# Room: $r"
    echo "Purpose: <one line — what work happens here>."
    echo "Load: <files worth reading here, and when>."
    echo "Skip: <what NOT to read from here>."
    echo "Process: <the ordered steps for this room's work>."
    echo "Naming: <the convention for files this room produces>."
    echo
    echo "For anything not in this room, return to the root map (../../AGENTS.md)."
  } > "$DIR/rooms/$r/CONTEXT.md"
done

echo "scaffolded ICM workspace at: $DIR"
echo "  map:    $DIR/AGENTS.md   (+ CLAUDE.md redirect)"
echo "  rooms:  $(for r in $ROOMS; do printf '%s ' "$r"; done)"
echo "  next:   fill the routing table + naming, then prove a fresh agent routes through it"
