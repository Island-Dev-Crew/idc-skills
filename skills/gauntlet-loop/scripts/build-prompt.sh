#!/usr/bin/env bash
# Convert any task into a ready-to-paste gauntlet-loop prompt.
# Usage:  build-prompt.sh "an explorable 3D walkthrough of this apartment"
#         echo "a first-person-shooter level" | build-prompt.sh
# The three parts (task / fan-out-with-blind-critic / falsifiable bar) are emitted with
# the task filled in and BRIEF + BAR + CAPS left as slots you MUST fill — the loop
# refuses to start cold, so a blank brief or bar is a deliberately visible TODO.
set -euo pipefail

task="${*:-}"
if [ -z "$task" ] && [ ! -t 0 ]; then task="$(cat)"; fi
task="$(printf '%s' "$task" | tr -s '[:space:]' ' ' | sed -E 's/^ +| +$//g')"
[ -n "$task" ] || { echo "usage: build-prompt.sh \"<one-line task>\"   (or pipe the task on stdin)" >&2; exit 2; }

cat <<PROMPT
# Gauntlet-loop prompt  (fill BRIEF and BAR before running — do not start cold)

TASK
Build: ${task}

BRIEF  (the loop optimizes toward whatever you give it — anchor it, or it polishes the wrong thing)
Ground the build in: <a reference peg / design system / v1 MVP to sharpen>.  # REQUIRED — replace me

BUILD METHOD
Break the task into the smallest independent pieces. Fan out one builder sub-agent per piece.
Shadow every builder with a SEPARATE blind critic that scores the artifact itself (never the
builder's self-report) against the BAR and sends it back if it falls short. Isolate parallel
builders so they cannot overwrite each other. Loop each piece until its critic passes it.

BAR TO HIT  (must be able to FAIL — a bar no critic can fail you on is decoration)
Do not stop until every critic passes on captured evidence, measured against:
<the falsifiable standard — e.g. "match these N reference photos; each critic marks all N >= pass",
 a metric to clear, or a checklist every critic must satisfy>.  # REQUIRED — replace me

CAPS  (loops burn hours and tokens — bound them)
Round cap: <N rounds per piece>.  Token/time budget: <cap>.  Stop and report at the cap even if unmet.
PROMPT
