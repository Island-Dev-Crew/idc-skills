---
name: domain-modeling
description: Actively build and sharpen a project's domain model — challenge terms, invent edge-case scenarios, and write the glossary and decisions down the moment they crystallise. Use when pinning down domain terminology or a ubiquitous language, recording an architectural decision, or when another skill needs the domain model maintained. Differentiator - the active discipline that changes the model; merely reading CONTEXT.md for vocabulary is a one-line habit, not this skill.
---

# Domain Modeling — sharpen the language as you design

Actively build and sharpen the project's domain model *as you design*. This is the **active** discipline — challenging terms, inventing edge-case scenarios, and writing the glossary down the moment it crystallises. It is distinct from two neighbours: merely *reading* [`CONTEXT.md`](../../CONTEXT.md) for vocabulary is a one-line habit any skill does; and [`deep-modules`](../deep-modules/SKILL.md) designs *interfaces and seams*, while this designs the *language* those modules speak. A **ubiquitous language** — one term, one meaning, used identically in conversation, glossary, and code — is what keeps an agent and a human from quietly meaning different things by "account."

## The glossary lives in CONTEXT.md

A **project's** domain `CONTEXT.md` is a **glossary and nothing else** — totally devoid of implementation details. Not a spec, not a scratchpad, not a home for implementation decisions. (One exception: a repo-root *substrate* `CONTEXT.md` that also grounds architecture and composition — lane-claim paths, temp dirs, staging repo, how the islands compose — is exempt; keep this glossary discipline only for the terminology it owns.) Create files lazily: write `CONTEXT.md` when the first term resolves; create `docs/adr/` when the first ADR is needed. A repo with multiple bounded contexts carries a `CONTEXT-MAP.md` at the root pointing at each context's own `CONTEXT.md` and `docs/adr/`.

## During the session — five moves

- **Challenge against the glossary.** When a term conflicts with the existing language, call it out immediately: *"Your glossary defines 'cancellation' as X, but you seem to mean Y — which is it?"*
- **Sharpen fuzzy language.** When a term is vague or overloaded, propose a precise canonical one: *"You're saying 'account' — do you mean the Customer or the User? Those are different things."*
- **Discuss concrete scenarios.** Stress-test relationships with invented edge cases that force precision about the boundaries between concepts. No live user to put the edge case to? Test it against the code and glossary instead of answering it yourself — record only contradictions you can point to, never a self-answered assertion.
- **Cross-reference with code.** When the user states how something works, check the code agrees — and surface any contradiction: *"Your code cancels entire Orders, but you just said partial cancellation is possible — which is right?"* Also check the glossary's own citations: an ADR a term cites must resolve to a real file in `docs/adr/`; a dangling or fabricated reference gets surfaced the same way.
- **Update CONTEXT.md inline.** When a term resolves, write it down *right there* — don't batch. Capture it as it happens.

## ADRs — the worthiness gate

This island owns one thing about ADRs: **when** one is worth writing — and only for a term this session resolved. An architecture, technology, or infrastructure choice that didn't arise from resolving a term is out of jurisdiction here; skip it. Only offer an ADR when **all three** hold: it's **hard to reverse** (the higher of code-diff cost and team language-habit cost — a rename cheap in code but expensive for a team to unlearn still counts), **surprising without context** (a future reader will ask "why this way?"), and **the result of a real trade-off** (genuine alternatives existed and you picked one for reasons). Miss any one, skip it.

The ADR **template, format, and emission ceremony** live in [`grill`](../grill/SKILL.md) — the single owner of *how* an ADR is written and its user-approval rule. When a term you resolve here clears all three tests, hand the emission to grill rather than restating the template; this island decides *whether*, grill does *how*. No live user to approve it — this island also runs non-interactively, maintaining another skill's domain model — write the qualifying ADR as pending-approval and surface that upward to the caller instead of stalling.

## The evidence weld

- **Enforced-vs-advisory:** this discipline is **advisory** — nothing mechanically forces a term to be used consistently; the cross-reference-with-code move is the closest thing to a check, and it only *surfaces* a contradiction for a human to resolve. Say so.
- The glossary is the **single source of truth** for meaning — the same law [`writing-for-agents`](../writing-for-agents/SKILL.md) holds for every meaning in every doc. One term, one place, one definition.

**Done when** every term resolved in the session is written to `CONTEXT.md` (as it happened, not batched), each qualifying ADR has either the user's approval or is explicitly surfaced pending-approval to the caller, and no contradiction between the stated model and the code is left unsurfaced.

**No authority without evidence. One term, one meaning — challenged against the code, not just asserted.**
