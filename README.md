# IDC Skills · The Forge

**An archipelago of agent skills.** Each skill is an island; the repo is the navigable chain that connects them. Fused from David Ondrej's and Matt Pocock's public canons, welded to the discipline Island Development Crew earned shipping agent-built software: **no authority without evidence — the skills demonstrate their own discipline.**

> *"In the multitude of counsellors there is safety."* — Proverbs 11:14

This is the **staging forge** (`Navigata1/idc-skills-forge`). Skills are validated here by live fleet use, then the golden fusion is promoted to `Island-Dev-Crew` as official, each carrying its validation record. A skill is proven by lanes running it, not by its author's confidence.

---

## The chain — sixteen islands, in build order

The order is the bootstrap: island 1 authors the rest; the crown ships with a week of receipts; the two IDC-only islands exist nowhere else.

| # | Island | Kind | What it does |
|---|--------|------|--------------|
| 1 | [`idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) | canon | Authors every other island — anatomy, progressive disclosure, the two loads, leading words, failure modes, fleet distribution. |
| 2 | [`cross-family-review`](skills/cross-family-review/SKILL.md) | 👑 crown | A different model family reviews a diff at an exact head; the verdict names its seats and voids on move. The author never reviews their own work. |
| 3 | [`worktree-fleet`](skills/worktree-fleet/SKILL.md) | fusion | Worktrees for same-machine parallelism — adopted for drafts, forbidden for evidence. The version that knows when *not* to use itself. |
| 4 | [`grill`](skills/grill/SKILL.md) | fusion | Relentless interview in three modes (ambush · drill · batch), emitting settled decisions as ADRs. |
| 5 | [`agent-guardrails`](skills/agent-guardrails/SKILL.md) | fusion | Four mechanical layers — shell · git · commit · data — under the whole fleet. |
| 6 | [`handoff`](skills/handoff/SKILL.md) | fusion | State-based handoff + the wake protocol: re-read verdicts and register from the tree before trusting the summary. |
| 7 | [`lane-claim`](skills/lane-claim/SKILL.md) | 💠 IDC-only | Declare-and-halt coordination across machines — the collisions worktrees can't touch. |
| 8 | [`transport-complete`](skills/transport-complete/SKILL.md) | fusion | Pushed-and-verified-live or not done — a health check for the exact SHA. |
| 9 | [`spec-pipeline`](skills/spec-pipeline/SKILL.md) | fusion | Spec → tracer tickets → implement at seams → optional persistent goal loop. |
| 10 | [`research`](skills/research/SKILL.md) | fusion | Primary-source investigation; every claim sourced or flagged unverified. |
| 11 | [`finding-register`](skills/finding-register/SKILL.md) | 💠 IDC-only | Findings enumerated at a SHA (not a count), provenance both ways, id swept before allocation. |
| 12 | [`deep-modules`](skills/deep-modules/SKILL.md) | adapt | The deep-module vocabulary + the boundary rules that make entry points the only way in. |
| 13 | [`diagnose`](skills/diagnose/SKILL.md) | adapt | The loop before the theory; performance judged by operation counts, not wall-clock. |
| 14 | [`archipelago`](skills/archipelago/SKILL.md) | Jon's | The evidence-gated build protocol — gates that must be able to fail, band caps you can't talk past. |
| 15 | [`short`](skills/short/SKILL.md) | adopt | Compress the current answer. |
| 16 | [`teach`](skills/teach/SKILL.md) | adopt | A stateful multi-session teaching workspace. |

## The moat, stated plainly

Three of these exist nowhere else — [`lane-claim`](skills/lane-claim/SKILL.md), [`finding-register`](skills/finding-register/SKILL.md), and the ceremony layer inside [`cross-family-review`](skills/cross-family-review/SKILL.md). Anyone can fuse two public repos. Only IDC can ship the review ceremony with receipts: named seats, provenance corrected in both directions, verdicts bound to exact heads. **That is the product.**

## Design palette

The archipelago wears the Iron Canvas palette — OLED `#0a0a0f`, garnet · rust · gold · jade · steel — with a faceted-gem motif. The landing experience is a journey across the chain, not a file listing: see [`docs/index.html`](docs/index.html). Repo-as-artifact, matching the thesis.

## Install

```bash
# distribute every island across the four fleet skill folders (Codex/Claude/Pi/Hermes)
./scripts/install.sh
```

`install.sh` copies each island to the canonical `~/.agents/skills/` (Claude and Pi are symlinks, auto-covered), copies to Hermes, verifies byte counts match across all four, and validates every `SKILL.md` frontmatter. See [`skills/idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) §8 for the layout and traps.

## Provenance & the pending inputs

The fusion recipe is `IDC-SKILLS-FUSION-REPORT-v1`. Two companion inputs — the Buzz conversations and the owner transcripts — arrived empty at authoring time; nothing here was reconstructed from them, and no claim in these skills represents Buzz's analysis or the owners' commentary. The Garnet ceremony layer rests on IDC's own verified production record.

## Pipeline — staging to official

1. **Author** under the `idc-skill-authoring` canon.
2. **Stage** here in `Navigata1/idc-skills-forge`.
3. **Vet in live fleet use** — evidence of use, not declaration of quality.
4. **Promote** the validated golden fusion to `Island-Dev-Crew`, each island carrying its validation record.

## License

MIT — see [LICENSE](LICENSE).

— **Island Development Crew** · Huntsville, AL · *No authority without evidence.* · Roll Tide 💎
