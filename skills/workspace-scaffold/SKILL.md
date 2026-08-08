---
name: workspace-scaffold
description: Scaffold a new ICM workspace for a domain — generate the root map, the rooms, the naming conventions, and prove the routing works, from a short brief. Use when the user wants to set up a folder-as-workspace, "make me a workspace", "scaffold an ICM", "workspace creator", or convert an existing project folder into a routed workspace. Differentiator - the generator for folder-workspace; it produces the structure and then proves a fresh agent routes through it before declaring done.
---

# Workspace Scaffold — generate the workspace

The capability primitive to [`folder-workspace`](../folder-workspace/SKILL.md)'s discipline. It turns a short brief ("a content studio: writing, production, community") into a working ICM workspace — root map, rooms, naming conventions — and then proves a fresh agent can route through it. The deterministic skeleton is a script; the judgment (which rooms, what naming, what each room does) is yours.

## Process

### 1. Grill the shape (briefly)

First confirm the work actually repeats and warrants a workspace at all. If the whole job fits one saved prompt or skill, emit that and stop — don't scaffold a tree for a thing done twice. That should-we-build call belongs to [`job-to-be-done`](../job-to-be-done/SKILL.md); settle it before generating anything.

Then don't scaffold cold. In one or two exchanges, settle: what work happens here (the rooms), what each room produces (the naming conventions), and whether this is a fresh workspace or an existing folder to convert. Scaffold only rooms that hold real work now — reject speculative, "misc", or empty-bucket rooms; three real rooms beat seven imagined ones, and a room is cheap to add later. If the brief is under-specified, run the [`grill`](../grill/SKILL.md) island first — but keep it short; a workspace is cheap to reshape later.

**Done when** you can name the rooms, one line of purpose per room, the naming convention for each room's outputs, and which of the five ICM forms this is (Pipeline / Umbrella / Record library / Knowledge bundle / Context map — defer the taxonomy to [`folder-workspace`](../folder-workspace/SKILL.md)), because the form decides the skeleton the generator lays.

### 2. Scaffold the skeleton

Run the bundled [scripts/scaffold.sh](scripts/scaffold.sh) — it creates the deterministic parts: the `CLAUDE.md` redirect, an `AGENTS.md` map stub carrying a routing-table skeleton and an enforcement note, a `rooms/<name>/CONTEXT.md` per room, and `inbox/` + `evidence/` directories.

```bash
scripts/scaffold.sh <workspace-dir> "room1 room2 room3"
```

Room names are restricted to a single flat `[A-Za-z0-9_-]` segment — no slashes, dots, or leading dash — and cannot be `inbox`, `evidence`, or `rooms` (reserved for the top-level dirs the script also creates). The script rejects anything else before touching disk.

scaffold.sh emits only the flat generic room shape — one of the five ICM forms. When the settled form is a **Pipeline**, lay numbered `NN_stage/` folders, each with its own `output/`; a **Record library**, a `_templates/<unit>/` stamp plus an `_index/log.md`; a **Knowledge bundle**, split factory and product as separate top-level trees. Extend the script or hand-build the matching skeleton — the flat room set is not always the right generation. Whichever form, the tree must also carry a factory location (`_shared/` or `references/`) for reference material stable across runs, and — where the workspace instantiates units — a `_templates/` blank unit: the factory/product split and instantiate-by-copying have to exist in the tree, not merely be described in the map.

**Done when** the skeleton exists: a root map, one `CONTEXT.md` per room, and the inbox/evidence dirs.

### 3. Fill in the judgment

Edit the generated map and rooms per [`folder-workspace`](../folder-workspace/SKILL.md) and [`writing-for-agents`](../writing-for-agents/SKILL.md): write the routing table (task → read → skip → skills), the naming conventions, each room's contract — purpose, process, and Inputs split into Working (this run) vs Reference (every run), closing with exactly one human check stated as an action a person does before the next room reads the output (the canonical stage-contract shape, not a bare purpose/load/skip/process) — and the "start here" purpose gate. Keep the map lean — it loads every session. Use the copy-me shapes in [folder-workspace/references/map-template.md](../folder-workspace/references/map-template.md).

**Done when** the routing table has a row per task the workspace handles, each room states its purpose and closes with the return-to-map fallback, and the map states which rules are enforced vs advisory.

### 4. Prove the routing (the completion gate)

A scaffold that doesn't route is worthless. Prove it before declaring done:

1. From the workspace root, give a fresh agent one under-specified prompt that maps to a room ("I want to work on X").
2. Confirm it reads the map, routes to the *right* room, and does **not** read the whole tree (progressive disclosure held).
3. Give it a prompt matching *no* room. Confirm it falls back to the map rather than guessing.
4. Give it a prompt that legitimately spans multiple rooms. Confirm the map tells it what to do — a dedicated multi-room/cross-cutting routing row naming an ordered read set, or an instruction to ask the user to split the task — rather than reading every room to cover its bases.

If any step reads everything, strands the agent, or leaves it to guess, the routing is wrong — fix the map before finishing. This is [`folder-workspace`](../folder-workspace/SKILL.md)'s completion criterion, applied to the thing you just generated.

**Done when** you have observed a correct route to a room, a correct fallback on a no-match prompt, and correct handling of a multi-room prompt.

## Converting an existing folder

scripts/scaffold.sh is from-scratch only — do not point it at a folder that already holds real work. It always creates `rooms/<name>/` stubs, so pointed at an existing project it builds a parallel tree of empty CONTEXT.md placeholders while every real file stays unmapped — orphaning the actual content and failing step 4's routing gate immediately.

For an existing folder, build the map by hand instead: write only `AGENTS.md`, `CLAUDE.md`, `inbox/`, and `evidence/` (skip `rooms/` entirely — use [scripts/scaffold.sh](scripts/scaffold.sh)'s stub text as a shape reference, not by running it), then add a `CONTEXT.md` inside each *existing* top-level folder that will act as a room. Point every routing-table row and every `Load:` line at that real folder (e.g. `Load: notes/`), never at a new `rooms/` copy. Propose naming conventions that match files already present — don't rename en masse, describe what's there. The point of ICM is you know your own files better than any agent; the scaffold just gives the agent the map to them.

**No authority without evidence. A scaffold is done when a fresh agent routes through it, not when the folders exist.**
