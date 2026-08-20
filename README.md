# IDC Skills · The Forge

**An archipelago of agent skills.** Each skill is an island; the repo is the navigable chain that connects them. Fused from David Ondrej's and Matt Pocock's public canons (through Pocock v1.2) and Jake Van Clief's Interpretable Context Methodology, welded to the discipline Island Development Crew earned shipping agent-built software: **no authority without evidence — the skills demonstrate their own discipline.**

> *"In the multitude of counsellors there is safety."* — Proverbs 11:14

This is the **staging forge** (`Navigata1/idc-skills-forge`) with registry candidate and integrity protocol `2.0.3`; that version string is not a shipped, public-ready, or tagged claim. Skills are validated here by live fleet use, then the golden fusion is promoted to `Island-Dev-Crew` as official, each carrying its validation record. A skill is proven by lanes running it, not by its author's confidence.

**Cross-harness by contract, not assumption:** the canonical source is preserved once, while each harness gets a documented loader path, metadata profile, and evidence tier. The current matrix covers fifteen surfaces, including Codex, Claude Code, claude.ai, Cursor, VS Code, Amp, Kimi, Antigravity, OpenClaw, Grok, Buzz, Pi, and Hermes. A shared folder proves byte distribution; it does not by itself prove invocation semantics. See the [human-readable matrix](docs/harness-support.md) and its [machine-readable contract](docs/harness-support.json).

---

## The chain — fifty islands, in build order

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
| 35 | [`video-analysis`](skills/video-analysis/SKILL.md) | 💠 IDC-native | Two channels — the transcript (what was said) + frames (what was shown); every claim cited to a line or a frame. |
| 36 | [`arch-survey`](skills/arch-survey/SKILL.md) | adapt · earned | Proactively survey a codebase for refactor opportunities — churn hot-spots + the deletion test, ranked. |
| 37 | [`merge-resolve`](skills/merge-resolve/SKILL.md) | adapt · earned | Resolve a merge/rebase by tracing each hunk to its intent; keep both, record the trade-off, never abort. |
| 38 | [`issue-triage`](skills/issue-triage/SKILL.md) | adapt · earned | Move an inbound queue of issues you didn't create through a triage state machine to agent-ready briefs. |
| 39 | [`agent-schedule`](skills/agent-schedule/SKILL.md) | adapt · earned | Run an unattended agent on a wall-clock — and verify it actually fired before trusting it. |
| 40 | [`prose-craft`](skills/prose-craft/SKILL.md) | fusion · earned | Author original prose in two phases — explore fragments and coin the leading word, then build grounded beats. |
| 41 | [`model-routing`](skills/model-routing/SKILL.md) | ⛰ earned | Route a task to the cheapest model that clears its cognitive-demand floor — the only island that picks the model a step runs on. |
| 42 | [`delegated-authority-prompt`](skills/delegated-authority-prompt/SKILL.md) | ⛰ earned | The inverse of grill — front-load the answers and grant decision rights, bounded by stop-condition tripwires. |
| 43 | [`batch-sample-curate`](skills/batch-sample-curate/SKILL.md) | ⛰ earned | Draw N candidates from a stochastic generator and curate to the best on a scored keep/cut ledger. |
| 44 | [`self-contained-ship`](skills/self-contained-ship/SKILL.md) | ⛰ earned | Prove an artifact ships with zero external requests — every asset inlined, a sealed-load runtime rung that phones home to nobody. |
| 45 | [`computer-use-smoke`](skills/computer-use-smoke/SKILL.md) | ⛰ earned | Drive a real UI through a smoke path and assert outcomes — the band-4 runtime evidence archipelago demands. |
| 46 | [`skill-supply-chain-review`](skills/skill-supply-chain-review/SKILL.md) | ⛰ earned | Audit a third-party skill before you adopt it — the adoption gate a fusion-built forge needs. |
| 47 | [`ai-humanizer`](skills/ai-humanizer/SKILL.md) | ⛰ earned | Detect and score AI-writing tells (0-100) with a bundled scorer — a de-slop pass with byte-verifiable before/after. |
| 48 | [`exposure-audit`](skills/exposure-audit/SKILL.md) | adapt · earned | Read-only exposure audit of a machine or repo against a named CVE/advisory → a structured report. |
| 49 | [`skill-duel`](skills/skill-duel/SKILL.md) | 💠 IDC-native | Run an incumbent vs a challenger on identical gauntlet cases — swap only on a strict win. The 50-cap governor. |
| 50 | [`connected-fix-prompt`](skills/connected-fix-prompt/SKILL.md) | fusion · earned | Compose N findings into one dependency-ordered fix mandate — root before symptom, single correct-order pass. |

