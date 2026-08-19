---
name: gauntlet-loop
description: Convert any task into a fan-out of builder sub-agents, each shadowed by a blind critic, driven against a falsifiable bar until the work clears it — the lightweight warp-drive for pushing an MVP to a high standard (games, 3D worlds, front-ends, any build). Use when the user says "gauntlet loop", "gauntlet-loop", "fan out sub-agents to build X", "loop until it's wowed", or wants to convert a task into a generator-critic fleet. Differentiator - the bar is falsifiable not vibes, the critic is blind and independent (a cross-family-review seat), and it refuses to start cold — bring a brief or it optimizes toward the wrong thing.
disable-model-invocation: true
argument-hint: "What task should the gauntlet loop build or polish?"
---

# Gauntlet Loop: fan out builders, shadow each with a blind critic, loop against a falsifiable bar

The loop that oneshots hyper-custom builds: a task, a fleet of builder sub-agents each shadowed by a **blind critic**, and a **bar** the fleet loops against until the work clears it. It is the generator↔evaluator pattern (Anthropic's *Building Effective Agents*) taken to fleet scale, coined "the gauntlet loop" by Matt Schumer. IDC adopts it with two hard edits: the bar must be **falsifiable**, and the loop **refuses to start cold**.

> The one rule: you can't wow your way past the bar. The critic must be able to fail you on captured evidence.

## The three parts: the whole pattern

Every gauntlet-loop prompt is exactly three slots. Convert any task by filling them:

1. **Task**: what to build, in one line ("an explorable 3D walkthrough of this apartment"; "a first-person-shooter level").
2. **Build method**: *fan out sub-agents; each builds one smallest piece; each is shadowed by a separate **blind critic** that checks the piece against the bar and can send it back.* Blind means the critic scores the artifact, never the builder's self-report.
3. **Bar to hit**: the standard the fleet loops against until met. "Utterly wowed vs. Call of Duty" is the vibe version; the IDC version pins it to something **that can fail**: a reference peg to match, a metric to clear, a checklist every critic must pass, captured as evidence (a screenshot diff, a test log), not asserted.

[scripts/build-prompt.sh](scripts/build-prompt.sh) emits a ready-to-paste prompt from a one-line task, so "convert any task into a gauntlet loop" is one command.

## Don't start cold: the most important rule

A gauntlet loop **optimizes toward whatever direction it is given.** Point it at a blank page and it will polish, at great cost, the wrong thing: a beautiful site that is off-brief, a game that is not the game you wanted.

- **Bring a brief or an MVP first.** A reference peg, a design system, a v1 to sharpen. The loop is a **warp-drive for V2**, not a V1 generator. If the brief does not exist yet, get it first; that is what `grill` is for (a user-invoked island; you run it, no agent fires it for you).
- The bar is only as honest as the brief. A vague bar ("make it great") makes the critic decorative; a falsifiable bar ("match these four reference photos; every critic marks all four ≥ pass") makes it real.

## Running it: two harnesses

- **Fleet harness (sub-agent orchestration in Claude Code, this environment):** run it as an actual fan-out: parallel builders, each paired with a blind critic, looping until the bar. `cross-family-review` is the blind-critic seat done right (independent family, fresh clone); `worktree-fleet` isolates parallel builders so they do not overwrite each other. Set a **round cap and a token budget up front**, because loops burn hours and tokens, and an uncapped loop against an unreachable bar never returns. State the caps as `enforced` only where the harness actually stops on them; otherwise they are `advisory` and you are the stop.
- **Plain chat harness:** paste the three-part prompt from the script. It instructs the main agent to fan out and self-critique. Same pattern, no tooling.

## Games and 3D worlds: where it shines, and where it stops

Strongest on **hyper-custom visual builds** (games, 3D walkthroughs, front-ends) because the critic can be *visual*: screenshot the build, diff it against a reference peg, fail it until they converge. That is the Pokémon starting area, the racing sim, the apartment walkthrough.

Be honest about the edge: **a browser oneshot is a prototype, not a shipped product.** A gauntlet-loop game is a playable HTML/WebGL artifact; porting it to a real store or platform (packaging, input, performance budgets, store review, licensing) is a separate productionization effort (see `productionize-opinion` and `transport-complete`). The loop gets you a wow-grade prototype fast; it does not get you a store listing. Say that to the user; never let the demo imply the store.

## Graduating to archipelago

The gauntlet loop is the **lightweight** cousin of `archipelago`. When the bar is a real definition-of-done you would defend to a stranger (typed contracts, a ledger, loopback routing, a governance verdict), graduate: run the build under `archipelago` and let the gauntlet loop be one phase's build method. Gauntlet loop for wow; archipelago for proof. Say which one you are running, so no one mistakes a wowed prototype for a passed gate.

## Credit

"The gauntlet loop" was coined by [Matt Schumer](https://x.com/mattshumer_) and popularized in walkthrough form by Jay of the RobaNuggets community. The generator↔evaluator core is Anthropic's evaluator-optimizer from [Building Effective Agents](https://www.anthropic.com/research/building-effective-agents) (2024). Adopted into the IDC archipelago with attribution, per the supersede-and-preserve covenant: the additions here are the falsifiable bar and the no-cold-start rule.

**No authority without evidence. You can't wow your way past a bar the critic can't fail you on.**
