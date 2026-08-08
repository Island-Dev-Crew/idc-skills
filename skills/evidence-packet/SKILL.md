---
name: evidence-packet
description: Assemble a byte-verifiable evidence packet for a change — the diff, the verification-ladder commands, and their captured outputs — so a reviewer recomputes every claim instead of trusting the author. Use when preparing work for review or merge, when the user mentions "evidence packet", "evidence bundle", "prove this change", or wants acceptance to rest on evidence the author cannot fake. Differentiator - IDC-native; this is the Contributor-Road artifact that lets a weak author and a frontier author be exactly as mergeable when both can run the ladder.
---

# Evidence Packet — the artifact the author cannot fake

An IDC-native island, the **Contributor Road** made portable. The thesis it serves: *acceptance is a decision made on evidence the author cannot fake.* When evidence is machine-checkable, acceptance stops needing either a genius author or an exhausted human reviewer — a weak model that can run the ladder is exactly as mergeable as a frontier one, because the gates decide mechanically on the packet, not on who wrote it.

The packet is the contributor's deliverable: **produce a diff → run the verification ladder → emit the packet → the gates decide.** Slop dies at the gate before a human reads it.

## What a packet contains

```
evidence/<change-slug>/
  head.txt         # the exact SHA the packet attests
  diff.patch       # git diff <base>...HEAD — what changed
  ladder.md        # each verification command + why it proves what it proves
  out/             # captured stdout/exit-code of every ladder command
  packet.sha256    # sha256 of everything above — the packet's own fingerprint
```

Every claim in `ladder.md` points at a file in `out/` a reviewer can recompute. A claim with no captured output is not evidence — it is a sentence.

## The verification ladder

The ladder is the ordered set of checks that, run green, prove the change. Each rung is **a command that could have failed** — a check that can't go red proves nothing (see [`diagnose`](../diagnose/SKILL.md) and the band caps in [`archipelago`](../archipelago/SKILL.md)). Build it from the change:

```bash
set -euo pipefail
# set these three for your change (real values, not placeholders):
SLUG="my-change"             # names the packet dir: evidence/<slug>/
BASE="main"                  # the ref you branched from
# shallow/single-branch checkouts (typical CI, fork PRs) don't have BASE — fetch it first:
# git fetch origin "$BASE:$BASE"  (or git fetch --unshallow)
git rev-parse --verify "$BASE" >/dev/null || { echo "BASE '$BASE' not present — fetch it: git fetch origin $BASE:$BASE (or git fetch --unshallow)"; exit 1; }
HEAD=$(git rev-parse HEAD)   # the exact head this packet attests
mkdir -p "evidence/$SLUG/out"
printf '%s\n' "$HEAD" > "evidence/$SLUG/head.txt"
git diff "$BASE"...HEAD > "evidence/$SLUG/diff.patch"

# each rung: run it, capture stdout AND exit code, so a reviewer sees pass/fail.
# run from repo root and avoid absolute paths/timestamps in the output — a reviewer's
# fresh clone lives at a different path, and the recompute contract below only
# tolerates divergence that's purely machine-local, not behavioral.
run_rung() {                       # run_rung <name> <command...>
  local name="$1"; shift
  local rc=0
  # a RED rung is evidence, not fatal: capture its non-zero exit without letting
  # the ladder's `set -e` abort the loop, so later rungs still run and the packet
  # still gets stamped. (`|| rc=$?` is a condition context, so errexit won't fire.)
  { "$@"; } > "evidence/$SLUG/out/$name.txt" 2>&1 || rc=$?
  printf 'EXIT=%s\n' "$rc" >> "evidence/$SLUG/out/$name.txt"
  echo "  captured $name -> out/$name.txt (exit $rc)"
}
# EXAMPLE — substitute your stack's real typecheck/test/lint commands below.
# A rung that fails because the tool is absent (ENOENT, no manifest) is noise,
# not evidence: fix or remove it before stamping. A red rung only counts if the
# command itself ran.
run_rung typecheck  npm run typecheck
run_rung tests      npm test
run_rung lint       npm run lint
# add rungs specific to the change: a repro that now passes, an operation-count
# baseline (not wall-clock — see diagnose), a byte-level scan, a screenshot.

# stamp the whole packet — sort the listing so the fingerprint is reproducible
# across machines (find's raw order is filesystem-dependent, so an unsorted roll-up
# hashes the same bytes to different values on a fresh clone).
( cd "evidence/$SLUG" && find . -type f ! -name packet.sha256 | LC_ALL=C sort \
    | xargs shasum -a 256 | shasum -a 256 | cut -d' ' -f1 > packet.sha256 )
echo "packet sha256: $(cat evidence/$SLUG/packet.sha256)"
```

## The recompute contract

The packet's value is that a reviewer, trusting none of it, can recompute it:

1. Check out `head.txt`'s SHA from a **fresh clone** (never a worktree — worktrees share `.git` state and can false-green; see [`worktree-fleet`](../worktree-fleet/SKILL.md)).
2. Re-run every command in `ladder.md`.
3. Compare: exit codes must match exactly, and output must match after the normalization filter recorded in `ladder.md` (e.g. strip the clone-root path prefix, run every command from repo root, never capture timestamps). Divergence after normalization → the packet is void, exactly like a verdict whose head moved. Divergence only in machine-local paths → it isn't.

This is what makes author strength irrelevant: the reviewer never grades the author, only recomputes the packet.

The packet's rules are **advisory inside this skill** — nothing here blocks a fabricated rung or a missing `out/` file; the enforcement lives downstream, where [`cross-family-review`](../cross-family-review/SKILL.md) recomputes the packet from a fresh clone and voids it on any divergence. This island assembles the evidence; the gate decides. State that boundary rather than implying the packet self-enforces.

## Completion

**Done when** `head.txt` names the reviewed SHA, every rung in `ladder.md` has a captured `out/` file showing its command and exit code, at least one rung demonstrably discriminates on this change — red against `BASE`'s content, green against `HEAD`'s, both runs captured (e.g. `out/discriminator.base.txt` and `out/discriminator.head.txt`) — and `packet.sha256` stamps the bundle. For a doc-only or trivial change where no ladder rung discriminates naturally, see [`diagnose`](../diagnose/SKILL.md) for constructing one. Hand the packet to [`cross-family-review`](../cross-family-review/SKILL.md); survivors become [`finding-register`](../finding-register/SKILL.md) entries, and the whole thing ships via [`transport-complete`](../transport-complete/SKILL.md).

**No authority without evidence. A claim with no captured output is a sentence, not evidence.**
