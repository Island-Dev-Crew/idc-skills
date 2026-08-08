---
name: workspace-audit
description: Audit an ICM workspace for drift — check that every path the map claims exists in the tree, and that no live folder or file is missing from the map. Use when a workspace has grown and the map may be stale, before trusting a map to route, or when the user mentions "audit my workspace", "check the map", "workspace drift", or "does the map still match". Differentiator - the verify side of folder-workspace; the map is a claim, the tree is the evidence, and drift is a claim the evidence contradicts.
---

# Workspace Audit — the map is a claim, the tree is the evidence

The verify-side island of the ICM cluster. A [`folder-workspace`](../folder-workspace/SKILL.md) map *claims* the tree contains certain rooms, files, and routes. Over time the tree drifts — a room is added and never mapped, a file the routing table points at is renamed. A stale map routes an agent to a file that no longer exists, or hides a room it should reach. Auditing is the forge's own move applied to the workspace: **the map is a claim; the tree is the evidence; drift is a claim the evidence contradicts.**

## What drift looks like

- **Broken claim** — the map names a path (a floor-plan line, a routing-table `Read` cell) that does not exist in the tree. The map lies; an agent routed there fails.
- **Blind spot** — a live room or context file exists in the tree that the map never mentions. An agent will never route to it; the work there is orphaned.
- **Stale route** — a routing row points at a file that moved. Same as a broken claim, but hides inside the table.
- **Schema drift** — a `schema.md` or naming-convention doc mandates a name the actual files stopped using, or the files adopted a name the schema never blessed. This is the most common decay: reconcile schema-to-files the moment you see it — update one to match the other, never leave both drifting on.
- **Duplicate home** — the same fact, or a hand-maintained second entry file (a `CLAUDE.md` and an `AGENTS.md` both editing the map), lives in two places and the copies have diverged. One home per fact; a link beats a copy — pick the home, make the other a pointer.

## Audit

Run the bundled [scripts/audit.sh](scripts/audit.sh) against the workspace (it runs from any cwd — every path is resolved under the workspace argument):

```bash
<this-skill-dir>/scripts/audit.sh <workspace-dir>
```

It strips URLs from the map, extracts every relative path the map references and checks each exists, then lists every `rooms/**/CONTEXT.md` and every top-level `*.md` (other than the map files and `README.md`) the map never mentions. It reports two lists: **broken claims** (mapped paths missing from the tree) and **blind spots** (tree paths missing from the map, matched by exact token — never substring — so a sibling name like `rooms/api` vs `rooms/api-gateway` can't hide a real gap). Trailing sentence punctuation is stripped, so a path at the end of a prose sentence (`…at rooms/api/CONTEXT.md.`) is not mis-read as a missing file. The same missing path referenced from several map locations is reported once per reference by design, so each stale reference is individually fixable — expect duplicates, not two separate defects. A clean audit prints neither and exits 0 — meaning no path-token mismatch was found, not that the map is correct; any drift exits 1.

The script is a *heuristic* — it catches path-level drift, not semantic drift (a room whose `Process` no longer matches how you actually work), and its path extraction assumes the [`folder-workspace`](../folder-workspace/SKILL.md) naming convention (no spaces in a path segment). A path containing a space is outside what it can parse, so rather than shred it into garbage tokens the script detects it and emits a distinct **WARNING** (skipped, judge by hand) instead of a false broken/blind finding. State that: the script is the enforced part; judging whether a room's *content* is still true is the advisory part, and it is yours.

## The walk test — the advisory half

The script is the enforced half; the walk test is the advisory half, yours to run by hand. Walk the workspace cold, as an agent with no memory:

1. **Open the root** — does the entry file plus at most two more reads answer *where am I* and *where do I go next*?
2. **Pick any room or stage** — does its CONTEXT name exact input paths, the job, the output, and the one human check?
3. **Read status from the tree** — can you state pipeline status purely by scanning the `output/` folders, or is a hand-maintained status file lying about what actually exists?
4. **Check the routing files** — is any of them carrying content payload where a pointer belongs?
5. **Check for divergence** — is any fact stored in two homes that can drift apart?
6. **Token check** — entry file plus one contract plus its inputs should land in roughly 2k–8k tokens.

A path-clean audit (exit 0) can still fail the walk. The script proves no path-token mismatch; the walk is where semantic drift surfaces — and semantic drift is the judgment call the script cannot make for you.

## Fix, don't hide

For each finding, fix the *map* or the *tree* — never silence the audit:

- **Broken claim** → the file moved or died. Update the map's path, or restore the file. Do not delete the routing row to make the audit pass; that hides a route the workspace needs.
- **Blind spot** → a real room went unmapped. Add its floor-plan line and routing row. If the folder is genuinely dead, delete it (an ICM workspace gets *smaller* as it matures — see [`folder-workspace`](../folder-workspace/SKILL.md)), and say so.

## Where the findings go

A confirmed drift is a finding — enumerate it into the [`finding-register`](../finding-register/SKILL.md) at the workspace's current head, with the `audit.sh` invocation as its recomputable command. Pair this with [`console-as-code`](../console-as-code/SKILL.md) when the map is assembled from stamped blocks: a stamp mismatch and a drift finding are the same signal at two altitudes.

**Done when** the audit reports zero broken claims and zero blind spots, or every remaining item is a recorded, reasoned decision (a folder deliberately left unmapped, with the reason). Not when the audit was silenced.

**No authority without evidence. Fix the drift; never delete the check to make it pass.**
