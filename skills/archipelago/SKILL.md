---
name: archipelago
description: Jon's full-cycle, evidence-gated build protocol — typed contracts at every seam, gates that must be able to fail, loopback routing when reality disagrees, and a tamper-evident ledger. Use for any build with a definition of done worth proving (a feature, service, migration, launch phase), or when the user says "arch build", "archipelago", "run this through archipelago", or "under my arch workflow". Differentiator - nothing crosses a gate on claims alone; a claim is not done until a captured, hashed piece of evidence proves it.
---

# Archipelago — the evidence-gated build protocol

Source of truth: **`Navigata1/archipelago`** (public). This island is the covenant and the operating procedure; the runnable scripts and JSON schemas live in that repo (or vendored under a `protocol/` folder). Apply the methodology when invoked — run it, don't narrate it back.

> **The one rule that governs everything: nothing crosses a gate on claims alone.**

It is heavier than an ad-hoc edit — that weight is the point. For a one-line fix, don't. For anything you'd hand a stranger with a straight face, do.

## The shape of a mission — S0 → S7

| Stage | Output |
|---|---|
| **S0 Idea** | `idea.lock.json` — the goal as **falsifiable** claims, each with a `falsifiedBy` probe |
| **S1 Plan** | `plan.lock.json` — phases + gates + a readiness verdict; a blocked verdict stops kickoff cold |
| **S2–S5 Build loop** | code, evidence, a living `state.json`; every gate crossing produces a schema-valid artifact + a ledger entry |
| **S6 Governance** | the honesty verdict — what was enforced, what was advisory, what was waived (with reason) |
| **S7 Compound** | a compound note + a `results.tsv` row — the protocol experiments on itself, keeping a change only if a metric moved |

Three mechanisms keep the stages honest:

- **Gates.** Each gate is a real command with a captured, SHA-256-hashed evidence file. **A gate that can't fail is decoration** — the scorer here passed five falsification tests before it was trusted.
- **Loopback routing.** A failed gate doesn't just retry; it routes back to the *earliest stage whose output the failure falsifies* (`G4 → S2` when evidence falsifies the build; `--route S1` when it falsifies the plan). Loopbacks are recorded in state, never swept away.
- **The ledger.** Every mutation appends to `ops/mission/ledger.jsonl`, each entry hash-chained to the previous. Tamper-*evident*, not tamper-proof — a local JSONL chain, and it says so plainly.

## Band caps — you can't talk your way to a 5

The scoring rule that does most of the work. Dogfood audits score 0–5, but:

- a **UI claim with no runtime evidence** caps at **band 4**,
- an **unverified claim** caps the whole audit at **band 3**,
- a **falsified claim** drops it to **band 1**.

You cannot talk your way to a 5; you can only evidence your way there. Mark unverified work `unverified` — never launder it into `verified`. State enforced-vs-advisory explicitly; never imply it. This is the same law every other island in this archipelago obeys — here it is made mechanical.

## Operating procedure

Run everything **from the target repo root** (the scripts hardcode `ops/mission/*` relative to the working directory). Protocol gates `G0–G6` are conceptual (loopback routing, artifact typing); phase-gate ids like `P0-G1` are the **runnable commands** in `plan.lock`/`state.json` — same letter `G`, different namespaces, the single most error-prone point when driving this. `loop.py fail` does not auto-resolve a phase-gate id to its conceptual G-family, so `--route` is **required**, not optional — omit it and the failure silently routes to S2 regardless of what it actually falsifies.

```sh
python3 scripts/validate_contracts.py                                  # S0/S1: locks are schema-valid
python3 scripts/kickoff.py --idea ops/mission/idea.lock.json \
    --plan ops/mission/plan.lock.json --repo <org>/<repo> --out ops/mission/state.json
python3 scripts/loop.py status                                         # where am I, is the chain intact
python3 scripts/loop.py run-gates P0                                   # run every pending gate in a phase
python3 scripts/loop.py fail P1-G1 --reason "…" --route S1             # honest failure + loopback (route required)
python3 scripts/loop.py close-phase P0                                 # only when all gates passed AND fresh
```

Kickoff *consumes* the locks — it refuses a plan that doesn't govern this idea, a blocked verdict, or overwriting an existing mission, because **the repo is the memory**: a cold agent session with zero context can resume from the tree alone.

## Honest boundaries

- The ledger is tamper-evident local JSONL, not a hosted notary — and only entries *after* a given one prove it wasn't tampered with. The tip entry has nothing chained over it yet. For a gate-crossing tip (which carries an `evidenceSha256`), re-derive it from that raw gate evidence before trusting it at a phase-close or ship decision. For an event type with **no** evidence field (a phase-close or route event), re-derivation is undefined — distrust the unresumed tip outright and resume/append a subsequent entry to chain over it before relying on it.
- Runtime evidence proves the app worked *in that run, on that machine* — no more.
- Every script *should* degrade honestly and **record the degradation as a finding** rather than skip silently — but one known gap violates this: `validate_contracts.py` resolves its schema/example siblings relative to its own location, so if they aren't co-located the glob matches zero files and it **exits 0 over nothing** (a gate passing on no input). Pass explicit lock paths and confirm a non-zero file count before trusting the S0/S1 green.
- `loop.py fail` stamps the wrong provenance: it hard-codes the ledger's `fromGate` to `G2` for any id not starting with a capital `G`, and every phase-gate id is `P#-G#`, so `fromGate` reads `G2` no matter which gate failed — even with `--route` correct. Read the failing gate from the `--reason`/route you supplied, not from the ledger's `fromGate`, until the script parses the id.
- Evidence files are named by gate-id + date only (no run counter), so a fix-and-rerun cycle **overwrites the prior run's evidence** and the ledger's `evidenceSha256` for a superseded run then matches nothing on disk. The tip re-derivation above only works for a gate's *latest* run — raw evidence for earlier runs is not retained under current naming.
- Gate falsifiability (that a gate command can actually fail) is an author responsibility — the tooling validates schema shape, not whether a gate is decorative. Catch no-op gates (`exit 0` and the like) in G-review.

## Where this sits in the archipelago

Archipelago is the causeway the other islands cross. `cross-family-review` is its G-review; `finding-register` is the register its audits feed; `transport-complete` is how a passed mission ships; `handoff`'s wake protocol is how a cold session resumes it. Reviewed against the `idc-skill-authoring` canon and polished to match — the protocol that taught the fleet "no authority without evidence" belongs on the same shelf as the skills that inherited it.

**No authority without evidence. Nothing crosses a gate on claims alone.**
