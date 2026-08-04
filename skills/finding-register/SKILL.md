---
name: finding-register
description: The IDC discipline for a durable register of findings (bugs, defects, review verdicts, doctrine) — each enumerated at an exact SHA, provenance-marked, and given a collision-free id swept before allocation. Use when tracking findings across sessions and machines, allocating a finding id (U-series or similar), reconciling counts, or when the user mentions "finding register", "the register", "U-series", or "allocate a finding id". Differentiator - IDC-only; enumeration is at-a-SHA not a running count, and an id is swept for collisions before it is issued.
---

# Finding Register — enumeration at a SHA

An IDC-only island. It is the memory that lets findings survive sessions and machines without drifting. The whole discipline is three rules that a naive "increment a counter" register violates and this one does not.

## The three rules

1. **Enumerate at a SHA, never a running count.** A finding is not "number 47." It is "the finding observable at `<SHA>` by `<command>`." Counts drift the moment two machines allocate in parallel or a session loses its place; a SHA-anchored enumeration is recomputable by anyone, forever. When asked "how many findings," answer by enumerating the register at a stated head — not by trusting a stored total.
2. **Mark provenance, both directions.** Every entry names the seat that raised it (`OpenAI Codex`, `Claude Fable 5`, `Jon Isaac`) and the seat that confirmed it. When provenance is wrong it is corrected against *either* seat — the register has been corrected against the chat seat and against the reviewer, on the record. Provenance is a claim the register defends, not a courtesy.
3. **Sweep for id collisions before you allocate.** Before issuing the next id, scan every existing id across the whole register — including entries created on other machines/lanes this cycle — and allocate strictly above the true maximum. Parallel allocation without a sweep is how duplicate ids were minted; the sweep is the cure.

## Entry shape

```
U-<n>  <one-line title>
  raised-by:   <seat>            // who found it
  confirmed-by:<seat | pending>  // who verified it (a different seat where it matters)
  head:        <SHA>             // the head at which it is observable
  command:     <the exact check that demonstrates it — one that can go red>
  status:      open | fixed | fenced | superseded
  disposition: <verdict + reason>
```

`U-` is IDC's series letter; keep whatever prefix the project already uses. What matters is that the id is unique across the whole fleet and the entry is recomputable from `head` + `command`.

## Allocating the next id

```bash
# 1. fetch the true state from every machine's shared record first
git fetch origin && git pull --ff-only origin main

# 2. SWEEP: the real maximum across the ENTIRE register, not the last one you remember
MAX=$(grep -oE '^U-[0-9]+' ops/register/*.md | grep -oE '[0-9]+' | sort -n | tail -1)
NEXT=$((MAX + 1))
echo "next id: U-$NEXT"     # allocate strictly above the swept maximum
```

Never trust a remembered "last id" — that memory is the drift. The sweep is cheap and the collision it prevents is expensive.

**Done when** the new id is strictly greater than every id present in the freshly-fetched register, and the entry carries a `head` and a `command` a stranger could run.

## Status transitions

- **open → fixed** — the `command` now goes green at a stated head; record that head.
- **open → fenced** — the finding is real but deliberately not acted on (e.g. a boundary ruling like "worktrees forbidden for evidence"). Fencing is a decision, recorded with its reason, not a silent drop.
- **any → superseded** — a later finding replaces this one. **Supersede and preserve**: never delete the old entry; mark it superseded and point to its replacement. The history is the value.

## Reconciliation

When two sources disagree on the register's state (two machines, a session vs the tree), the tree wins — reconcile by re-enumerating at a common head, not by trusting either summary. A count that can't be recomputed from `head` + `command` is a claim, and a claim is not a finding.

## Where this plugs in

- `cross-family-review` verdicts that survive become register entries, enumerated at the reviewed head.
- `lane-claim` provenance (seat + machine) is the provenance an entry marks; the ID sweep is gated by lane ownership so two lanes never mint the same id.
- `diagnose` produces the `command` field — a tight, red-capable check is exactly what makes an entry recomputable.

**No authority without evidence. A count you can't recompute is a claim, not a finding.**
