# IDC Skills · The Forge

**An archipelago of agent skills.** Each skill is an island; the repo is the navigable chain that connects them. Fused from David Ondrej's and Matt Pocock's public canons (through Pocock v1.2) and Jake Van Clief's Interpretable Context Methodology, welded to the discipline Island Development Crew earned shipping agent-built software: **no authority without evidence — the skills demonstrate their own discipline.**

> *"In the multitude of counsellors there is safety."* — Proverbs 11:14

This is the **staging forge** (`Navigata1/idc-skills-forge`, release 1.4.0). Skills are validated here by live fleet use, then the golden fusion is promoted to `Island-Dev-Crew` as official, each carrying its validation record. A skill is proven by lanes running it, not by its author's confidence.

**Dual-harness:** every island ships an `agents/openai.yaml` sidecar, so the set works in Claude Code, Pi, Hermes **and** Codex from one source. User-invoked islands carry `policy.allow_implicit_invocation: false` — the Codex analog of `disable-model-invocation`.

---

## The chain — thirty-four islands, in build order

The order is the bootstrap: island 1 authors the rest and rests on island 2 (the universal levers); the crown ships with a week of receipts; the ICM cluster (22–28) is the workspace architecture the whole chain routes within; twelve islands are IDC's own.

| # | Island | Kind | What it does |
|---|--------|------|--------------|
| 1 | [`idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) | canon | Authors every island — skill anatomy, invocation, the Codex sidecar, fleet distribution, evidence discipline. |
| 2 | [`writing-for-agents`](skills/writing-for-agents/SKILL.md) | fusion · v1.2 | The universal levers for any agent doc — pointers, the two loads, hierarchy, leading words, pruning. The canon points here. |
| 3 | [`cross-family-review`](skills/cross-family-review/SKILL.md) | 👑 crown | A different model family reviews a diff at an exact head; the verdict names its seats and voids on move. The author never reviews their own work. |
| 4 | [`worktree-fleet`](skills/worktree-fleet/SKILL.md) | fusion | Worktrees for same-machine parallelism — adopted for drafts, forbidden for evidence. The version that knows when *not* to use itself. |
| 5 | [`grill`](skills/grill/SKILL.md) | fusion · v1.2 | Relentless interview in three modes (ambush · drill · batch), rounds with emoji-scan, emitting decisions as ADRs. |
| 6 | [`wayfinder`](skills/wayfinder/SKILL.md) | adapt · earned | Plan work too big for one session as a map of decision tickets — resolve decisions one at a time until the way is clear. |
| 7 | [`agent-guardrails`](skills/agent-guardrails/SKILL.md) | fusion | Four mechanical layers — shell · git · commit · data — under the whole fleet. |
| 8 | [`handoff`](skills/handoff/SKILL.md) | fusion | State-based handoff + the wake protocol: re-read verdicts and register from the tree before trusting the summary. |
| 9 | [`lane-claim`](skills/lane-claim/SKILL.md) | 💠 IDC-only | Declare-and-halt coordination across machines — the collisions worktrees can't touch. |
| 10 | [`transport-complete`](skills/transport-complete/SKILL.md) | fusion | Pushed-and-verified-live or not done — a health check for the exact SHA. |
| 11 | [`spec-pipeline`](skills/spec-pipeline/SKILL.md) | fusion | Spec → tracer tickets → implement at seams → optional persistent goal loop. |
| 12 | [`prototype`](skills/prototype/SKILL.md) | adapt · earned | Throwaway code that answers one design question — a shareable HTML demo or switchable UI variants. The prototype is a primary source. |
| 13 | [`research`](skills/research/SKILL.md) | fusion | Primary-source investigation; every claim sourced or flagged unverified. |
| 14 | [`finding-register`](skills/finding-register/SKILL.md) | 💠 IDC-only | Findings enumerated at a SHA (not a count), provenance both ways, id swept before allocation. |
| 15 | [`deep-modules`](skills/deep-modules/SKILL.md) | adapt | The deep-module vocabulary + the boundary rules that make entry points the only way in. |
| 16 | [`domain-modeling`](skills/domain-modeling/SKILL.md) | adapt · earned | Actively sharpen the ubiquitous language — challenge terms, invent edge cases, write the glossary as it crystallises. |
| 17 | [`diagnose`](skills/diagnose/SKILL.md) | adapt | The loop before the theory; performance judged by operation counts, not wall-clock. |
| 18 | [`archipelago`](skills/archipelago/SKILL.md) | Jon's | The evidence-gated build protocol — gates that must be able to fail, band caps you can't talk past. |
| 19 | [`domain-wire`](skills/domain-wire/SKILL.md) | 💠 IDC-native | Wire a domain the IDC way — three-lane model, one canonical, siblings 308, graduation in the same commit. |
| 20 | [`console-as-code`](skills/console-as-code/SKILL.md) | 💠 IDC-native | Assemble the operating prompt from versioned, SHA-stamped in-repo blocks — the cure for prompt drift. |
| 21 | [`evidence-packet`](skills/evidence-packet/SKILL.md) | 💠 IDC-native | The byte-verifiable packet a reviewer recomputes — acceptance on evidence the author cannot fake. |
| 22 | [`job-to-be-done`](skills/job-to-be-done/SKILL.md) | 🧭 ICM-native | The pre-build triage — should this be built or automated at all? 90/10, augment don't just automate. |
| 23 | [`folder-workspace`](skills/folder-workspace/SKILL.md) | 🧭 ICM-native | Folders as agent architecture, routed by a three-layer map so one agent becomes the agent each task needs. Layer 0. |
| 24 | [`workspace-scaffold`](skills/workspace-scaffold/SKILL.md) | 🧭 ICM-native | Generate an ICM workspace from a brief — then prove a fresh agent routes through it. Ships `scaffold.sh`. |
| 25 | [`data-source-map`](skills/data-source-map/SKILL.md) | 🧭 ICM-native | Wire an external data source (SQL, BigQuery, Drive) via a markdown descriptor — a map to live data, not a copy. Jake's OKF. |
| 26 | [`productionize-opinion`](skills/productionize-opinion/SKILL.md) | 🧭 ICM-native | Distill your transcripts and decisions into durable workspace context that carries your voice. Mines you, not the web. |
| 27 | [`skill-tune`](skills/skill-tune/SKILL.md) | 🧭 ICM-native | Empirically improve a skill — keep an edit only when a measured score rises. Band caps, for markdown. |
| 28 | [`workspace-audit`](skills/workspace-audit/SKILL.md) | 🧭 ICM-native | The map is a claim, the tree is the evidence — catch drift between them. Ships `audit.sh`. |
| 29 | [`wizard`](skills/wizard/SKILL.md) | fusion · v1.2 | Generate an interactive bash wizard for human-only steps — dashboards, credentials, CI secrets. Ships `template.sh`. |
| 30 | [`to-questionnaire`](skills/to-questionnaire/SKILL.md) | fusion · v1.2 | Turn a decision you can't answer alone into a questionnaire for the one person who can. The inverse of grill. |
| 31 | [`wait-what`](skills/wait-what/SKILL.md) | fusion · v1.2 | Re-pitch a message that didn't land — plain language, grounded in the project's own words. |
| 32 | [`short`](skills/short/SKILL.md) | adopt | Compress the current answer. |
| 33 | [`teach`](skills/teach/SKILL.md) | adopt | A stateful multi-session teaching workspace. |
| 34 | [`gauntlet-loop`](skills/gauntlet-loop/SKILL.md) | fusion · earned | Convert any task into a fan-out of builders + blind critics against a falsifiable bar. The lightweight cousin of archipelago. |

## The ICM cluster — folder as workspace

Islands 22–28 fuse Jake Van Clief's **Interpretable Context Methodology** — folders and markdown as agent architecture, not agent swarms — with the forge's evidence discipline. ICM and the forge reached the same thesis from opposite directions: *the repo is the memory.* ICM got there from folder/context architecture; the archipelago from evidence/review. The cluster spans one loop — **triage** (should we build it?) → **architect** (`folder-workspace`) → **scaffold** (generate it) → **wire** (`data-source-map` — external data via a descriptor) → **capture** (`productionize-opinion`) → **tune** (empirically improve the markdown) → **audit** (does the map still match the tree?). The weld throughout: the map is an *auditable routing contract*, a `skill-tune` edit survives only on a measured gain, and a distilled opinion is marked distilled-vs-verified. `folder-workspace` is layer 0 — the ground every other island routes within.

## The moat, stated plainly

Twelve islands are IDC's own. **Five exist nowhere else** — the IDC-origin islands: [`lane-claim`](skills/lane-claim/SKILL.md) and [`finding-register`](skills/finding-register/SKILL.md) (💠 IDC-only), plus [`domain-wire`](skills/domain-wire/SKILL.md), [`console-as-code`](skills/console-as-code/SKILL.md), [`evidence-packet`](skills/evidence-packet/SKILL.md) (💠 IDC-native). **Seven more ship nowhere else *in this welded form*** — the ICM cluster (six from 1.3.0 plus [`data-source-map`](skills/data-source-map/SKILL.md), the external-data leaf earned in 1.3.1 — seven in all): [`job-to-be-done`](skills/job-to-be-done/SKILL.md), [`folder-workspace`](skills/folder-workspace/SKILL.md), [`workspace-scaffold`](skills/workspace-scaffold/SKILL.md), [`data-source-map`](skills/data-source-map/SKILL.md), [`productionize-opinion`](skills/productionize-opinion/SKILL.md), [`skill-tune`](skills/skill-tune/SKILL.md), [`workspace-audit`](skills/workspace-audit/SKILL.md) — where Jake Van Clief's public methodology is fused with the forge's evidence law so the map is an auditable contract, not a convenience. Add the review-ceremony layer inside the otherwise-fused [`cross-family-review`](skills/cross-family-review/SKILL.md). Anyone can fuse public repos. Only IDC ships the review ceremony with receipts, the doctrine that wires a 73-deed estate, and ICM welded to *no authority without evidence*. **That is the product.**

## Design palette

The archipelago wears the Iron Canvas palette — OLED `#0a0a0f`, garnet · rust · gold · jade · steel — with a faceted-gem motif. The landing experience is a journey across the chain, not a file listing: see [`docs/index.html`](docs/index.html). Repo-as-artifact, matching the thesis.

## Install

```bash
# distribute every island across the four fleet skill folders (Codex/Claude/Pi/Hermes)
./scripts/install.sh
```

`install.sh` copies each island to the canonical `~/.agents/skills/` (Claude and Pi are symlinks, auto-covered), copies to Hermes, verifies byte counts match across all four, and validates every `SKILL.md` frontmatter. See [`skills/idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) §8 for the layout and traps.

## Provenance & the pending inputs

The fusion recipe is `IDC-SKILLS-FUSION-REPORT-v1`. Release **1.4.0** adds one earned island — `gauntlet-loop` (Matt Schumer's fan-out-with-blind-critic technique, attributed, with the IDC edits: a *falsifiable* bar and a no-cold-start rule) — after all 33 prior islands cleared confidence ≥9 under a defect-tied vet and the pack was promoted to `Island-Dev-Crew`. Release **1.3.1** adds four earned islands — `data-source-map` (Jake's OKF, the ICM external-data leaf), `prototype`, `wayfinder`, and `domain-modeling` — chosen because they fill genuine gaps, not to hit a count; growth stops when a cut stops earning its place. Release **1.3.0** adds the six ICM-native islands, fusing Jake Van Clief's Interpretable Context Methodology (folder-as-workspace, the three-layer routing map, become-the-agent, model-agnostic, survives-updates) — grounded in his own talks and cross-checked against the public ICM community templates — with the forge's evidence discipline. Release **1.2.0** folds in Matt Pocock's skills v1.2 — `writing-for-agents` (the universal levers the canon now points to), the `wizard` + `to-questionnaire` + `wait-what` productivity islands, the fixed grill rounds, and the Codex `agents/openai.yaml` sidecars — plus three IDC-native islands drawn from IDC's own work: `domain-wire` (the domain doctrine), `console-as-code` (named in the Garnet×Buzz synthesis as the first candidate to graduate into Garnet ops), and `evidence-packet` (the Contributor-Road artifact). Two companion inputs — the Buzz conversations and the owner transcripts — arrived empty at the original authoring time; nothing here was reconstructed from them, and no claim in these skills represents Buzz's analysis or the owners' commentary. The Garnet ceremony layer rests on IDC's own verified production record.

## Pipeline — staging to official

1. **Author** under the `idc-skill-authoring` canon.
2. **Stage** here in `Navigata1/idc-skills-forge`.
3. **Vet in live fleet use** — evidence of use, not declaration of quality.
4. **Promote** the validated golden fusion to `Island-Dev-Crew`, each island carrying its validation record.

## License

MIT — see [LICENSE](LICENSE).

— **Island Development Crew** · Huntsville, AL · *No authority without evidence.* · Roll Tide 💎
