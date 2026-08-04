# Verdict format + smell baseline

Loaded by `cross-family-review` at step 2 (smell baseline) and step 4 (verdict template). One level deep from `SKILL.md`.

## The verdict template

Emit exactly this shape. It survived three review rounds in production untouched — the report-back discipline the fleet (and Buzz) consumes mirrors it.

```
# VERDICT — <short title of the work>
Reviewed head:  <full 40-char SHA>          # binds this verdict; void the moment HEAD moves
Base:           <base ref> (<its SHA>)
Author seat:    <e.g. OpenAI Codex>          # the seat that wrote the diff — never the reviewer
Reviewer seat:  <e.g. Claude Fable 5>        # a DIFFERENT model family, fresh clone
Disposition:    approve | changes-requested | blocked

## Standards
<the Standards subagent's report, verbatim or lightly cleaned>
Worst finding (Standards): <one line, or "none">

## Spec
<the Spec subagent's report, verbatim — or "no spec available">
Worst finding (Spec): <one line, or "none">

## Recompute
Diff:  git diff <base>...HEAD
Log:   git log <base>..HEAD --oneline
Anyone who trusts none of the above can recompute every finding from these two commands.

VOID-ON-MOVE: this verdict binds <SHA>. It is void — not stale, void — the instant HEAD moves.
```

Rules that bind the format:
- **No single winner across axes.** Report the worst finding *within each axis*. Picking one overall "worst" is the reranking the two-axis separation exists to prevent.
- **Provenance both directions.** If the author seat is wrong, the verdict says so; if the reviewer is wrong, a later verdict corrects the reviewer by name. The record has done both.
- **A blocked or changes-requested disposition routes to the author seat**, never the reviewer, and the re-review binds the new head.

## The smell baseline (Fowler, *Refactoring* ch.3)

Paste this into the Standards subagent in full — it is the fixed floor when a repo documents nothing. Each is a labelled heuristic ("possible Feature Envy"), never a hard violation. A documented repo standard overrides any of them; skip anything tooling already enforces.

- **Mysterious Name** — a name that doesn't reveal what it does/holds. → rename; if no honest name comes, the design is murky.
- **Duplicated Code** — the same logic shape in more than one hunk/file. → extract the shape, call it from both.
- **Feature Envy** — a method reaching into another object's data more than its own. → move it onto the data it envies.
- **Data Clumps** — the same few fields/params keep travelling together. → bundle them into one type.
- **Primitive Obsession** — a primitive standing in for a domain concept. → give the concept its own small type.
- **Repeated Switches** — the same switch/if-cascade on one type recurs. → polymorphism, or one shared map.
- **Shotgun Surgery** — one logical change forces scattered edits. → gather what changes together into one module.
- **Divergent Change** — one module edited for several unrelated reasons. → split so each changes for one reason.
- **Speculative Generality** — abstraction/params/hooks for needs the spec doesn't have. → delete; inline until a real need shows.
- **Message Chains** — long `a.b().c().d()` navigation. → hide the walk behind one method on the first object.
- **Middle Man** — a class/function that mostly just delegates. → cut it, call the real target.
- **Refused Bequest** — a subclass ignoring most of what it inherits. → drop inheritance, use composition.
