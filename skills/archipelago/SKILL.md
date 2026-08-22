---
name: archipelago
description: Jon's full-cycle, evidence-gated build protocol — typed contracts at every seam, gates that must be able to fail, loopback routing when reality disagrees, and a tamper-evident ledger. Use for any build with a definition of done worth proving (a feature, service, migration, launch phase), or when the user says "arch build", "archipelago", "run this through archipelago", or "under my arch workflow". Differentiator - nothing crosses a gate on claims alone; a claim is not done until a captured, hashed piece of evidence proves it.
---

# Archipelago: the evidence-gated build protocol

The signed local island is the operating covenant. Upstream provenance is **`Navigata1/archipelago`** at `b9f7cee2823f9791503db20f33b22c9e20af7abe`. The runnable scripts, schemas, examples, license, source hashes, and reviewed local hardening are vendored under `protocol/`; never fetch or execute upstream at runtime. `protocol/UPSTREAM.json` binds every unchanged or modified helper to its upstream and result digest. Apply the methodology when invoked: run the locally reviewed procedure, don't narrate it back.

> **The one rule that governs everything: nothing crosses a gate on claims alone.**

It is heavier than an ad-hoc edit, and that weight is the point. For a one-line fix, don't. For anything you'd hand a stranger with a straight face, do.

## The shape of a mission: S0 → S7

| Stage | Output |
|---|---|
| **S0 Idea** | `idea.lock.json`: the goal as **falsifiable** claims, each with a `falsifiedBy` probe |
| **S1 Plan** | `plan.lock.json`: phases + gates + a readiness verdict; a blocked verdict stops kickoff cold |
| **S2-S5 Build loop** | code, evidence, a living `state.json`; every gate crossing produces a schema-valid artifact + a ledger entry |
| **S6 Governance** | the honesty verdict: what was enforced, what was advisory, what was waived (with reason) |
| **S7 Compound** | a compound note + a `results.tsv` row; the protocol experiments on itself, keeping a change only if a metric moved |

Three mechanisms keep the stages honest:

- **Gates.** Each gate is a real command with a captured, SHA-256-hashed evidence file. **A gate that can't fail is decoration**: the scorer here passed five falsification tests before it was trusted.
- **Loopback routing.** A failed gate doesn't just retry; it routes back to the *earliest stage whose output the failure falsifies* (`G4 → S2` when evidence falsifies the build; `--route S1` when it falsifies the plan). Loopbacks are recorded in state, never swept away.
- **The ledger.** Every mutation appends to `ops/mission/ledger.jsonl`, each entry hash-chained to the previous. Tamper-*evident*, not tamper-proof: a local JSONL chain, and it says so plainly.

## Band caps: you can't talk your way to a 5

The scoring rule that does most of the work. Dogfood audits score 0-5, but:

- a **UI claim with no runtime evidence** caps at **band 4**,
- an **unverified claim** caps the whole audit at **band 3**,
- a **falsified claim** drops it to **band 1**.

You cannot talk your way to a 5; you can only evidence your way there. Mark unverified work `unverified`; never launder it into `verified`. State enforced-vs-advisory explicitly; never imply it. This is the same law every other island in this archipelago obeys; here it is made mechanical.

## Operating procedure

Run everything **from the target repo root**; resolve `<archipelago-skill-dir>` to the directory containing this `SKILL.md`. The vendored scripts intentionally read and write `ops/mission/*` relative to the current working directory. Protocol gates `G0–G6` are conceptual (loopback routing, artifact typing); phase-gate ids like `P0-G1` are runnable commands in `plan.lock`/`state.json`. The hardened loop resolves the exact phase-gate to its embedded G-family, resets a manually failed gate, records the exact id, and blocks phase close until a later passing run resolves its loopback.

```sh
python3 <archipelago-skill-dir>/protocol/scripts/validate_contracts.py ops/mission/idea.lock.json ops/mission/plan.lock.json
python3 <archipelago-skill-dir>/protocol/scripts/kickoff.py --idea ops/mission/idea.lock.json \
    --plan ops/mission/plan.lock.json --repo <org>/<repo> --out ops/mission/state.json
python3 <archipelago-skill-dir>/protocol/scripts/loop.py status
python3 <archipelago-skill-dir>/protocol/scripts/loop.py run-gates P0
python3 <archipelago-skill-dir>/protocol/scripts/loop.py fail P1-G1 --reason "…" --route S1
python3 <archipelago-skill-dir>/protocol/scripts/loop.py verify-ledger
python3 <archipelago-skill-dir>/protocol/scripts/loop.py close-phase P0
python3 <archipelago-skill-dir>/protocol/scripts/run_runtime_probes.py
python3 <archipelago-skill-dir>/protocol/scripts/dogfood_lanes.py
```

Kickoff *consumes* the locks. It validates both contracts, captures their stable repository bytes, and records their SHA-256 digests. Every later loop action rejects lock drift or any gate id, title, or command that differs from the approved `plan.lock`. It also refuses a plan that doesn't govern this idea, a blocked verdict, a symlink/out-of-repository lock, or overwriting an existing mission, because **the repo is the memory**: a cold agent session with zero context can resume from the tree alone.

## Honest boundaries

- The ledger is tamper-evident local JSONL, not a hosted notary, and only entries *after* a given one prove it wasn't tampered with. The tip entry has nothing chained over it yet. For a gate-crossing tip (which carries an `evidenceSha256`), re-derive it from that raw gate evidence before trusting it at a phase-close or ship decision. For an event type with **no** evidence field (a phase-close or route event), re-derivation is undefined: distrust the unresumed tip outright and resume/append a subsequent entry to chain over it before relying on it.
- `loop.py status` and `loop.py verify-ledger` both exit nonzero on a broken ledger. Use `verify-ledger` in CI because its output surface is narrow and purpose-built.
- Runtime evidence proves the app worked *in that run, on that machine*, and no more.
- Bare `validate_contracts.py` validates only the bundled examples. Mission gates must pass the explicit idea/plan paths and confirm both filenames appear. The dependency-free local validator covers the schema keywords used by the vendored contracts; it does not claim general JSON Schema 2020-12 conformance.
- Gate evidence uses a unique nanosecond filename, so reruns retain prior raw output instead of overwriting it. The ledger is still local and tamper-evident rather than a hosted notary.
- Gate commands are intentionally executable authority. `plan.lock.hitl` must represent the human approval for those exact hash-bound command strings; never kickoff a plan received from an untrusted source. If a repository carries `ops/mission/render-sotu.mjs`, rendering additionally requires `IDC_ARCHIPELAGO_NODE` to be an absolute executable and `IDC_ARCHIPELAGO_NODE_SHA256` to match its bytes; the loop does not discover Node from `PATH`.
- Gate falsifiability (that a gate command can actually fail) is an author responsibility: the tooling validates schema shape, not whether a gate is decorative. Catch no-op gates (`exit 0` and the like) in G-review.

## Where this sits in the archipelago

Archipelago is the causeway the other islands cross. `cross-family-review` is its G-review; `finding-register` is the register its audits feed; `transport-complete` is how a passed mission ships; `handoff`'s wake protocol is how a cold session resumes it. Reviewed against the `idc-skill-authoring` canon and polished to match: the protocol that taught the fleet "no authority without evidence" belongs on the same shelf as the skills that inherited it.

**No authority without evidence. Nothing crosses a gate on claims alone.**