## The ICM cluster — folder as workspace

Islands 22–28 fuse Jake Van Clief's **Interpretable Context Methodology** — folders and markdown as agent architecture, not agent swarms — with the forge's evidence discipline. ICM and the forge reached the same thesis from opposite directions: *the repo is the memory.* ICM got there from folder/context architecture; the archipelago from evidence/review. The cluster spans one loop — **triage** (should we build it?) → **architect** (`folder-workspace`) → **scaffold** (generate it) → **wire** (`data-source-map` — external data via a descriptor) → **capture** (`productionize-opinion`) → **tune** (empirically improve the markdown) → **audit** (does the map still match the tree?). The weld throughout: the map is an *auditable routing contract*, a `skill-tune` edit survives only on a measured gain, and a distilled opinion is marked distilled-vs-verified. `folder-workspace` is layer 0 — the ground every other island routes within.

## The moat, stated plainly

Twelve islands are IDC's own. **Five exist nowhere else** — the IDC-origin islands: [`lane-claim`](skills/lane-claim/SKILL.md) and [`finding-register`](skills/finding-register/SKILL.md) (💠 IDC-only), plus [`domain-wire`](skills/domain-wire/SKILL.md), [`console-as-code`](skills/console-as-code/SKILL.md), [`evidence-packet`](skills/evidence-packet/SKILL.md) (💠 IDC-native). **Seven more ship nowhere else *in this welded form*** — the ICM cluster (six from 1.3.0 plus [`data-source-map`](skills/data-source-map/SKILL.md), the external-data leaf earned in 1.3.1 — seven in all): [`job-to-be-done`](skills/job-to-be-done/SKILL.md), [`folder-workspace`](skills/folder-workspace/SKILL.md), [`workspace-scaffold`](skills/workspace-scaffold/SKILL.md), [`data-source-map`](skills/data-source-map/SKILL.md), [`productionize-opinion`](skills/productionize-opinion/SKILL.md), [`skill-tune`](skills/skill-tune/SKILL.md), [`workspace-audit`](skills/workspace-audit/SKILL.md) — where Jake Van Clief's public methodology is fused with the forge's evidence law so the map is an auditable contract, not a convenience. Add the review-ceremony layer inside the otherwise-fused [`cross-family-review`](skills/cross-family-review/SKILL.md). Anyone can fuse public repos. Only IDC ships the review ceremony with receipts, the doctrine that wires a 73-deed estate, and ICM welded to *no authority without evidence*. **That is the product.**

## Design palette

The archipelago wears the Iron Canvas palette — OLED `#0a0a0f`, garnet · rust · gold · jade · steel — with a faceted-gem motif. The landing experience is a journey across the chain, not a file listing: see [`docs/index.html`](docs/index.html), the full seven-act tour in [`docs/walkthrough.html`](docs/walkthrough.html), and [`docs/report.html`](docs/report.html) — now generated from machine-readable records for all 50 registry islands. Reacceptance fails unless the registry, source records, embedded records, visible cards, and aggregate report bytes are the deterministic expected output. Repo-as-artifact, matching the thesis.

## Install

The dependency-free Python installer works from PowerShell, Command Prompt, and POSIX shells. The 2.0.3 protocol routes it through an independently installed freshness launcher; the repository's own verifier can prove signed content, but it cannot prove that its whole tree was not rolled back. Targets remain explicit so the external write set is visible before execution:

```text
python scripts/validate_skills.py
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh --repo-root /absolute/idc-skills --config /trusted/etc/idc-skills-freshness.json verify
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh --repo-root /absolute/idc-skills --config /trusted/etc/idc-skills-freshness.json install -- --target agents --json
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh --repo-root /absolute/idc-skills --config /trusted/etc/idc-skills-freshness.json install -- --target agents --verify-only --json
```

