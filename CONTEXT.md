# CONTEXT — the archipelago substrate

The shared file the islands read and write to coordinate without explicit handoffs. This is the repo-level substrate `idc-skill-authoring` §10 calls for: a coordinated set of skills forming a loop (align → spec → build → verify → ship → compound), not an unrelated catalog.

## The one law

**No authority without evidence.** A claim is not done until a captured piece of evidence — from a check that could have failed — proves it. State enforced-vs-advisory explicitly; never imply it. Mark unverified work `unverified`; never launder it into `verified`.

## Named seats

The fleet names its seats by model family, always: `OpenAI Codex`, `Claude Fable 5`, `Jon Isaac`. Provenance is marked in both directions and corrected against either seat when either is wrong. `cross-family-review`, `finding-register`, and `lane-claim` all depend on this.

## How the islands compose

- **align** — `grill` reaches shared understanding, emits ADRs.
- **build** — `spec-pipeline` (spec → tickets → implement) writes code; `deep-modules` shapes it; `worktree-fleet` parallelizes it on one machine; `lane-claim` coordinates it across machines.
- **verify** — `cross-family-review` issues a head-bound verdict from a different family; `diagnose` produces the red-capable checks; survivors land in `finding-register`.
- **ship** — `transport-complete` proves the exact SHA live.
- **compound** — `archipelago` gates the whole cycle; `handoff` carries state to the next session with a wake protocol.
- **under all of it** — `agent-guardrails` makes misbehaviour mechanically impossible.

## Interfaces between islands (the artifact shapes)

- A **verdict** binds a full SHA, names author + reviewer seats, and voids on move. Shape: `cross-family-review/references/verdict-format.md`.
- A **finding-register entry** is `U-<n>` + head + a recomputable `command`. Enumerated at a SHA, never a running count.
- A **lane claim** answers who / where / from-what-head / since-when, in `ops/lanes/<lane>.claim.json`.
- A **handoff** is state-not-instructions, saved to the OS temp dir, and its receiver runs the wake protocol.

## Staging status

Staging repo: `Navigata1/idc-skills-forge` (public). Promotion target: `Island-Dev-Crew`. A skill graduates when live lanes have run it — evidence of use, not the author's confidence.
