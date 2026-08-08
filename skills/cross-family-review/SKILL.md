---
name: cross-family-review
description: Run the IDC review ceremony — an independent reviewer from a different model family reviews a diff at an exact head, along the Standards and Spec axes, and returns a named-seat verdict bound to that head. Use when the user wants a branch, PR, or work-in-progress reviewed, says "cross-family review", "fable review", "gpt review", "review before merge", or wants an adversarial second opinion before shipping. Differentiator - this is the crown ceremony; the seat that wrote the code never reviews it, verdicts bind an exact SHA and void on move, and independence is a claim the reviewer's fresh clone must back.
---

# Cross-Family Review — the crown ceremony

The most valuable island, because it is the one IDC has run in production with receipts. It fuses David Ondrej's cross-family reviewer launches (*fable-review*, *gpt-review*), Matt Pocock's two-axis *code-review* structure, and the Garnet review record: named seats, provenance marked in both directions, exact-head verdicts, and void-on-move. Anyone can fuse two public repos; only a ceremony with receipts is a moat.

**The governing thesis:** *No authority without evidence. Acceptance is a decision made on evidence the author cannot fake.* Everything below serves that one sentence.

## The three laws

1. **The author never reviews their own work.** The seat that produced the diff does not launch, steer, or write its own reviewer. Independence is the product; a self-review destroys it. If you wrote the code, you set up the ceremony — you do not sit in the reviewer's chair.
2. **A different family reviews.** The reviewer runs on a different model family from the author (Fable reviews Codex's work; Codex reviews Fable's). A sustained cross-family disagreement, resolved by principle rather than seniority, is how the ceremony locates the right answer — it beat single-family consensus twice in the production record. If no second family is reachable, the ceremony halts — see Step 3.
3. **The verdict binds an exact head, and voids on move.** A verdict names the SHA it reviewed. The moment `HEAD` moves, the verdict is void — not stale, void — including a message-only amend or reword; a new SHA always means a new ceremony, never a re-bind. Re-review the new head or do not claim review.

## Process

### 1. Pin the exact head

```bash
git rev-parse HEAD                       # the head under review — record it in full
git status --porcelain                   # MUST be empty; a dirty tree has no reviewable head
```

Whatever fixed point the user names is the base — a SHA, branch, tag, `main`, `HEAD~5`. Confirm it resolves and the diff is non-empty *before* launching anything:

```bash
git rev-parse <base>                     # bad ref fails here, not inside a subagent
git diff <base>...HEAD --stat            # three-dot: compare against the merge-base
git log <base>..HEAD --oneline           # the commit list
```

An empty diff or bad ref fails at this step. **Done when** you can state the reviewed head (full SHA), the base, and a non-empty diff command, on a clean tree.

### 2. Identify the two axes' sources

- **Standards** — the diff conforms to the repo's documented standards (`CODING_STANDARDS.md`, `CONTRIBUTING.md`, ADRs in the touched area), plus the Fowler **smell baseline** in [references/verdict-format.md](references/verdict-format.md), which applies even when the repo documents nothing. A documented repo standard always overrides the baseline; baseline smells are always judgement calls, never hard violations. Skip anything tooling already enforces.
- **Spec** — the diff faithfully implements the originating issue / PRD / spec. Find it via issue references in the commit messages, a path the user passed, or a spec file matching the branch. If there is genuinely no spec, the Spec axis reports "no spec available" — it does not invent one.

### 3. Launch the reviewer — from a fresh clone, cross-family

**No second family reachable.** Confirm this before pinning the head, not after. If no different-family reviewer seat can be launched (single-seat environment, missing launch mechanics), halt and issue a `blocked` verdict with Reviewer seat recorded as `NONE AVAILABLE` and the reason stated — same-family review is never a substitute and must never be labeled as the reviewer seat. A single-seat mechanics rehearsal is fine for calibration only if marked `REHEARSAL — no independence claim, not a verdict`; it never enters `finding-register` and never gates a merge.

The reviewer must see the code the way a stranger would. **A reviewer's clone is part of the independence claim** — it reads the exact head from a clean checkout, not the author's warm working tree, and never from a worktree (worktrees share `.git` state; see the `worktree-fleet` island). Give it the reviewed SHA, the diff command, the axis sources — and then get out of its way.

Ondrej's launch discipline, kept verbatim in spirit: *give the reviewer the necessary context, stay neutral, do not nudge it toward any one solution. Tell it what to review broadly — let it find its own bugs. Tell it to work extremely hard and surface any critical or serious issue. When it finishes, show its exact response in full — do not rewrite it, do not soften it.*

Run the two axes as **parallel subagents on different families** so they don't pollute each other's context:

- **Standards subagent** — reviewer family ≠ author family. Give it the diff command, the commit list, the documented-standards files, and the smell baseline pasted in full (it has no other access to it). Brief: *"Per file/hunk: (a) every place the diff violates a documented standard — cite the standard; (b) any baseline smell — name it, quote the hunk. Distinguish hard violations from judgement calls. Documented standards override the baseline. Skip what tooling enforces. Under 400 words."*
- **Spec subagent** — give it the diff command, the commit list, and the spec. Brief: *"(a) requirements asked for but missing or partial; (b) behaviour not asked for (scope creep); (c) requirements that look implemented but wrong. Quote the spec line for each finding. Under 400 words."* If the spec is missing, skip this subagent and say so.

### 4. Return the verdict — named, provenance-marked, head-bound

Aggregate under `## Standards` and `## Spec`, verbatim or lightly cleaned. **Do not merge or rerank across axes** — a change can pass one and fail the other, and the separation is what stops one axis masking the other. Then issue the verdict using the template in [references/verdict-format.md](references/verdict-format.md). Every verdict carries, non-negotiably:

- **Reviewed head** — the full SHA from step 1.
- **Seats** — the author seat and the reviewer seat, each named by family (`OpenAI Codex`, `Claude Fable 5`, `Jon Isaac`). Provenance is marked in both directions and the record is corrected against *either* seat when either is wrong — the ceremony has corrected the chat seat and the reviewer, on the record.
- **Disposition** — `approve` / `changes-requested` / `blocked`, with the worst finding per axis.
- **Void-on-move notice** — this verdict binds `<SHA>`; it is void the moment `HEAD` moves.

**Done when** the verdict names its reviewed head, both seats, and a disposition, and a reader who trusts none of it can recompute every finding from the diff command alone.

## Adversarial, not consensus

For verdicts, use **adversarial named-seat review**, not a consensus average. No seat can hide in an average; a named seat owns its call and a cross-family disagreement surfaces the real answer instead of blending it away. Consensus and best-of-N breadth earn their place in *draft ideation* — never in the verdict that gates a merge.

## Where this plugs in

- The launch mechanics (`fable-review` / `gpt-review`) are how step 3 spawns the reviewer; the seat that implements never launches its own.
- Findings that survive the verdict enter the `finding-register` island — enumerated at the reviewed SHA, provenance-marked, swept for ID collisions before allocation.
- A `changes-requested` verdict routes back through the author seat, never the reviewer, and the re-review binds the *new* head.
- Before merging, registering findings, or otherwise relying on a verdict, recompute `git rev-parse HEAD` and compare it to the verdict's reviewed head — a mismatch means void, full stop; return to Step 1.

**No authority without evidence. The verdict is void the moment the head moves.**
