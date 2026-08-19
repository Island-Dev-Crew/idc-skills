---
name: ai-humanizer
description: Detect and SCORE AI-writing tells in prose — a bundled statistical + pattern scorer that emits a deterministic 0-100 AI-likeness number, so a de-slop pass yields byte-verifiable BEFORE/AFTER evidence (the score dropped) instead of a claim. Use when reviewing text for AI slop, gating an edit that must sound human, proving a rewrite actually reduced the tells, or when the user says "score this for AI", "how AI does this read", "de-slop", "humanize check", or "does my rewrite still sound like a bot". Differentiator - the only island that MEASURES slop with a failable check; prose-craft authors prose, short compresses, wait-what re-pitches — none score.
---

# AI Humanizer: measure the slop, don't claim you removed it

Every other writing island *produces* text. This one *judges* it: a bundled scorer reads prose and returns a **0-100 AI-likeness score**, where higher means more machine-extruded. The number is the point. "I made it sound human" is a claim; a score that fell from 67 to 6 is evidence from a check that could have failed. Model-agnostic: the tells (buzzword vocabulary, uniform sentence rhythm, chatbot residue, inflated significance) are shared across model families, so no vendor or model name is hardcoded.

The scorer is `scripts/score.js`: pure Node, no dependencies, no network, deterministic (same bytes in → same number out). It blends three signals: **pattern density** (24 detectors over a tiered slop vocabulary and phrase set), **category breadth** (how many kinds of tell are present), and **statistical uniformity** (burstiness, sentence-length variation, type-token ratio, trigram repetition; humans write in bursts, machines are metronomic).

## The loop: score, de-slop, re-score

Nothing here rewrites for you. It gates a rewrite you (or another island) performed, on evidence:

```bash
node scripts/score.js draft.md            # → a single number, e.g. 67
node scripts/score.js --json draft.md     # → full breakdown: findings, stats, sub-scores
```

1. **Score the draft.** Capture the BEFORE number.
2. **De-slop it.** The de-slop tools are [`prose-craft`](../prose-craft/SKILL.md) (author) and [`short`](../short/SKILL.md) (compress), but both are **user-invoked**, so you cannot fire them yourself; tell the human to invoke whichever fits, or edit by hand. That work is out of scope here; this island only measures.
3. **Re-score and prove the drop** with the bundled gate:

```bash
./scripts/delta.sh before.md after.md     # prints before/after/delta; exit 1 if AFTER >= BEFORE
```

`delta.sh` is the **red-capable** check: it exits non-zero when the rewrite did not lower the measured tells, so "de-slopped" can never launder into `verified` on a claim alone. The BEFORE/AFTER pair plus the exit code is the evidence packet.

## What the score is, and isn't

- **A signal, not a verdict on quality.** A low score means *fewer measured AI tells*, not "good writing"; sterile human prose also scores low. Read it as one gauge, `advisory` by default.
- **`enforced` only where you wire it.** The number blocks nothing until you put `delta.sh` in a pre-commit hook or CI step and honor its exit code. State which you did; never imply the gate is running when it is only available.
- **Thresholds are conventions, not law.** Roughly: <20 mostly human, 20-45 lightly touched, 45-70 moderately AI, 70+ heavily AI. Pick a ceiling for your context and say so; don't present the band as if the tool decreed it.
- **Short text is noisy.** Uniformity signals need ≥20 words and ≥3 sentences or they are withheld; a one-line snippet scores on patterns alone.

## Reading `--json` when a number isn't enough

`findings[]` lists each tripped detector by `id`, `category`, `weight`, and `matchCount`, so you can see *why* a draft scored high (a wall of Tier-1 vocabulary reads differently from three chatbot sign-offs) and aim the de-slop pass. `stats` exposes the raw stylometry (`burstiness`, `sentenceLengthVariation`, `typeTokenRatio`, `trigramRepetition`) for when the tell is rhythm, not words. `patternScore` and `uniformityScore` are the two blended components behind the composite.

## The vocabulary is a source of truth, not a style opinion

The detectors and word tiers are vendored into `score.js` from the public Wikipedia:Signs-of-AI-writing corpus and stylometric research (Copyleaks arXiv:2503.01659, StyloAI). Editing them changes the score, so treat the list as calibrated data: if you retune it, re-run the BEFORE/AFTER pair on a known slop/human sample and confirm the gap survives: a scorer that no longer separates the two samples is broken, and a broken scorer's "PASS" is worth nothing.

## Ship checklist for a de-slop claim

- [ ] BEFORE score captured on the original draft
- [ ] AFTER score captured on the rewrite, same scorer, same bytes
- [ ] `delta.sh` run; its exit code honored (0 = proven drop, 1 = no drop)
- [ ] score reported as `advisory`, or the hook/CI wiring that makes it `enforced` named explicitly
- [ ] any vocabulary retune re-validated against a slop/human sample

**No authority without evidence. A dropped score is proof; "I humanized it" is a claim.**
