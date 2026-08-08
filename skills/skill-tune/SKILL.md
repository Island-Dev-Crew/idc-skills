---
name: skill-tune
description: Empirically improve a skill or markdown context file against a measured score — an edit survives only on a measured gain, reverted otherwise. Use when a skill underperforms, a CLAUDE.md or context file needs tightening, or the user mentions "skill-opt", "optimize this skill", "tune this markdown", "make this prompt better", or "auto-research loop for skills". Differentiator - no-authority-without-evidence applied to skills; the gain is measured, never asserted, and a tuned file is usually a shorter file.
---

# Skill Tune — keep the edit only if the score moved

The empirical counterpart to [`idc-skill-authoring`](../idc-skill-authoring/SKILL.md): authoring is how you *write* a skill; tuning is how you *improve* one against evidence. It fuses Microsoft's **SkillOpt** and Andrej Karpathy's **auto-research** loops with the forge's law — an edit is kept **only when a measured score rises**, which is the archipelago's band-cap discipline applied to a markdown file. You cannot tune your way to "better" by conviction; you can only evidence your way there.

The one finding that anchors the whole method: **the most efficient context files are small — roughly 500–800 tokens — and it is better to split a big one than to pad it.** Separating thought is what lets the model work; a tuned file is usually a *shorter* file.

## The loop

```
build an eval set → run the skill → judge each output → edit → re-run → keep iff score rose
```

### 1. Build a red-capable eval set

You cannot tune without a score that can go down. Assemble 5–20 representative tasks the skill should handle — the ones it fails on today are the most valuable. If fewer than 5 tasks genuinely fail, keep the set small rather than padding it — but retain a handful of currently-passing tasks in the measured set as regression guards, so a kept edit must hold them green. Each task has an input and a checkable expectation. A tuning run with no failing case is like a [`diagnose`](../diagnose/SKILL.md) loop that never goes red: it proves nothing. Record the tasks in `tune/<skill>/tasks.md`.

For subjective targets (tone, warmth, aesthetics) write the expectation as an observable proxy — required/banned phrases, structural markers, lead-with-the-fact ordering — and note in `tasks.md` that the proxy is the measured thing, not the quality itself; spot-check one kept iteration against the real quality before declaring the tune done.

**Done when** you have tasks the *current* skill measurably fails or under-serves, with a stated expectation per task.

### 2. Baseline

Run the current skill across every task and **judge each output** — ideally with a different model family via [`cross-family-review`](../cross-family-review/SKILL.md), so the judge is not the author. If no second model family is reachable, self-judge against a rubric written *before* seeing the outputs, and say so in the note (`judge: self`) — a downgrade, never silence. Score each 0–1 (or against a rubric); record the baseline in `tune/<skill>/results.tsv`. Each iteration is a git commit; `sha` is that commit's real SHA (the pin `cross-family-review` needs), not a placeholder:

```
# results.tsv — one row per run
iter   sha       tokens   pass   mean_score   note
0      a1b2c3d   1240     6/12   0.58         baseline
```

Record **token count** too — a tune that raises the score but doubles the tokens is a trade, not a win; name it. The count that bites is the *per-load context* — the `SKILL.md` top plus whatever a task actually pulls in — not the byte total of the whole disclosed tree; that is why splitting detail behind a pointer can hold the score while tokens fall.

### 3. Edit — toward smaller

Make one focused change and re-run. The edits that pay, in order:

- **Prune no-ops** (per [`writing-for-agents`](../writing-for-agents/SKILL.md)): delete any sentence the model already obeys by default. This is where most of the gain and most of the shrink live — prevention, not compression: the gain is in what the step no longer loads, not in tighter wording of what stays.
- **Split** an over-800-token file into a lean `SKILL.md` plus a pointer to disclosed reference — the model attends better to a short top.
- **Sharpen a leading word** that is too weak to beat the default.
- **Collapse restatements** into one token.

One change per iteration, so the score delta is attributable. Exception: if baseline analysis turns up several independent defects at once, bundle them into one rewrite iteration — log it `note: bundle: N changes` so the delta is marked unattributable — and if the score then drops, ablate (revert one change at a time) rather than reverting wholesale. Return to single-change edits after that first rewrite.

### 4. Keep iff the score rose

Re-run the eval set, re-judge, append a `results.tsv` row. **Keep the edit only if `mean_score` rose without `tokens` growing more than 20% (or `mean_score` held while `tokens` fell).** A rise paired with token growth past 20% only counts as kept if the note logs the trade-off (`note: trade-off — tokens +NN%, justified because …`); unjustified growth reverts like a score drop. If the score dropped outright, revert — the file reads better to you, but the evidence says it performs worse, and the evidence wins. Loop until the score plateaus or the file is as small as it can be while holding the score.

Any tasks you lean on for regression checking must appear as scored rows in `results.tsv` (or as a regression column on the iteration row) — a spot-check kept out of the log leaves no evidence, so a regression on it could not revert an edit.

Enforced-vs-advisory: the **score-must-rise gate is the enforced part** — `results.tsv` is the evidence, and an edit that didn't raise the score does not stay. For an over-cap trade-off, the enforced check is only that the logged trade-off note *exists*; whether the justification is *adequate* is advisory judgement, ideally reviewed by the cross-family judge when one is in use. *Which* edit to attempt (§3) is advisory judgement too. Say which; never imply the loop enforces good taste.

**Done when** the final `results.tsv` shows a run whose score beats the baseline (or matches it at fewer tokens), every kept edit is backed by a row where the score did not fall, and the reverted edits are visible in the log so the next tuner does not retry them. Before shipping, a person reads the final kept diff — the score guards performance, not meaning or safety, and an edit that raised the proxy can still be wrong on something the proxy never measured. The evidence decides which edits stay; the human still owns whether the tuned file ships.

## What this is not

Not a way to make a skill *sound* better — that is the hollow-output failure Jake names, where polished steps rest on nothing. Substance comes from the eval set, not the prose. Not a one-shot: the value is the loop. And not a replacement for authoring — tune a skill that already does one thing (per idc-skill-authoring); tuning cannot rescue a skill that bundles three concerns.

**No authority without evidence. The edit that raises the score stays; the one that only reads better goes.**
