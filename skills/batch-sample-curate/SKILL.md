---
name: batch-sample-curate
description: Draw N candidates from a probabilistic-output tool (image, video, design, copy generators) and curate to the best against an explicit rubric, recording why each candidate was kept or cut — the get-many-then-select economics of a stochastic generator. Use when a tool returns a different artifact every run and you must pick among many, or the user says "batch sample", "generate N and pick", "best of N", "curate the candidates", or "sample and select". Differentiator - independent draws selected against a scored keep/cut ledger, not one build refined toward a bar (gauntlet-loop) and not throwaway code answering one question (prototype).
disable-model-invocation: true
argument-hint: "What probabilistic tool are we sampling, and what does a winning candidate look like?"
---

# Batch Sample & Curate: get many, then select

A probabilistic-output tool returns a **different artifact every run** from the same prompt. When the tool exposes **no conditioning path** (no seed carry, no img2img, no send-back of the last output), each draw is independent and remembers nothing, so you can't refine one output toward a bar. You **draw N, then select** the best against an explicit rubric, and record what the winner beat. Variance is the resource; sampling is how you spend it.

**Route first:** if the generator *does* accept conditioning or feedback (seeded/img2img image models, a chat LLM you re-prompt with "make it warmer"), prefer `gauntlet-loop`'s build↔critic loop over blind resampling; you have a lever this skill assumes away. This skill is for the genuinely memoryless case, where re-drawing is the only move.

This is the one move the siblings don't make. `gauntlet-loop` *refines* a single build through a critic that can send it back; here, on a non-conditionable generator, there is no send-back, so it can't be corrected, only re-drawn. `prototype` builds throwaway code to answer a design question. Neither samples independent candidates and curates to a winner on a scored ledger. That ledger is the whole discipline.

## 1. Write the rubric first: the bar that can cut a candidate

Before drawing anything, name the criteria a candidate must satisfy, **falsifiable** so a draw can be cut on evidence, not vibes. Rank them if some dominate (a copy generator: on-brief > tone > length; an image: subject accuracy > composition > style). Without a rubric written first, "I picked the best" is unverified authority, a claim with nothing behind it.

## 2. Draw N: the sampling economics

N is a **spend**. A cap controls magnitude; it does not authorize external cost. Before any paid draw, obtain the operator's explicit spend approval or use an already-enforced budget they authorized for this run. Each draw costs credits, tokens, or wall-clock; each additional draw buys *diminishing* marginal quality. Draw independent candidates from the **same** prompt in parallel, not one nudged toward the bar.

- **Start small** (3-5). If the best of the batch already clears the rubric, **stop**; more draws are pure waste.
- **If none clear, the gap is usually the prompt, not the count.** Fix the prompt and redraw; drawing 50 of a mis-specified thing burns spend on the wrong target.
- **Bound the failure path: set an abort gate.** Pick a cap up front (a spend ceiling or K prompt-fix rounds, e.g. K=3). If after K revisions no candidate clears the rubric, **stop and declare a capability ceiling**: the tool can't hit this bar. Escalate, relax a criterion, or change tools. Prompt-fix→redraw is not an infinite loop; a give-up is a first-class outcome.
- **Keep or cut, then redraw; never send back.** On a non-conditionable generator there is no memory of the last sample, so there is nothing to improve; widening N is the only lever it gives you. (If the tool *does* condition, you're in the wrong skill; see the routing note above.)

## 3. Score every candidate: the keep/cut ledger

Score each candidate against the rubric and record the verdict for **every** one (kept *and* cut) with the reason tied to a named criterion. Score against the rubric alone, not against "which draw came first," so the batch isn't anchored to candidate #1.

```
| # | rubric result                    | verdict | why (one line)                          |
|---|----------------------------------|---------|-----------------------------------------|
| 1 | subject ✓  comp ✓  style ✗       | cut     | style reads generic, misses the brief   |
| 2 | subject ✓  comp ✓  style ✓       | KEEP    | clears all three; strongest composition |
| 3 | subject ✗                        | cut     | wrong subject — hard fail, no rescore   |
```

**Enforced-vs-advisory:** the rubric and ledger are **advisory**, a discipline you follow. Nothing here mechanically blocks a lazy pick unless you wire a script to gate it. A candidate kept on gut feel is `unverified`; mark it so, and never launder it into a rubric-passed row it didn't earn.

## 4. Curate to the winner: keep the cuts as evidence

Select the top candidate. **On a genuine tie** (two or more KEEP rows that pass every criterion identically) break by the margin on the highest-ranked criterion, then by a named secondary (e.g. composition strength), and **record the tie-break reason as its own ledger line** so the pick stays falsifiable. **Keep the ledger and the cut candidates reachable** (a folder, an issue, a commit): the cuts are the evidence the winner beat them. A selection with no visible alternatives is an unverifiable claim; don't delete the batch down to the one you shipped.

## Reach for a sibling instead when

- You're pushing **one** artifact to a high bar through a build↔critic loop → `gauntlet-loop`.
- You're answering **one** design question with disposable code → `prototype`.

**Done when** the rubric was written before the draw, every candidate has a keep/cut row tied to a criterion, and either the winner is selected (with any tie-break recorded) and the cuts survive as reachable evidence, **or** the abort gate fired: the capability ceiling is declared and the batch escalated. A give-up is a valid end state; a good-looking one appearing is not.

**No authority without evidence. The best is only the best against a rubric that could have cut it, with the ledger showing what it beat.**
