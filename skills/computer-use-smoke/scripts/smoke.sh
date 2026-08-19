#!/usr/bin/env bash
# smoke.sh — backend-agnostic behavioral smoke harness.
#
# Gates on a readiness signal (never a fixed sleep), runs a flow driver whose
# EXIT CODE IS THE VERDICT, and stamps evidence. The driver — Playwright,
# browser-use, or a computer-use harness — is passed in, so this harness stays
# backend-agnostic and only the driver swaps.
#
#   smoke.sh <ready-url> <repo-local-executable-flow-driver> [args...]
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
case "$READY_URL" in
  http://*|https://*) ;;
  *) echo "smoke: ready URL must use http(s)" >&2; exit 2 ;;
esac
authority="${READY_URL#*://}"; authority="${authority%%/*}"
case "$authority" in *@*) echo "smoke: credentials in ready URL are forbidden" >&2; exit 2 ;; esac
origin="${READY_URL%%://*}://$authority"
export SMOKE_ALLOWED_ORIGINS="${SMOKE_ALLOWED_ORIGINS:-$origin}"
case " ${SMOKE_ALLOWED_ORIGINS} " in
  *" $origin "*) ;;
  *) echo "smoke: ready origin is not in SMOKE_ALLOWED_ORIGINS: $origin" >&2; exit 2 ;;
esac

driver="${FLOW[0]}"
case "$driver" in */*) ;; *) echo "smoke: flow driver must be an explicit repo-local path" >&2; exit 2 ;; esac
[ -f "$driver" ] && [ ! -L "$driver" ] && [ -x "$driver" ] \
  || { echo "smoke: flow driver must be a real executable file: $driver" >&2; exit 2; }
driver_abs="$(cd "$(dirname "$driver")" && pwd -P)/$(basename "$driver")"
repo_abs="$(pwd -P)"
case "$driver_abs" in "$repo_abs"/*) ;; *) echo "smoke: flow driver escapes the repository: $driver_abs" >&2; exit 2 ;; esac
FLOW[0]="$driver_abs"

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
if [ "$ready" != 1 ]; then
  printf 'VERDICT=3\nSTAGE=readiness\nORIGIN=%s\n' "$origin" > "$RUN/verdict.txt"
  echo "smoke: $READY_URL never became ready; evidence -> $RUN" >&2
  exit 3
fi

# 2. Drive the flow. Its exit code is the verdict — this harness only relays it.
export SMOKE_EVIDENCE="$RUN"
rc=0
"${FLOW[@]}" > "$RUN/flow.log" 2>&1 || rc=$?

printf 'VERDICT=%s\nSTAGE=flow\nORIGIN=%s\n' "$rc" "$origin" | tee "$RUN/verdict.txt"
echo "smoke: evidence -> $RUN (verdict $rc)" >&2
exit "$rc"
