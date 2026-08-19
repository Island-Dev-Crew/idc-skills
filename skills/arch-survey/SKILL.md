---
name: arch-survey
description: Proactively survey a whole codebase for architectural refactor opportunities — mine change-history hot-spots, test each against the deep-module deletion test, and rank them as a before/after report. Use when no bug is in play and the user asks "survey the architecture", "where should we refactor", "find refactor opportunities", "which modules should we deepen", or "architectural hot-spots". Differentiator - the discovery-and-ranking scan across the codebase; deep-modules designs ONE already-chosen module, diagnose is the reactive bug loop, domain-modeling shapes the language.
---

# Arch Survey: mine the hot-spots, rank the deepenings

Find where a codebase would most repay an architectural refactor, and rank the candidates. Nothing is broken; this is the *discovery* scan that runs before anyone picks a module to work on. It borrows its vocabulary and its central test from [`deep-modules`](../deep-modules/SKILL.md) (**module**, **interface**, **depth**, **seam**, **leverage**, **locality**, the **deletion test**). Use those terms exactly. It does **not** design an interface (that is `deep-modules`, on the one candidate you pick) and does **not** chase a failing test (that is [`diagnose`](../diagnose/SKILL.md)). Read [`CONTEXT.md`](../../CONTEXT.md) first so candidates are named in the project's own language, and check ADRs in the areas you touch.

## 1. Scope by change-history: YAGNI

Deepening a module only pays back on the parts that keep changing. Decide *where* to look before you look. If the user named a direction (a module, a subsystem, a pain point), take it and skip the mining. If that named area turns out **healthy** (low churn, already deep, passes the deletion test), emit exactly that: a clean survey that finds nothing to refactor is a valid, reportable result; say so plainly and stop, don't manufacture a candidate to have something to rank. Otherwise mine the hot-spots, the files that churn most over a recent stretch of history:

```bash
# rank tracked files by commit-touch count over the last ~200 commits
git log --pretty=format: --name-only -n 200 | grep -v '^$' | sort | uniq -c | sort -rn | head -25
```

The count is the evidence: a hot-spot is a file with a *witnessed* churn number, not a hunch about what "feels messy". If churn is flat and scattered with no clear peak, widen the net and say so: a survey with no hot-spots is a finding, not a failure.

## 2. Survey each hot-spot for shallowness

The module frame presumes **code** modules with real interfaces and callers. A whole-codebase churn scan also surfaces non-module hot-spots (config, generated, vendored, and data files) that churn for reasons a deepening can't fix; leave those out of frame, or handle them by judgment, and never force them through the deletion test. Walk the top *code* files. Note where you hit friction; don't force a rigid checklist:

- Understanding one concept means bouncing between many small modules (no **locality**).
- A **shallow** module: interface nearly as complex as the implementation.
- Pure functions extracted only for testability, while the real bug surface is *how they're called*.
- Tightly-coupled modules leaking across their seams; areas hard to test through the current interface.

## 3. Apply the deletion test: the gate

Run the **deletion test** (owned by `deep-modules`) on every suspect: imagine deleting the module. If complexity **concentrates** (reappears spread across N callers), it earned its keep and deepening it has leverage. If complexity merely **moves**, it was a pass-through; drop the candidate. A "yes, concentrates" is the signal; a candidate that fails the deletion test does not enter the ranking, however high its churn.

## 4. Rank as a before/after report

Emit one self-contained report (write it outside the repo tree unless the user says otherwise). Per surviving candidate:

- **Files**: the modules involved, named from `CONTEXT.md`.
- **Churn**: the touch-count from step 1, verbatim. This is the load-bearing evidence.
- **Problem / Solution**: the friction, then the deepening in plain English (no interface designed yet).
- **Before / After**: the shallow shape now vs. the deep shape proposed, in terms of locality and leverage and how tests would improve.
- **Strength**: `Strong` / `Worth exploring` / `Speculative`, earned by churn + deletion-test result, never by vibe.

Close with the one candidate you'd tackle first and why. If a candidate contradicts an ADR, surface it only when the friction is real enough to reopen the ADR, and mark the conflict.

## 5. Hand off: do not poach

Stop at the ranked report. When the user picks one, that candidate crosses to [`deep-modules`](../deep-modules/SKILL.md) to design its interface and seam. If a good candidate needs a concept `CONTEXT.md` lacks, route the naming to [`domain-modeling`](../domain-modeling/SKILL.md). This island surveys and ranks; it does not build.

## Evidence weld

- **Enforced-vs-advisory:** the churn mining is a **reproducible command**: anyone can re-run it and get the same ranking; that number is `enforced` evidence. The deletion test and the strength badge are **advisory** design judgments; say so, and never launder a hunch into a `Strong` without the churn count and a stated deletion-test result behind it.
- A candidate with no churn evidence and no deletion-test verdict is `unverified`; label it so, and never promote it into the ranked list as if it were vetted.

**No authority without evidence. The churn count is the evidence; the ranking is not.**
