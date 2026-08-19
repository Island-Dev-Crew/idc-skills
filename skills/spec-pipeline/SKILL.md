---
name: spec-pipeline
description: Turn a discussed feature into a spec, break it into tracer-bullet tickets with blocking edges, implement each at pre-agreed seams with TDD, and optionally drive the whole thing as a persistent goal loop. Use when the user wants to plan and build a feature end to end, says "spec this", "break into tickets", "implement the spec", "tracer bullets", or "run this as a goal". Differentiator - one pipeline from spec to shipped, with Ondrej's persistent runner splicing onto Pocock's spec/tickets/implement chain.
---

# Spec Pipeline: spec → tickets → implement → loop

One island for the whole path from a settled understanding to shipped code. It adopts Matt Pocock's engineering chain (*to-spec*, *to-tickets*, *implement*) and splices David Ondrej's *goal-loop* as the persistent runner for the mechanical stretch. Four stages; run them in order, and stop at the checkpoint each names.

Two leading words carry the pipeline: a **tracer bullet** (a thin vertical slice through every layer that actually works end to end) and the **frontier** (the tickets whose blockers are all done, ready to start now).

## Stage 1: Spec (synthesis, not interview)

Take the current conversation and codebase understanding and produce a spec (a PRD). **Do not interview**. Synthesize what you already know; if the understanding isn't there yet, run the `grill` island first, not this one. If the effort is *too big for a single spec* (foggy, spanning many sessions), it needs [`wayfinder`](../wayfinder/SKILL.md) first. `wayfinder` is **user-invoked**: you cannot fire it yourself; tell the operator to run it, then let each resolved decision feed a spec here. (Stage 2's ticket **frontier** is the tracer-bullet build analogue of wayfinder's decision-frontier: same leading word, one referent for build slices, the other for decisions.)

1. Explore the repo. Use the project's domain glossary throughout; respect ADRs in the area you touch.
2. Before sketching seams, list every Implementation Decision the spec will need. If any would be invented rather than derived from the conversation, the repo, or ADRs, **stop and run `grill` (or `wayfinder`)**: do not proceed. Unknowns that remain go into the spec's Open Questions, never as a fabricated decision.
3. Sketch the **seams** at which you'll test the feature. Prefer existing seams; use the highest seam possible; the fewer new seams, the better: ideal is one. **Confirm the seams with the user** before writing the spec.
4. Write the spec: Problem Statement · Solution · a LONG numbered list of User Stories (`As an <actor>, I want <feature>, so that <benefit>`) · Implementation Decisions (modules, interfaces, schema, contracts: no file paths or code snippets, they rot) · Testing Decisions (test external behaviour not implementation; which modules; prior art) · Out of Scope · Notes. Publish it where the repo keeps specs.

**Done when** the seams are user-confirmed and the spec is published.

## Stage 2: Tickets (tracer bullets with edges)

Break the spec into **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

- Each slice cuts a narrow but *complete* path through every layer (schema → API → UI → tests): vertical, never a horizontal slice of one layer.
- A completed slice is demoable or verifiable on its own, and sized to fit one fresh context window.
- Give each ticket its **blocking edges**: the tickets that must finish first. A ticket with no blockers can start immediately.
- **Prefactor first:** "make the change easy, then make the easy change."

**Wide refactors are the exception.** A mechanical change whose blast radius fans across the codebase can't land as one green slice. Sequence it **expand → migrate → contract**: add the new form beside the old (nothing breaks), migrate call sites in batches sized by blast radius (each its own ticket, CI green batch to batch because the old form still exists), then delete the old form once no caller remains. Advisory default for batch size: one batch per owning module or directory, capped at roughly 10-20 call sites (what one fresh context window can migrate and verify), shrunk further where call sites diverge in behavior; override with a stated reason.

Present the breakdown as a numbered list (title · blocked-by · what it delivers), quiz the user on granularity and edges, iterate until approved, then publish one ticket per unit in dependency order: native blocking links on a real tracker, or one file per ticket locally. Work the **frontier**: any ticket whose blockers are all done.

**Done when** the user approves the breakdown and the tickets are published with their edges.

## Stage 3: Implement (TDD at the seams)

Implement each frontier ticket:

- Use **TDD** at the pre-agreed seams: write the test at the seam, watch it fail, implement, watch it pass. **Migration tickets** (from an expand → migrate → contract sequence) use characterization tests instead: green before, green after, diff reviewed; the red-first discipline applies only to tickets introducing new behavior.
- Run typechecking regularly and single test files regularly; run the full suite once at the end.
- Commit to the current branch. Then hand the diff to the `cross-family-review` island: the seat that implemented never reviews itself. If no second model family is reachable, mark the ticket `verdict-pending` (never verified) and record the gap in the commit; the review gate binds only when a second family exists, otherwise it is advisory.

**Done when** the ticket's acceptance criteria are met, the suite is green, and a cross-family verdict has landed at the head. Lacking a second family, the ticket is marked `verdict-pending` with that gap on record.

## Stage 4: Loop (optional persistent runner)

For a long mechanical stretch (a migration, a coverage lift, a batch of tracer tickets), drive it as a persistent `/goal` loop instead of turn-by-turn. Use only when all three hold: >30 min of mechanical work, a **verifiable stop condition** (tests pass, coverage ≥ X, build green), and an agent-ready repo. Write the contract compactly:

```
**Objective:** <one sentence, one concrete outcome>
**Read first:** <spec / tickets / files>
**Constraints:** <what must NOT change; no new deps; no unrelated refactors>
**Validate:** `<exact command>` after each change
**Stop when:** <verifiable condition>, OR when a change needs human/product input
```

Forbid reward-hacking explicitly: *"Do not delete, skip, weaken, or narrow tests to make the goal pass."* Never instruct it to create new ADRs (those need the user's approval). Always review the diff before merging: long autonomy means more code to validate, not less.

**Done when** the stop condition is verifiably met and the diff has been reviewed.

**No authority without evidence. A tracer bullet is done when it runs end to end, green, reviewed by another family.**
