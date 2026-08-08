#!/usr/bin/env bash
# smoke.sh — backend-agnostic behavioral smoke harness.
#
# Gates on a readiness signal (never a fixed sleep), runs a flow driver whose
# EXIT CODE IS THE VERDICT, and stamps evidence. The driver — Playwright,
# browser-use, or a computer-use harness — is passed in, so this harness stays
# backend-agnostic and only the driver swaps.
#
#   smoke.sh <ready-url> <flow-driver> [args...]
#
# Contract for the flow driver:
#   - it asserts observable state at each checkpoint (coded assertions, not vibes)
#   - it writes evidence into $SMOKE_EVIDENCE
#   - exit 0 = every checkpoint green; non-zero = first red (name it on stderr)
set -euo pipefail

READY_URL="${1:?usage: smoke.sh <ready-url> <flow-driver> [args...]}"
shift
FLOW=("$@")
[ "${#FLOW[@]}" -gt 0 ] || { echo "smoke: no flow driver given" >&2; exit 2; }

# Per-run evidence dir must be collision-resistant: same-second and concurrent
# invocations (gauntlet-loop, parallel gates, CI matrix) must not overwrite each
# other's verdict.txt/flow.log. mktemp -d allocates a unique dir atomically.
mkdir -p build/smoke
RUN="$(mktemp -d "build/smoke/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"

# 1. Readiness gate — poll the health signal, don't sleep-and-hope. The loop
#    conditions on a real 2xx, so a slow-starting app is waited-for, not raced.
ready=0
for _ in $(seq 1 60); do
  if curl -fsS -m 5 "$READY_URL" >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[ "$ready" = 1 ] || { echo "smoke: $READY_URL never became ready" >&2; exit 3; }

# 2. Drive the flow. Its exit code is the verdict — this harness only relays it.
export SMOKE_EVIDENCE="$RUN"
rc=0
"${FLOW[@]}" > "$RUN/flow.log" 2>&1 || rc=$?

printf 'VERDICT=%s\n' "$rc" | tee "$RUN/verdict.txt"
echo "smoke: evidence -> $RUN (verdict $rc)" >&2
exit "$rc"
