---
name: skill-duel
description: Run an incumbent skill against a challenger through one identical gauntlet — same executor cases, same defect-tied critic, same seat — and return a swap or no-swap verdict welded to the scores; a challenger displaces the incumbent only by strictly beating it, a tie keeps the seat. Use when a capped skill pack is at its slot limit and a candidate wants in, when a deprecated slot needs a defender, or the user says "skill duel", "skill-duel", "run a duel", "challenger vs incumbent", "defend the slot", or "who wins the seat". Differentiator - head-to-head, not skill-tune's solo own-score loop and not cross-family-review's single-diff verdict; the incumbent wins ties and a script decides the swap, so no seat changes on a claim.
disable-model-invocation: true
argument-hint: "Which incumbent slot, and which challenger is contesting it?"
---

# Skill Duel — the mechanical governor of a capped pack

The endgame island. Once a pack is at its cap (the 50-slot archipelago), nothing changes except two ways: a **won duel** displaces an incumbent, or a **deprecated slot** is filled. Everything else is deadlock by design — churn is the enemy, and this island is the only gate through it. It borrows the gauntlet's executor-and-critic harness ([`gauntlet-loop`](../gauntlet-loop/SKILL.md)) and the head-bound named-seat verdict ([`cross-family-review`](../cross-family-review/SKILL.md)), and points them at one question: *does the challenger earn the seat?*

**The governing thesis:** *No authority without evidence. A seat changes hands only on a captured head-to-head both contestants could have lost — never on a claim, and never on a tie.*

## The two laws

1. **One identical gauntlet, or no verdict.** Both skills run the **same executor challenge cases**, scored by the **same defect-tied critic**, in the **same seat**. Fairness is the harness being byte-identical — only the skill under test differs; the case-set, the critic, the seat, and the round cap are held constant across both runs. A defect-tied case ties each score to a specific defect the case can expose (per `gauntlet-loop`'s falsifiable bar) — never a vibe. The critic is **blind and independent** (a `cross-family-review` seat scores the artifact, not the builder's self-report); note the split from that ceremony — there the *reviewer* differs from the author, here the *executor seat* is held identical for both contestants so the seat is not a confound, and only the critic is independent.
2. **Strict-beat, tie-to-incumbent.** The challenger displaces the incumbent **only** by a strictly higher mean over the shared cases. A tie keeps the incumbent; a loss keeps the incumbent. This incumbency bias is the anti-churn governor, not an accident — a proven island is not evicted by a coin-flip.

## Process

### 1. Pin the pack and the shared gauntlet
Record the pack head (`git rev-parse HEAD`, clean tree), the contested slot, and the two seats by name (the incumbent skill, the challenger skill). Freeze the case-set: same case ids for both runs. **Done when** you can state the slot, both skills, and a case-set whose ids a stranger could re-run.

### 2. Run both through the identical harness
Run the incumbent across every case, then the challenger across the *same* cases, same blind critic, same seat, same round cap. Score each case 0–1 tied to its defect. Write one row per case to `duel/<slot>/incumbent.tsv` and `duel/<slot>/challenger.tsv` (`<case-id>\t<score>`). Do not tune either skill mid-duel — that is `skill-tune`'s solo loop, a different island; here the skills are frozen and only compete.

### 3. Let the script decide the swap
[scripts/duel-verdict.sh](scripts/duel-verdict.sh) takes the two result files, **rejects the duel unless the case-id sets are identical** (proving one gauntlet), computes each mean, and applies strict-beat with tie-to-incumbent. The decision is in code so no one can narrate a tie into a win.

```bash
./scripts/duel-verdict.sh duel/<slot>/incumbent.tsv duel/<slot>/challenger.tsv
```

### 4. Return the verdict — seats, scores, head-bound
Issue **swap** or **no-swap**, carrying non-negotiably: the pack head (full SHA); both seats named; both means and the strict-beat margin; the shared case-set id list (the check that could have failed); and a **void-on-move notice** — the verdict binds this head and this case-set, and voids the moment either changes. A re-scored or edited case-set is a new duel, never a re-bind. **Done when** a reader who trusts none of it can re-run the cases and recompute the swap from the two `.tsv` files alone.

## Enforced vs advisory
The **strict-beat gate and the identical-gauntlet check are enforced** — `duel-verdict.sh` exits non-zero on mismatched case ids and prints `NO-SWAP` on any tie or loss; the `.tsv` files are the evidence. *Which* cases model the defects, and whether the critic is truly blind, are **advisory** judgement — say which; never imply the script certifies case quality. An unrun case is not a scored case: never launder a missing row into a win.

## Where this plugs in
- `gauntlet-loop` supplies the executor cases and the defect-tied blind critic both contestants share; `cross-family-review` supplies the independent critic seat and the head-binding discipline.
- A survived verdict enters `finding-register` at the pack head — the swap or the successful defense is a finding, enumerated at a SHA.
- The 50-slot cap is `archipelago`'s band cap applied to the pack; this island is how a full pack still evolves without churning.
- `skill-tune` is the solo counterpart — improve one skill against its own score *before* it enters a duel; the duel never tunes, it only compares frozen contestants.

**No authority without evidence. The incumbent holds the seat until a challenger strictly beats it on cases both could have lost.**
