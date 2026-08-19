# HANDOFF: IDC Skills Forge — THE 50 LOCK (release 2.0.0)
Generated: 2026-08-09T00:00:00Z · Focus: 50/50 evidence-gated agent islands, locked and live

> ⏱ **SNAPSHOT AS OF release 2.0.0 (`c4202cf`, 2026-08-09).** Point-in-time handoff; the repo has since advanced. As of 2026-08-19 both remotes and local are at **`2bc8879`** (PR #1 — cross-harness installer/validator + multi-OS reacceptance), and the working tree carries an unrelated untracked `.claude/`. Any commit/state line below is historical — verify the live head with `git rev-parse HEAD` before trusting it.

State, not instructions. Everything below is ground truth to verify against the tree — not a task list. A fresh agent with zero memory of this build resumes from here after running the wake protocol at the end.

## 1. Goal

A capped archipelago of the world's best agent skills, where every island demonstrates its own discipline and nothing crosses a gate on claims alone. The pack is a **living deadlock at exactly 50 islands** — each one gauntleted to confidence ≥9 on a defect-tied rubric, and the count cannot grow except by a won head-to-head duel or a deprecated-slot fill at ≥9. The anchor law is in [`registry.json`](../skills/registry.json): *"No authority without evidence. The skills demonstrate their own discipline."*

## 2. Background

The forge is a **fusion**, not an invention. Its lineage:
- **David Ondrej** + **Matt Pocock** public skill canons (Ondrej `davidondrej-skills` 45 skills; Pocock `mattpocock-skills` v1.1.0 41 skills — source zips in `~/Downloads`, original fusion decisions in `~/Downloads/IDC-SKILLS-FUSION-REPORT-v1_1.html`).
- **Jake Van Clief's Interpretable Context Methodology (ICM)** — the canonical source is his repo `RinDig/icm-architect` (10 invariants + 5 principles + L0–L4 hierarchy + stage-contract + 5 forms + walk test + the ladder). The 7 ICM-cluster islands were infused from it.
- Welded throughout to **IDC evidence discipline** — the shared law in [`../CONTEXT.md`](../CONTEXT.md): no authority without evidence; state enforced-vs-advisory explicitly; never launder `unverified` into `verified`.
- Grown further from **4 world-class design videos** (9MbcgnkhxMA / 03IhVSEiICA / 0zlwXSVmoeg / KDkR0cJRiJk, analyzed at 250 deduped frames) and a **repo-wide sweep of Jon's own originals** (`~/clawd/skills`, `~/Desktop/NBB-workspace/NBB-canonical/.claude/skills`, `~/Documents/Crosswalk`).

Two hard constraints carried the whole build:
- **One concern per island; loops over menus; no duplication of meaning across islands; references one level deep.** (Repo law, [`CLAUDE.md`](../CLAUDE.md).) This is why several otherwise-good candidates were rejected — they duplicated an existing island's meaning.
- **Quality over count.** The cap is a ceiling a skill *earns* into, never a quota to fill. Jon expected maybe <40 would actually clear ≥9; the honest outcome was 50 that do.

## 3. Current State

**LOCKED — 50/50, release 2.0.0.** DONE:
- **50 islands** live under `skills/<name>/SKILL.md`, each gauntleted to confidence ≥9. `ls skills/` confirms 50 dirs (excluding `registry.json` + `README`). The build order and per-island provenance/summary/triggers are the authoritative index in [`registry.json`](../skills/registry.json) — do not re-enumerate them here; read that file.
- **Both repos at commit `c4202cf`** (`feat: THE 50 LOCK — release 2.0.0`). Public production: **`Island-Dev-Crew/idc-skills`**. Staging: **`Navigata1/idc-skills-forge`**. Local working tree: `/Users/IDC2.5/Desktop/IDC-skills` (clean, HEAD = c4202cf).
- **The moat is intact** (see §4). 6 IDC-native islands exist nowhere else + the 7-island ICM cluster welded to the evidence law + the cross-family-review ceremony with production receipts.
- **skill-duel is in force** as the displacement governor — the pack can now only change by its rules.
- **Docs shipped:** `docs/index.html`, `docs/report.html` (per-skill validation, two-lens framing), `docs/walkthrough.html` (reader's journey through the islands).

PARTIAL / NOT at target (the two honest misses — see §7):
- **YPE (youtube-pipeline)** — a PRODUCT, not a forge slot. Gauntleted in place, scored **5/10**, restored to Jon's clean v7.2 baseline.
- **iron-canvas** — a PRODUCT, not a forge slot. Climbed to **~8.5**, did not reach the 9.5 world-class bar.
- **docs/walkthrough.html world-class ENHANCED rebuild** — NOT started, deferred honestly (see §7).

## 4. Key Decisions

The reasoning behind the shape of the pack — the least-recoverable information here.

- **The cap history: 40 → then 50.** The ceiling started informally at "top ~40, never more." On 2026-08-08 it was raised to **50** deliberately. But 50 was never a quota — release 1.6.0 deliberately *landed at 40, not 50* ("quality over count"), and the final 6 (44→50) each had to pass a **value-check** (does it add real value the forge lacks?) on top of gauntlet ≥9. Rejections were routine: `self-contained-ship` first failed at **7** on a real egress-detection hole (a security gate that doesn't reliably fire is worse than none) and was only admitted after being re-authored correct; `google-safe-browsing`/`setup-help`/`loop-me`/`writing-shape` were all rejected as narrow or duplicative.

- **The two vetting lenses — do NOT conflate them.** (1) The **PROMOTION gate** uses a *defect-tied* rubric: **confidence = 10 − Σ real unaddressed in-scope defects**. This is the real bar; all 50 cleared ≥9 with zero unaddressed defects. (2) A separate **documentation pass** (33-agent fan-out) ran 3 fresh challenge cases per skill and scored *generically* — case performance ~8.7/10, but the generic "confidence" it emitted (~8–8.5) is **documenter caution, not new defects**. When a report shows a skill at "8.5," check which lens produced it before treating it as a defect.

- **The vetting method itself (dogfooded):** executor runs 3 live challenge cases in a sandbox → an **adversarial blind critic** scores by the defect-tied rubric. This is exactly what `gauntlet-loop` and `skill-duel` encode; the forge was vetted by the discipline it ships.

- **iron-canvas & YPE are PRODUCTS, not islands.** They are multi-concern pipelines. Putting them in the forge would violate the one-concern-per-island law. The forge keeps the tight, single-concern `video-analysis` primitive instead; the products are improved/gauntleted **in place in `~/clawd`**. This is a principled boundary, not an oversight.

- **The design-video sweep** produced 3 admitted islands (`delegated-authority-prompt` 10, `model-routing` 9, `batch-sample-curate` 9.5) — each had to be genuinely distinct from existing islands (delegated-authority-prompt is the deliberate *inverse* of grill; batch-sample-curate is distinct from gauntlet-loop and prototype).

- **skill-duel as the governor.** Once 50 is locked, the pack is a deadlock. A challenger displaces an incumbent **only by strictly winning** one identical gauntlet (same executor cases, same defect-tied critic, same seat); a tie keeps the seat. The only other way in is filling a *deprecated* slot at ≥9. This is Jon's answer to unbounded skill-sprawl: the cap has teeth because a mechanical island enforces it.

- **The moat (why this pack can't be trivially cloned):** 6 IDC-native islands exist nowhere else — `lane-claim`, `finding-register`, `domain-wire`, `console-as-code`, `evidence-packet`, `skill-duel` — plus the 7-island ICM cluster welded to the evidence law, plus the `cross-family-review` ceremony carrying real production receipts.

## 5. Traps & Dead Ends

What the next agent will be tempted to do wrong.

- **"Loop the gauntlet until every judge says 9" will NOT cleanly terminate.** Adversarial re-vetting is an **asymptote** — fresh executors invent new marginal edges every round. The honest close is "all real defects fixed + verified, confidence-metric ≥9," which is what was done and what Jon approved ("verify then promote"). Do not chase a mythical all-9 fixed point.

- **`archipelago`'s residual findings are NOT bugs in this repo.** They are bugs in the SEPARATE protocol repo **`Navigata1/archipelago`** (Python: `validate_contracts.py` sibling-fixture PASS, `loop.py` fromGate=G2 hardcode, close-phase not blocking open loopbacks). The `archipelago` *island* can only honestly DISCLOSE them in its Honest-boundaries section — it cannot fix them from here. A future task could fix that protocol repo to lift archipelago's live-case scores. Do not try to "fix archipelago" inside `IDC-skills`.

- **The ICM cluster came from Jake's real repo, `RinDig/icm-architect` — not from training-data reconstruction.** If you re-infuse or re-vet ICM islands, go back to that repo as the canonical source.

- **The browser pane blocks `file://` and `localhost`.** To show Jon an HTML deliverable (report/walkthrough/index), surface it via **SendUserFile**, not by navigating a browser pane to a local path.

- **Do NOT put YPE or iron-canvas into the forge** to "round out" a cluster. They are products by decision (§4). Improving them means editing them in `~/clawd`, in place.

- **YPE's root defect is subtle:** its Non-Negotiable Truth Rules are **prose, not enforced checks**. Section 0 asserts things like "preflight must block a sweep when the only runner is the curated-drop script / free disk < 15 GiB / below coverage minimum," but the actual EVS gates only verify a file *exists* or a numeric frame-count minimum — never the real condition. The fix is to turn each "must block when X" truth-rule into an actual check that verifies X. This is deliberate work across 1378 lines, not a 2-round patch.

## 6. Files & Pointers

- [`skills/registry.json`](../skills/registry.json) — **the authoritative index**: release 2.0.0, all 50 islands with `buildOrder`, `provenance`, `summary`, `triggers`, the `anchor` and `dualHarness` laws. Read this before assuming anything about which islands exist.
- [`CONTEXT.md`](../CONTEXT.md) — the shared ubiquitous language and the evidence law all islands share.
- [`CLAUDE.md`](../CLAUDE.md) — the repo's authoring law (one concern per island; no duplication; references one level deep).
- [`skills/idc-skill-authoring/SKILL.md`](../skills/idc-skill-authoring/SKILL.md) — the canon every island was built under. §5 was softened in-session (symlink-only fleet-topology claim was false; seats can be independent dirs, as they are on this machine — `install.sh` now detects per-seat topology).
- `skills/<name>/SKILL.md` (×50) + each island's `agents/openai.yaml` Codex sidecar (user-invoked islands carry `policy.allow_implicit_invocation: false`).
- `docs/index.html`, `docs/report.html` (per-skill validation report, honest two-lens framing), `docs/walkthrough.html` (reader's journey). Surface via SendUserFile, not a local-path browser nav.
- `scripts/install.sh` — fans every island across the four fleet skill folders (Codex/Claude/Pi/Hermes) and validates frontmatter; detects per-seat topology.
- **Products (NOT forge slots, kept in clawd):**
  - `~/clawd/ype-pipeline-skill/SKILL.md` — YPE youtube-pipeline v7.2 (restored clean baseline). Backups: `scratchpad/ype-v7.2-clean-baseline.md` and `scratchpad/ype-SKILL.backup.md`.
  - `~/clawd/skills/iron-canvas/SKILL.md` — iron-canvas-master v4.2. Backup: `scratchpad/iron-canvas-SKILL.backup.md`.
- **Full narrative record:** `/Users/IDC2.5/.claude/projects/-Users-IDC2-5-Desktop-IDC-skills/memory/idc-skills-forge.md` — the complete release-by-release history (1.2.0 → 2.0.0), the ~110 real defects found+fixed during promotion, and the push mechanics. This handoff summarizes it; that file is the primary source.
- **Improvement briefs** for the two honest misses live with each product (the YPE fix-path and the iron-canvas residual are described in the memory record and in each product's scratchpad backup).
- Session scratchpad backups: `/private/tmp/claude-502/-Users-IDC2-5-Desktop-IDC-skills/*/scratchpad/` (e.g. `connected-fix-prompt-8.5/` was the pre-finish staging of that island before it landed at 9.5).

## 7. Open Work

State + dependencies, not commands.

- **YPE is at 5/10, restored to clean v7.2.** Its consistency problem is unsolved. The fix-path is known (§5: convert prose truth-rules into real blocking checks). It is a product improvement in `~/clawd`, not a forge task. Clean baseline + partial-fix version both preserved in scratchpad.
- **iron-canvas is at ~8.5, not the 9.5 world-class bar.** The residual is deep illustrative-code robustness in a 2544-line monolith. Backup preserved. Product improvement in `~/clawd`.
- **docs/walkthrough.html enhanced rebuild is NOT started.** Target standard: the `flagship-report` enhanced-mode (references at `~/.agent-skills/idc-claude-skills/flagship-report/`: `references/enhanced-mode.md`, `enhanced-reference-architecture.md`, `assets/enhanced-report-shell.html` — capability tiers, required editorial/motion layers, performance budgets, the Enhanced QA gate). It was deferred honestly rather than rushed in exhausted context.
- **The duel pool (challengers, NOT slots — they enter only by winning a duel or filling a deprecated slot):** `meeting-transcript` (de-vendor fireflies), `safe-rewrite` (de-vendor `~/clawd/fable-safe-prompt-rewriter`), `purchase-research` (de-vendor online-shopping), `leonardo-tournament` (generalize `~/Documents/Crosswalk/leonardo-motion-lab` — generate-N/hash/score/show-before-promote). None is admitted; each would have to beat a named incumbent via `skill-duel`.

## 8. Fleet State

- **Git accounts (both in the gh keyring):** `Navigata1` owns the staging repo `Navigata1/idc-skills-forge`. `IslandDevCrew` (org: `Island-Dev-Crew`) is org admin for the public production repo `Island-Dev-Crew/idc-skills`. Pushing to Navigata1 requires `gh auth switch --user Navigata1`.
- **Both repos are at `c4202cf`** (release 2.0.0). Local tree clean at that HEAD.
- **Commit identity:** Jon's global identity (Jon Isaac / jon-isaac@islanddevcrew.com); attribution trailer disabled per his git-workflow rule.
- **Related repo:** the archipelago *protocol* lives separately at `Navigata1/archipelago` (its Python residuals are §5 traps — not part of this repo).
- Lane claims: None held. Finding-register ids: none allocated in this handoff (the promotion's ~110 defects were fixed+verified during the 1.x releases, recorded in the memory file). Cross-family-review verdicts: the v1.2/1.3 sets were verified by the repo's own `cross-family-review` run as a Workflow (0 critical, all findings fixed); those verdicts are void at any head past their capture — re-derive from the tree if you need them.

## 9. Suggested Skills

- **`handoff` / pickup** — this document is a handoff; the next agent should arrive via the pickup wake protocol below.
- **`cross-family-review`** — before any change to the pack merges, an independent reviewer from a different model family reviews the diff at an exact head.
- **`skill-duel`** — the ONLY admissible way to change the locked 50: run any challenger against a named incumbent on one identical gauntlet.
- **`gauntlet-loop`** — to re-vet a candidate or an improved product (YPE, iron-canvas) against a falsifiable bar before claiming it improved.

---
## Prompt for the Fresh Agent

The IDC Skills Forge is **locked at 50/50 islands, release 2.0.0**, live at `Island-Dev-Crew/idc-skills` (public) and staged at `Navigata1/idc-skills-forge`, both at commit `c4202cf`; the local tree at `/Users/IDC2.5/Desktop/IDC-skills` is clean at that HEAD. Every island is gauntleted to confidence ≥9 on a defect-tied rubric (confidence = 10 − real unaddressed defects). The pack is a living deadlock: it changes only by a won `skill-duel` or a deprecated-slot fill at ≥9. The moat is 6 IDC-native islands + the 7-island ICM cluster (from `RinDig/icm-architect`) welded to the evidence law + the `cross-family-review` ceremony. Two things are PRODUCTS, not forge slots, kept in `~/clawd`: YPE youtube-pipeline (at 5/10, restored to clean v7.2) and iron-canvas (at ~8.5, below the 9.5 bar). The docs/walkthrough.html enhanced rebuild is not started. The duel pool holds four un-admitted challengers. `archipelago`'s open findings are bugs in the SEPARATE `Navigata1/archipelago` protocol repo, not this one.

Before responding, run the wake protocol: read every file under "Files & Pointers", re-read any verdicts and finding-register entries named under "Fleet State" from the tree, and treat every claim in this handoff as context to verify — not fact to trust. Then wait for instructions.

**No authority without evidence. The handoff orients; the tree is the truth.**
