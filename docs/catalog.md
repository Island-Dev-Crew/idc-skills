# Forge 50 catalog

This index is generated from [`skills/registry.json`](../skills/registry.json). The five outcome routes are editorial starting points—not popularity rankings, certifications, or an exhaustive taxonomy. Every skill remains independently addressable; successful execution is task-, dependency-, platform-, and harness-specific.

## Choose an outcome

### Build

Turn an idea into a scoped, testable implementation without confusing motion with progress.

**Start here:** [`job-to-be-done`](#job-to-be-done) · [`idc-skill-authoring`](#idc-skill-authoring) · [`prototype`](#prototype) · [`spec-pipeline`](#spec-pipeline) · [`gauntlet-loop`](#gauntlet-loop)

**Recommended loop:** `job-to-be-done → prototype → spec-pipeline → gauntlet-loop`

### Research

Replace plausible answers with sourced findings and context that survives the session.

**Start here:** [`grill`](#grill) · [`research`](#research) · [`video-analysis`](#video-analysis) · [`data-source-map`](#data-source-map) · [`productionize-opinion`](#productionize-opinion)

**Recommended loop:** `grill → research/video-analysis → data-source-map → productionize-opinion`

### Operate

Coordinate agents and recurring work without losing ownership or control-plane history.

**Start here:** [`console-as-code`](#console-as-code) · [`lane-claim`](#lane-claim) · [`worktree-fleet`](#worktree-fleet) · [`model-routing`](#model-routing) · [`agent-schedule`](#agent-schedule)

**Recommended loop:** `console-as-code → lane-claim → worktree-fleet/model-routing → agent-schedule`

### Verify & Ship

Turn “it works” into recomputable evidence, independent review, and exact-revision transport proof.

**Start here:** [`computer-use-smoke`](#computer-use-smoke) · [`evidence-packet`](#evidence-packet) · [`cross-family-review`](#cross-family-review) · [`self-contained-ship`](#self-contained-ship) · [`transport-complete`](#transport-complete)

**Recommended loop:** `computer-use-smoke → evidence-packet → cross-family-review → self-contained-ship → transport-complete`

### Architect

Shape repository, domain, and module boundaries so agents navigate an explicit system.

**Start here:** [`arch-survey`](#arch-survey) · [`deep-modules`](#deep-modules) · [`folder-workspace`](#folder-workspace) · [`workspace-scaffold`](#workspace-scaffold) · [`archipelago`](#archipelago)

**Recommended loop:** `arch-survey → deep-modules → folder-workspace/workspace-scaffold → archipelago`

## All fifty islands

Invocation values come from the registry. Provenance is reproduced as recorded; see [`provenance.json`](../provenance.json) and [`THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md) for source-level detail. The separate [validation record](report.html) includes historical evidence epochs and a named residual for each island; it is not a blanket current certification.

<a id="idc-skill-authoring"></a>

### 01. [idc-skill-authoring](../skills/idc-skill-authoring/SKILL.md)

The skill layer of the canon — folder anatomy, progressive disclosure, invocation and router skills, the Codex openai.yaml sidecar, fleet distribution, and the evidence discipline. Points to writing-for-agents for the universal levers.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Ondrej effective-agent-skills + Pocock writing-great-skills (v1.2 refactor) + IDC fleet distribution

<a id="writing-for-agents"></a>

### 02. [writing-for-agents](../skills/writing-for-agents/SKILL.md)

The universal levers for any document an agent reads — context pointers, the two loads, information hierarchy, completion criteria, leading words, pruning, and failure modes. Fires when editing AGENTS.md / CLAUDE.md / rules files.

- **Invocation:** `model`
- **Recorded lineage:** NEW v1.2 — Pocock writing-for-agents; the universal source of truth the canon points to

<a id="cross-family-review"></a>

### 03. [cross-family-review](../skills/cross-family-review/SKILL.md)

The crown ceremony: an independent reviewer from a different model family reviews a diff at an exact head along Standards and Spec axes and returns a named-seat verdict that voids on move. The author never reviews their own work.

- **Invocation:** `model`
- **Recorded lineage:** CROWN — fusion: Ondrej fable/gpt-review + Pocock code-review two-axis + Garnet review ceremony

<a id="worktree-fleet"></a>

### 04. [worktree-fleet](../skills/worktree-fleet/SKILL.md)

Git worktrees for same-machine parallel agents, with the IDC boundary: adopted for drafts, forbidden for evidence. Worktree artifacts are inadmissible as gate evidence until re-derived from a fresh clone.

- **Invocation:** `user`
- **Recorded lineage:** fusion: Ondrej git-worktree + IDC §02 admissibility boundary

<a id="grill"></a>

### 05. [grill](../skills/grill/SKILL.md)

Relentless interview to reach shared understanding before building, in three modes (ambush, drill, batch), emitting settled decisions as ADRs. Facts are looked up; only decisions are asked.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Pocock grill-me/grilling/batch-grill-me (v1.2 rounds + emoji scan) + Ondrej prompt-me + IDC ADR emission

<a id="wayfinder"></a>

### 06. [wayfinder](../skills/wayfinder/SKILL.md)

Plan a chunk of work too big for one agent session — chart it as a shared map of decision tickets on the issue tracker, then resolve them one at a time until the way to the destination is clear. Plans across sessions by resolving decisions, not slices of a build.

- **Invocation:** `user`
- **Recorded lineage:** earned add — Pocock wayfinder (multi-session decision-ticket planning)

<a id="agent-guardrails"></a>

### 07. [agent-guardrails](../skills/agent-guardrails/SKILL.md)

Four mechanical layers under an AI fleet — shell denylist, git block, pre-commit gate, read-only data role — mechanizing the covenants beneath the prompts.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Ondrej global-agent-guardrails + Pocock git-guardrails/setup-pre-commit + read-only db role

<a id="handoff"></a>

### 08. [handoff](../skills/handoff/SKILL.md)

Compact a session into a state-based handoff a fresh agent resumes from with zero memory, plus the wake protocol the receiver runs — re-reading verdicts and register state from the tree before trusting the summary.

- **Invocation:** `user`
- **Recorded lineage:** fusion: Ondrej handoff + Pocock handoff/claude-handoff + IDC wake protocol

<a id="lane-claim"></a>

### 09. [lane-claim](../skills/lane-claim/SKILL.md)

Declare-and-halt coordination for agents working one repo across many machines: claim a lane before touching it, halt if already claimed, release when done. Cures the cross-machine collisions worktrees cannot.

- **Invocation:** `model`
- **Recorded lineage:** IDC-ONLY — Garnet boot step 6 (declare-and-halt fleet coordination)

<a id="transport-complete"></a>

### 10. [transport-complete](../skills/transport-complete/SKILL.md)

Ship a change and babysit it until verifiably live — commit, push, watch CI, confirm the deploy promoted the exact SHA, prove production serves it. Done means a health check for the exact SHA, not a successful push.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Ondrej prod-push + IDC transport covenant

<a id="spec-pipeline"></a>

### 11. [spec-pipeline](../skills/spec-pipeline/SKILL.md)

One pipeline from a discussed feature to shipped code: spec (synthesis) then tracer-bullet tickets with blocking edges, implement at pre-agreed seams with TDD, then an optional persistent goal loop.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Pocock to-spec/to-tickets/implement + Ondrej goal-loop as persistent runner

<a id="prototype"></a>

### 12. [prototype](../skills/prototype/SKILL.md)

Build a throwaway prototype to answer one design question — a single shareable HTML file for a logic/state question, or several switchable UI variants for a look question — then capture the answer and discard the code.

- **Invocation:** `model`
- **Recorded lineage:** earned add — Pocock prototype v1.2 (the prototype is a primary source)

<a id="research"></a>

### 13. [research](../skills/research/SKILL.md)

Investigate a question against high-trust primary sources and capture findings as a cited Markdown file — every claim sourced or explicitly flagged unverified. DeepAPI is an optional backend.

- **Invocation:** `model`
- **Recorded lineage:** fusion: Ondrej deep-research/research-prompt + Pocock research (primary-source discipline)

<a id="finding-register"></a>

### 14. [finding-register](../skills/finding-register/SKILL.md)

A durable register of findings each enumerated at an exact SHA (not a running count), provenance-marked in both directions, and given a collision-free id swept before allocation.

- **Invocation:** `model`
- **Recorded lineage:** IDC-ONLY — the U-series discipline

<a id="deep-modules"></a>

### 15. [deep-modules](../skills/deep-modules/SKILL.md)

Shared vocabulary and enforcement for deep modules — a lot of behaviour behind a small interface at a clean seam — with the dependency-cruiser rules that make entry points the only way in.

- **Invocation:** `model`
- **Recorded lineage:** Pocock codebase-design + setup-ts-deep-modules, adapted

<a id="domain-modeling"></a>

### 16. [domain-modeling](../skills/domain-modeling/SKILL.md)

Actively build and sharpen a project's domain model — challenge terms, invent edge-case scenarios, and write the glossary and term-derived decisions down when they crystallise. The active discipline that changes the model, distinct from reading CONTEXT.md.

- **Invocation:** `model`
- **Recorded lineage:** earned add — Pocock domain-modeling (ubiquitous language, glossary, ADRs)

<a id="diagnose"></a>

### 17. [diagnose](../skills/diagnose/SKILL.md)

A disciplined loop for hard bugs: build a tight red-capable feedback loop first, reproduce and minimise, hypothesise, instrument, fix with a regression test, post-mortem. Performance is judged by operation counts, not wall-clock.

- **Invocation:** `model`
- **Recorded lineage:** Pocock diagnosing-bugs + IDC operation-counts law

<a id="archipelago"></a>

### 18. [archipelago](../skills/archipelago/SKILL.md)

The full-cycle, evidence-gated build protocol — typed contracts at every seam, gates that must be able to fail, loopback routing, a tamper-evident ledger, and band caps you cannot talk your way past.

- **Invocation:** `model`
- **Recorded lineage:** Jon's existing protocol (Navigata1/archipelago), reviewed against the canon

<a id="domain-wire"></a>

### 19. [domain-wire](../skills/domain-wire/SKILL.md)

Wire a domain the IDC way — the three-lane model (story / product / AI-native), one canonical per venture with siblings 308-redirecting to it, automatic graduation when a brand deed exists, and canonicals moving in the same commit.

- **Invocation:** `model`
- **Recorded lineage:** IDC-NATIVE — the IDC domain doctrine (three-lane model, graduation, governance rules)

<a id="console-as-code"></a>

### 20. [console-as-code](../skills/console-as-code/SKILL.md)

Assemble an agent's operating prompt from versioned in-repo blocks (BOOT, covenants, lanes, seats), stamped with the assembly SHA, so every prompt is an auditable artifact and the same console assembles identically on every seat.

- **Invocation:** `model`
- **Recorded lineage:** IDC-NATIVE — named in the Garnet×Buzz synthesis as the first IDC-skills candidate to graduate into Garnet ops

<a id="evidence-packet"></a>

### 21. [evidence-packet](../skills/evidence-packet/SKILL.md)

Assemble a byte-verifiable evidence packet — the diff, the verification-ladder commands, and their captured outputs — so a reviewer recomputes every claim instead of trusting the author. A weak and a frontier author are equally mergeable when both can run the ladder.

- **Invocation:** `model`
- **Recorded lineage:** IDC-NATIVE — the Contributor-Road artifact from the Two Roads synthesis

<a id="job-to-be-done"></a>

### 22. [job-to-be-done](../skills/job-to-be-done/SKILL.md)

The pre-build triage that asks whether a thing should be built or automated at all, and where the human stays in the loop — delegation/complexity/outcome, the 90/10 rule. Its best outcome is often 'don't build it'.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE — Jake Van Clief (job-to-be-done, 90/10, augment-don't-automate)

<a id="folder-workspace"></a>

### 23. [folder-workspace](../skills/folder-workspace/SKILL.md)

Structure a repo as an ICM workspace — folders and markdown as agent architecture, routed by a three-layer map (map/rooms/workspace) so one agent becomes the agent each task needs, without agent swarms. The map is an auditable routing contract.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE flagship — Jake Van Clief's Interpretable Context Methodology, welded to the evidence discipline

<a id="workspace-scaffold"></a>

### 24. [workspace-scaffold](../skills/workspace-scaffold/SKILL.md)

Scaffold a new ICM workspace for a domain — generate the root map, the rooms, the naming conventions — then prove a fresh agent routes through it before declaring done.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE — the workspace-creator generator (ships scaffold.sh)

<a id="data-source-map"></a>

### 25. [data-source-map](../skills/data-source-map/SKILL.md)

Wire an external data source into a workspace with a markdown descriptor — describe where a SQL/BigQuery/Drive/Oracle store lives, what it holds, and what to ask it, so an agent queries it on demand instead of ingesting it into a vector store. The descriptor is a map to live data, not a copy.

- **Invocation:** `model`
- **Recorded lineage:** earned add — Jake Van Clief's OKF (Open Knowledge Format), welded to the evidence discipline

<a id="productionize-opinion"></a>

### 26. [productionize-opinion](../skills/productionize-opinion/SKILL.md)

Distill an operator's own raw material — transcripts, notes, decisions, chat history — into durable workspace context that carries their voice and process. Mines you, not external sources; inferences are marked as inferences.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE — Jake Van Clief's core thesis (productionize your opinion / the ingest agent)

<a id="skill-tune"></a>

### 27. [skill-tune](../skills/skill-tune/SKILL.md)

Empirically improve a skill or context file — run it on representative tasks, judge each output, edit, re-run, and keep an edit only when a measured score rises. The most efficient files are small (500-800 tokens); a tuned file is usually a shorter file.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE — Microsoft SkillOpt + Karpathy auto-research, welded to the band-cap law

<a id="workspace-audit"></a>

### 28. [workspace-audit](../skills/workspace-audit/SKILL.md)

Audit an ICM workspace for drift — check every path the map claims exists in the tree, and that no live room is missing from the map. The map is a claim; the tree is the evidence; drift is a claim the evidence contradicts.

- **Invocation:** `model`
- **Recorded lineage:** ICM-NATIVE — the verify side of folder-workspace (drift detection, ships audit.sh)

<a id="wizard"></a>

### 29. [wizard](../skills/wizard/SKILL.md)

Generate an interactive bash wizard that walks a human through steps only they can perform — opening each URL, saying what to click, capturing values, and writing them into .env files and GitHub Actions secrets. Ships a fixed template.sh UX library.

- **Invocation:** `model`
- **Recorded lineage:** NEW v1.2 — Pocock wizard (bundled template.sh library)

<a id="to-questionnaire"></a>

### 30. [to-questionnaire](../skills/to-questionnaire/SKILL.md)

Turn a decision you can't answer alone into a Markdown questionnaire for the one person who can — filled in async or worked through together. Grills you about the send (who it goes to, what you need back), not the subject.

- **Invocation:** `user`
- **Recorded lineage:** NEW v1.2 — Pocock to-questionnaire (the inverse of grill)

<a id="wait-what"></a>

### 31. [wait-what](../skills/wait-what/SKILL.md)

Stop — that last message did not land. Re-pitch it with the missing context, in ASD-STE100 Simplified Technical English, grounded in the project's own CONTEXT.md ubiquitous language.

- **Invocation:** `user`
- **Recorded lineage:** NEW v1.2 — Pocock wait-what, grounded in the forge CONTEXT.md ubiquitous language

<a id="short"></a>

### 32. [short](../skills/short/SKILL.md)

Compress the current answer — strip filler, simplify wording, cut length while keeping substance.

- **Invocation:** `user`
- **Recorded lineage:** adopt: Ondrej short

<a id="teach"></a>

### 33. [teach](../skills/teach/SKILL.md)

A stateful multi-session teaching workspace — mission-grounded lessons from high-trust sources, delivered as beautiful self-contained HTML with tight feedback loops and learning records.

- **Invocation:** `user`
- **Recorded lineage:** adopt/dedupe: Pocock teach (attributed)

<a id="gauntlet-loop"></a>

### 34. [gauntlet-loop](../skills/gauntlet-loop/SKILL.md)

Convert any task into a fan-out of builder sub-agents each shadowed by a blind critic, looped against a falsifiable bar. The lightweight cousin of archipelago — wow-grade prototypes fast; graduate to archipelago when the bar must be a real gate. Ships build-prompt.sh, the deterministic task-to-prompt converter.

- **Invocation:** `user`
- **Recorded lineage:** fusion: Matt Schumer's gauntlet loop (attributed) + Anthropic evaluator-optimizer + IDC falsifiable-bar & no-cold-start

<a id="video-analysis"></a>

### 35. [video-analysis](../skills/video-analysis/SKILL.md)

Turn a video URL into a grounded analysis from two channels — the transcript (what was said) and frames sampled at a chosen cadence (what was shown); every claim cited to a transcript line or a frame number. Ships grab.sh.

- **Invocation:** `model`
- **Recorded lineage:** IDC-native: the transcript+frames media-analysis methodology (yt-dlp + ffmpeg)

<a id="arch-survey"></a>

### 36. [arch-survey](../skills/arch-survey/SKILL.md)

Proactively survey a whole codebase for architectural refactor opportunities — mine change-history hot-spots, gate each through the deep-module deletion test, and rank them as a before/after report. The discovery scan that runs before deep-modules designs one chosen module.

- **Invocation:** `model`
- **Recorded lineage:** adapt: Pocock improve-codebase-architecture — proactive churn+deletion-test survey to a ranked report

<a id="merge-resolve"></a>

### 37. [merge-resolve](../skills/merge-resolve/SKILL.md)

Resolve an in-progress git merge or rebase by tracing every conflicting hunk to the intent that authored it (commit/PR/issue), keeping both intents where they compose and recording the trade-off where they collide, never aborting, and running the project checks before finishing.

- **Invocation:** `model`
- **Recorded lineage:** adapt: Pocock resolving-merge-conflicts — trace-to-intent, never-abort, checks gate

<a id="issue-triage"></a>

### 38. [issue-triage](../skills/issue-triage/SKILL.md)

Move a queue of issues you did NOT create (bug reports, incoming requests, external PRs) through a triage state machine, grill for missing info, and emit durable agent-ready briefs — every AI note carrying an honesty disclaimer. The inbound on-ramp job-to-be-done and grill don't cover.

- **Invocation:** `model`
- **Recorded lineage:** adapt: Pocock triage — inbound-queue state machine + agent-ready briefs + honesty disclaimer

<a id="agent-schedule"></a>

### 39. [agent-schedule](../skills/agent-schedule/SKILL.md)

Schedule an unattended agent on a recurring wall-clock (cron/systemd/heartbeat/while-sleep vs a built-in scheduler), then verify the schedule actually fired before trusting it. The only island triggered by time; every loop sibling is condition-driven.

- **Invocation:** `model`
- **Recorded lineage:** adapt: Ondrej agent-self-scheduling — wall-clock triggers + fire-verification, vendor-stripped

<a id="prose-craft"></a>

### 40. [prose-craft](../skills/prose-craft/SKILL.md)

Author original prose (article, essay, explainer) in two phases: EXPLORE mines fragments and coins the load-bearing leading word; EXPLOIT builds grounded beats where no beat leans on an ungrounded concept, optionally shaping each block's form. Distinct from short/wait-what/teach/writing-for-agents.

- **Invocation:** `user`
- **Recorded lineage:** fusion: Pocock writing-fragments + writing-beats + writing-shape — explore then exploit, grounding discipline

<a id="delegated-authority-prompt"></a>

### 41. [delegated-authority-prompt](../skills/delegated-authority-prompt/SKILL.md)

Compose a minimum-question, maximum-authority delegation prompt in five slots (objective + definition of done, context pack, decision rights, stop conditions, evidence contract) so a delegated agent runs far without check-ins, made safe by the tripwires that bound it. The mirror of grill: grill front-loads the questions, this front-loads the answers.

- **Invocation:** `user`
- **Recorded lineage:** ICM-NATIVE — the deliberate inverse of grill: front-load the answers as context + decision rights, granting an agent authority bounded by explicit stop conditions

<a id="model-routing"></a>

### 42. [model-routing](../skills/model-routing/SKILL.md)

Route one task to the cheapest model or tool that still clears its cognitive-demand floor (vision-native / deep-reasoning / cheap-bulk), and record why the pick clears the bar. The only island that selects the model a step runs on.

- **Invocation:** `model`
- **Recorded lineage:** design-video derived (Kimi/Claude model-selection practice) — cognitive-demand vs cost-floor routing

<a id="batch-sample-curate"></a>

### 43. [batch-sample-curate](../skills/batch-sample-curate/SKILL.md)

Draw N candidates from a probabilistic-output tool (image/video/design/copy) and curate to the best against a scored keep/cut ledger, recording why each was kept or cut. Distinct from gauntlet-loop (refine one to a bar) and prototype.

- **Invocation:** `user`
- **Recorded lineage:** design-video derived (probabilistic-generator sampling economics)

<a id="self-contained-ship"></a>

### 44. [self-contained-ship](../skills/self-contained-ship/SKILL.md)

Prove a deliverable phones home to nobody before it ships — a static egress scanner (schemes wss/ws/ftp + fetch/WebSocket/XHR/EventSource/import/@import/url/src/href, per-hit bounded egress-ok waiver) paired with a sealed offline load asserting zero outbound. The containment gate; transport-complete proves liveness, not containment.

- **Invocation:** `model`
- **Recorded lineage:** earned add — the containment leaf of the ship cluster (validated high-value; first script failed the gauntlet at 7 on egress-detection holes, authored correct here)

<a id="computer-use-smoke"></a>

### 45. [computer-use-smoke](../skills/computer-use-smoke/SKILL.md)

Drive a real UI through a scripted smoke path and assert observable outcomes (Playwright/browser-use/computer-use) — the runtime primitive that produces the band-4 evidence archipelago demands but nothing else makes. A verdict is an assertion; a screenshot is triage.

- **Invocation:** `model`
- **Recorded lineage:** sweep-find (NBB-canonical) — behavioral UI runtime evidence, backend-abstracted

<a id="skill-supply-chain-review"></a>

### 46. [skill-supply-chain-review](../skills/skill-supply-chain-review/SKILL.md)

Audit a third-party agent skill before adopting it — provenance, hidden/implicit invocation, dangerous instructions, prompt-injection surface, unresolved pointers — and emit a trust verdict bound to a pinned version. No authority without evidence, applied to the supply chain.

- **Invocation:** `model`
- **Recorded lineage:** sweep-find (NBB-canonical) — third-party skill adoption gate

<a id="ai-humanizer"></a>

### 47. [ai-humanizer](../skills/ai-humanizer/SKILL.md)

Detect and SCORE AI-writing tells in prose — a bundled statistical + pattern scorer emitting a deterministic 0-100 AI-likeness number — so a de-slop pass yields byte-verifiable before/after evidence (the score dropped), not a claim. The prose cluster's failing check.

- **Invocation:** `model`
- **Recorded lineage:** sweep-find (clawd) — AI-slop detector/scorer with a bundled analyzer

<a id="exposure-audit"></a>

### 48. [exposure-audit](../skills/exposure-audit/SKILL.md)

Read-only exposure audit of any target machine or repo against a NAMED advisory (CVE/breach/malicious-package/supply-chain) — enumerate what is installed and reachable, decide affected-or-not on captured evidence, write a structured report. Read-only; never remediate.

- **Invocation:** `model`
- **Recorded lineage:** adapt: David Ondrej cyber-audit, de-personalized — read-only exposure audit

<a id="skill-duel"></a>

### 49. [skill-duel](../skills/skill-duel/SKILL.md)

Run an incumbent skill against a challenger through ONE identical gauntlet (same executor cases, same defect-tied critic, same seat) and return a swap/no-swap verdict welded to the scores — a challenger displaces only by strictly beating the incumbent; a tie keeps the seat. The mechanical governor of the capped pack.

- **Invocation:** `user`
- **Recorded lineage:** IDC-native — the 50-cap displacement governor

<a id="connected-fix-prompt"></a>

### 50. [connected-fix-prompt](../skills/connected-fix-prompt/SKILL.md)

Compose ONE dependency-ordered refinement prompt from a set of findings — rank N interdependent defects root-cause-before-symptom and by impact, each carrying recomputable evidence, so a fixer clears them in a single correct-order pass instead of thrashing. The composer between finding-register and the fixer.

- **Invocation:** `user`
- **Recorded lineage:** design-video derived — findings to a dependency-ordered fix mandate

---

Generated by `python3 -B scripts/render_catalog.py`. Edit the registry or the renderer, then regenerate; do not hand-edit this file.