The launcher source is tracked at [`bootstrap/idc_verify_fresh.py`](bootstrap/idc_verify_fresh.py), but that in-tree copy is deliberately non-authoritative and refuses to run from a checkout. The reviewed bytes must be installed outside the repository with an external canonical configuration, signed live release index, exact first-run index digest, protected checkpoint, and an external clean-environment process wrapper; candidate-controlled `scripts/install.sh` cannot bootstrap trust. Only this launcher emits `readyToRun=true`; `scripts/skill_integrity.py` emits the narrower `contentReady`. See the [full deployment, schema, threat boundary, and release ceremony](integrity/README.md).

The native fleet aliases are `agents=~/.agents/skills`, `claude=~/.claude/skills` when that directory exists, `pi=~/.pi/agent/skills` when it exists, and the legacy Hermes topology `hermes=~/.hermes/skills`. Use `--custom-target name=path` only after the [support contract](docs/harness-support.md) establishes that the receiving harness loads that path. Native installs preserve canonical bytes and POSIX executable modes, preflight every selected destination, replace one skill directory atomically, and verify exact signed manifests after freshness passes. Both Claude.ai export modes stage selected skills against the authenticated per-file map and build ZIPs only from that verified snapshot. A whole multi-target run is not rollback-atomic after an unexpected I/O failure.

claude.ai is a compatibility export, not a native install. The current profile fails closed because 48 canonical descriptions exceed the documented 200-character upload limit and thirteen user-only skills have no documented explicit-only equivalent. The historical supplied snapshot can still be reproduced without changing the canonical tree, but nesting extension keys under `metadata` preserves values only—not invocation behavior:

```text
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh --repo-root /absolute/idc-skills --config /trusted/etc/idc-skills-freshness.json export-claude-ai-snapshot -- --output .exports/claude-ai --json
```

The five-check content gate binds every byte of all 50 skill trees, the registry and security controls, every discovered external reference and network-command occurrence, and reviewed fetch/execute exceptions to a detached OpenSSH signature from the stable 1Password-held Forge key. The separate index signature uses a domain-separated namespace and binds release sequence, raw manifest digest, verifier digest, launcher digest, and final Git commit. Neither result is a sandbox or a full execution trace.

Run the external launcher's `reaccept` command for the full fifty-island validator, signed content check, installer, deterministic export, 50-record registry/report gate, and no-source-drift gate. Current direct installer, hook, and reacceptance routes reject an absent syntactic handoff marker, but that marker is forgeable defense-in-depth, not launcher authentication; only the independently pinned launcher is an authoritative entrypoint. `scripts/install.sh` delegates only when `IDC_SKILLS_FRESHNESS_PYTHON`, `IDC_SKILLS_FRESHNESS_LAUNCHER`, and `IDC_SKILLS_FRESHNESS_CONFIG` name the externally pinned runtime, launcher, and policy. Repository-owned CI tests content and the launcher attack fixtures; whole-tree CI readiness still requires an organization-controlled required check outside candidate code. See [`skills/idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) §5 for authoring guidance.

## Provenance

The fusion recipe is `IDC-SKILLS-FUSION-REPORT-v1`. The immutable archive hashes, exact David Ondrej and Matt Pocock source commits, live comparison heads, per-island lineage pointer, and the one honestly unresolved historical ICM commit are recorded in [`provenance.json`](provenance.json). Required upstream MIT notices are preserved in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md). Release **1.5.0** added six earned islands after a full re-review of the David-Ondrej and Matt-Pocock source canons; release **1.4.0** added `gauntlet-loop`; release **1.3.1** added `data-source-map`, `prototype`, `wayfinder`, and `domain-modeling`; release **1.3.0** added the ICM-native cluster; release **1.2.0** folded in Matt Pocock's v1.2 writing and productivity material plus IDC-native islands. The Garnet ceremony layer is IDC-authored; this repository does not independently certify the external operational history that informed it.

## Pipeline — staging to official

1. **Author** under the `idc-skill-authoring` canon.
2. **Stage** here in `Navigata1/idc-skills-forge`.
3. **Vet in live fleet use** — evidence of use, not declaration of quality.
4. **Promote** the validated golden fusion to `Island-Dev-Crew`, each island carrying its validation record.

## License

MIT — see [LICENSE](LICENSE) and [third-party notices](THIRD-PARTY-NOTICES.md).

— **Island Development Crew** · Huntsville, AL · *No authority without evidence.* · Roll Tide 💎
