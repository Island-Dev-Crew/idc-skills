---
name: connected-fix-prompt
description: Compose ONE dependency-ordered refinement prompt from a set of findings — rank N interdependent defects root-cause-before-symptom and by impact, each carrying its recomputable evidence, so a fixer clears them in a single correct-order pass instead of thrashing round by round. Use when you hold a list of findings (from finding-register, cross-family-review, or a vet) and need a single fixer mandate, or say "connected fix prompt", "order these fixes", "compose a fix plan", "sequence these findings". Differentiator - the composer that sits between the register that stores findings and the fixer that acts; not a store, not a finder, not a build method — it topologically orders and flags interdependencies so one fix is never undone by the next.
disable-model-invocation: true
argument-hint: "Which findings should be composed into a single ordered fix prompt?"
---

# Connected Fix Prompt — order the fixes before you fix

The composer between the register and the fixer. `finding-register` stores findings; the fixer acts; nothing in between decides the order. Hand a fixer a flat list and it works it top-to-bottom — symptom before root — so a later fix undoes an earlier one and you **thrash** round by round, re-vetting the same defects. This island emits ONE mandate that clears the whole list in a single **root-before-symptom** pass.

Two leading words: **thrash** (the round-by-round undo this prevents) and **root before symptom** (the order that prevents it).

**You compose this — no agent fires it.** It is user-invoked (`disable-model-invocation: true`), so it carries no description another agent can trigger; you run it by name and hand it the findings.

## Input — a set of findings, not one bug

A **list**, each item already enumerated with a recomputable command: a `finding-register` entry, a `cross-family-review` verdict item, or a vet's output. One finding needs no ordering — that is `diagnose`. This island earns its keep at **N interdependent findings**, where the order between them is the whole problem.

## The method — five moves

1. **Build the dependency graph.** For each pair ask - *does fixing A change what B is, or whether B still exists?* Draw an edge root→symptom. A root whose fix dissolves three symptoms is one edge to each. **If no edges exist, stop and say so:** an unordered set is a plain impact sort (`finding-register` / priority territory), not a dependency plan — this island earns its keep only at ≥1 interdependency, so hand an all-advisory list back to a priority sort rather than dress it as a fix graph.
2. **Topologically order, root before symptom.** Emit the sequence so every root precedes its symptoms. A fix applied before its root is the thrash - it gets undone the moment the root moves.
3. **Flag interdependencies.** Where fixing A *alters* B (changes B's evidence, not merely its position), say so - the fixer must **recompute B's check after A lands**, because A may have already closed B or moved its target.
4. **Rank by impact within the graph's freedom.** Topology fixes some order; where two findings are independent, the higher-impact one goes first. A tie is a judgment call - mark it as one.
5. **Break cycles — one at a time, until the residual is acyclic.** A genuine cycle (A alters B *and* B alters A, or any longer loop) has no linear root-before-symptom order, so Move 2 is undefined while one remains. Break it by fixing the **highest-impact node** first, or — when no node dominates — **collapse the cyclic findings into one combined fix**; collapse always terminates, so it is the fallback when impact ties or the loop won't decompose. Then **recompute every other cycle member's check bidirectionally** (not one-directional — A's fix may have moved B *and* B's target moved A's), and **re-derive the order on the residual graph**. A graph can hold more than one cycle, and breaking one can expose another: re-run the cycle check and repeat break→recompute→re-derive until the residual is a true DAG. Flag each broken cycle in the header as **enforced-bidirectional** so the fixer re-vets the whole cycle, not just what looks downstream.

## Carry the evidence — every finding brings its own check

Each ordered item carries its finding's recomputable command (the one that can go **red**), so the fixer self-verifies as it goes instead of trusting its own claim. A finding whose command can't run is `unverified` - carry it labeled `unverified`; never launder it into an item the fixer will assume is checkable.

## Output shape — the single fixer mandate

```
Fix in this order. After each, re-run its check before starting the next.

1. U-<n>  <title>            [ROOT]
   why-first: <what it dissolves or unblocks>
   check:     <recomputable command — red before, green after>
2. U-<m>  <title>            [depends on 1 — recompute check AFTER 1 lands]
   why-first: <the interdependency: what 1 changed about this>
   check:     <recomputable command>
```

The header states **enforced-vs-advisory per edge**: is an order *enforced* (the later fix genuinely breaks without the earlier) or *advisory* (merely more efficient)? Say which for every edge; never imply enforced when it is only advisory.

**Done when** the residual graph is a true DAG and every finding sits in an order where no root follows its symptom — reached either directly (the input was already acyclic) or by breaking every cycle first: each cycle resolved by a **combined or highest-impact fix**, recomputed bidirectionally, flagged enforced-bidirectional, and the order re-derived, repeating break→re-derive until no cycle remains. Never claim a clean order over a graph that still cycles — an unbroken cycle is reported as a cycle, not laundered into a fake sequence. Every interdependency carries a recompute note, every item carries a red-capable check, and each edge's enforced-vs-advisory status is stated.

## Where this plugs in

- **[`finding-register`](../finding-register/SKILL.md)** stores the findings and gives each a head + recomputable command - this island *consumes* that list; it never allocates ids or writes the register.
- **[`cross-family-review`](../cross-family-review/SKILL.md)** *produces* the findings - a `changes-requested` verdict's items are exactly this island's input, enumerated at the reviewed head.
- The fixer that acts is downstream - it runs the mandate in one pass, in the order this emits, re-vetting each check as it lands.

**No authority without evidence. An order you can't justify by a dependency edge is a guess, not a plan.**
