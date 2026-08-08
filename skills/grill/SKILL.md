---
name: grill
description: Interview the user relentlessly to reach a shared understanding of a plan, decision, or idea before building — in three modes (ambush, drill, batch) — and emit the settled decisions as ADRs. Use when the user wants to stress-test their thinking, says "grill me", "grill", "interview me", "prompt me", "ask me questions", or is about to build something under-specified. Differentiator - always emits an ADR record of what was decided; facts are looked up, only decisions are asked.
---

# Grill — relentless interview, three modes

Fuses Matt Pocock's relentless drilling (*grill-me* / *grilling* / *batch-grill-me*) with David Ondrej's ambush timing (*prompt-me*) and one IDC addition: the settled decisions become **ADRs**, so the understanding survives the session that produced it.

Map the work as a **design tree**: every decision branches into the decisions that hang off it. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask *now* without guessing at answers you haven't heard yet.

The one law across all modes: **facts are your job, decisions are the user's.** If a fact can be found by exploring the environment (filesystem, tools, git), look it up — never ask the user for something you could find. Put each *decision* to the user and wait. For every question, give your **recommended answer**.

Boundary: if the answers live with **someone else** — a stakeholder, not the user in front of you — park that branch: name the stakeholder and the exact gap, and tell the user to invoke [`to-questionnaire`](../to-questionnaire/SKILL.md) themselves (it's user-invoked, not something you can trigger). Keep grilling the rest of the frontier. Grill mines *you*; to-questionnaire mines *them*.

## Three modes

Pick by how the user wants to be interrogated. When unsure, ask which — or default to **drill**.

### Drill (one at a time)
Walk the decision tree depth-first, resolving dependencies one by one. Ask **one question at a time**, each with your recommended answer, and wait for the answer before the next. Asking several at once is bewildering. Use when decisions are tightly coupled and each answer reshapes the next question.

### Batch (frontier per round)
Work the tree in **rounds**. Ask the *whole frontier* in one round, then wait. Each round's answers push the frontier outward and unblock downstream questions; recompute the frontier and ask the next round. A question depending on another still-open question belongs to a *later* round. Use when the frontier is wide and the user prefers throughput — it cures the drag of the public one-at-a-time grill, where the tail of the session is easy questions answered "yes, yes, yes" one slow turn each.

Format each round for **fast visual scan** (the user is often dictating): number every question, prefix each with an emoji marker for the eye to catch (`1️⃣`, `2️⃣`, `3️⃣`…), and give each its recommended answer inline, so the user can blast back "Q1 agree, Q2 change to X, Q3 agree" in one pass.

Reconciling a round: within one reply, the user's last stated value for a question wins — echo any superseded value back in the next round's recap so the correction is on record. A duck ("whatever's easiest", "you pick") adopts your inline recommendation; echo it as "adopting: X (deferred)" and fold it into the completion recap below rather than re-asking it.

### Ambush (extract what's in their head)
The user hasn't told you what matters yet. Interview to surface **priorities, avoided work, and importance** — what remains, what's being dodged, what really matters and what doesn't. Trigger shape: *"start prompting me to figure out what other work needs doing, what we're avoiding, what has importance and what doesn't."* Use at the start of a project, before there's even a plan to drill.

## Facts are found, not asked

When a frontier question needs a fact from the environment, dispatch a sub-agent (or just look) — don't ask. Search the repo and whatever org context the user has already surfaced — no further. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions *downstream* of it wait; ask the rest of the frontier now. If the lookup comes back empty, the fact-slot becomes a decision: report "no existing convention found for X" and ask it as a decision with your recommended answer.

## Completion — and the ADR emission

A grill session is done when the **frontier is empty**: every branch visited, nothing left silently assumed. **Do not act on it until the user confirms shared understanding.** Confirm it with one consolidated recap of every settled decision (including any deferral-adopted values) and a single explicit yes/no — that answer, not the last per-question reply, is what satisfies this gate.

Then emit the ADRs — this is the IDC step the public grill skills stop short of. For each material decision settled during the grill, write a short Architecture Decision Record so the *why* outlives the conversation:

```
# ADR <NNNN> — <decision title>
Status: accepted
Context: <the question that forced the decision — one or two sentences>
Decision: <what was chosen>
Alternatives rejected: <what was considered and why it lost>
```

Never create ADRs the user hasn't approved — the grill *is* the approval; emit an ADR only for decisions the user actually confirmed. Save them where the repo already keeps ADRs (`docs/adr/`, `docs/decisions/`); if there's no convention, put them somewhere sensible and say where.

**Done when** the frontier is empty, the user has confirmed shared understanding, and every confirmed material decision has an ADR.

**No authority without evidence. The decisions are the user's; the facts are yours to find.**
