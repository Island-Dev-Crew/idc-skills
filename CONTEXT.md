# CONTEXT — the archipelago substrate

The shared file the islands read and write to coordinate without explicit handoffs. This is the repo-level substrate `idc-skill-authoring` §10 calls for: a coordinated set of skills forming a loop (align → spec → build → verify → ship → compound), not an unrelated catalog.

## The one law

**No authority without evidence.** A claim is not done until a captured piece of evidence — from a check that could have failed — proves it. State enforced-vs-advisory explicitly; never imply it. Mark unverified work `unverified`; never launder it into `verified`.

## Named seats

The fleet names its seats by model family, always: `OpenAI Codex`, `Claude Fable 5`, `Jon Isaac`. Provenance is marked in both directions and corrected against either seat when either is wrong. `cross-family-review`, `finding-register`, and `lane-claim` all depend on this.

## How the islands compose

- **architect (layer 0)** — `folder-workspace` is the ICM substrate the whole loop routes within (folders as architecture, the three-layer map); `workspace-scaffold` generates it and proves the routing; `data-source-map` wires external data (SQL/BigQuery/Drive) into it via a descriptor; `productionize-opinion` fills the rooms with the operator's voice; `workspace-audit` checks the map still matches the tree.
- **triage** — `job-to-be-done` asks whether a thing should be built or automated at all, before grill/spec-pipeline spend effort on it.
- **plan** — `wayfinder` charts a foggy effort too big for one session as a map of decision tickets, dispatching to grill/research/prototype/domain-modeling ticket by ticket.
- **author** — `writing-for-agents` holds the universal levers for any agent doc; `idc-skill-authoring` adds the skill layer (anatomy, invocation, Codex sidecar, fleet distribution); `skill-tune` improves a skill empirically, keeping an edit only on a measured gain.
- **align** — `grill` reaches shared understanding, emits ADRs; `domain-modeling` sharpens the ubiquitous language into the glossary; `to-questionnaire` mines a decision out of someone who isn't you; `wait-what` re-grounds an answer that stopped making sense.
- **build** — `spec-pipeline` (spec → tickets → implement) writes code; `prototype` answers a design question with throwaway code first; `deep-modules` shapes it; `worktree-fleet` parallelizes it on one machine; `lane-claim` coordinates it across machines; `wizard` drives the human through the clicks an agent can't.
- **verify** — `cross-family-review` issues a head-bound verdict from a different family; `diagnose` produces the red-capable checks; `evidence-packet` bundles them so a reviewer recomputes instead of trusting; survivors land in `finding-register`.
- **ship** — `transport-complete` proves the exact SHA live; `domain-wire` connects the deed the doctrine's way.
- **compound** — `archipelago` gates the whole cycle; `handoff` carries state to the next session with a wake protocol; `console-as-code` keeps the operating prompt itself an auditable, SHA-stamped artifact.
- **under all of it** — `agent-guardrails` makes misbehaviour mechanically impossible.

## Interfaces between islands (the artifact shapes)

- A **verdict** binds a full SHA, names author + reviewer seats, and voids on move. Shape: `cross-family-review/references/verdict-format.md`.
- A **finding-register entry** is `U-<n>` + head + a recomputable `command`. Enumerated at a SHA, never a running count.
- A **lane claim** answers who / where / from-what-head / since-when, in `ops/lanes/<lane>.claim.json`.
- A **handoff** is state-not-instructions, saved to the OS temp dir, and its receiver runs the wake protocol.

## Staging status

Staging repo: `Navigata1/idc-skills-forge` (public). Promotion target: `Island-Dev-Crew`. A skill graduates when live lanes have run it — evidence of use, not the author's confidence.
