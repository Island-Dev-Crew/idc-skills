---
name: workspace-scaffold
description: Scaffold a new ICM workspace for a domain — generate the root map, the rooms, the naming conventions, and prove the routing works, from a short brief. Use when the user wants to set up a folder-as-workspace, "make me a workspace", "scaffold an ICM", "workspace creator", or convert an existing project folder into a routed workspace. Differentiator - the generator for folder-workspace; it produces the structure and then proves a fresh agent routes through it before declaring done.
---

# Workspace Scaffold — generate the workspace

The capability primitive to [`folder-workspace`](../folder-workspace/SKILL.md)'s discipline. It turns a short brief ("a content studio: writing, production, community") into a working ICM workspace — root map, rooms, naming conventions — and then proves a fresh agent can route through it. The deterministic skeleton is a script; the judgment (which rooms, what naming, what each room does) is yours.

## Process

### 1. Grill the shape (briefly)

Don't scaffold cold. In one or two exchanges, settle: what work happens here (the rooms), what each room produces (the naming conventions), and whether this is a fresh workspace or an existing folder to convert. If the brief is under-specified, run the [`grill`](../grill/SKILL.md) island first — but keep it short; a workspace is cheap to reshape later.

**Done when** you can name the rooms, one line of purpose per room, and the naming convention for each room's outputs.

### 2. Scaffold the skeleton

Run the bundled [scripts/scaffold.sh](scripts/scaffold.sh) — it creates the deterministic parts: the `CLAUDE.md` redirect, an `AGENTS.md` map stub carrying a routing-table skeleton and an enforcement note, a `rooms/<name>/CONTEXT.md` per room, and `inbox/` + `evidence/` directories.

```bash
scripts/scaffold.sh <workspace-dir> "room1 room2 room3"
```

**Done when** the skeleton exists: a root map, one `CONTEXT.md` per room, and the inbox/evidence dirs.

### 3. Fill in the judgment

Edit the generated map and rooms per [`folder-workspace`](../folder-workspace/SKILL.md) and [`writing-for-agents`](../writing-for-agents/SKILL.md): write the routing table (task → read → skip → skills), the naming conventions, each room's purpose/load/skip/process, and the "start here" purpose gate. Keep the map lean — it loads every session. Use the copy-me shapes in [folder-workspace/references/map-template.md](../folder-workspace/references/map-template.md).

**Done when** the routing table has a row per task the workspace handles, each room states its purpose and closes with the return-to-map fallback, and the map states which rules are enforced vs advisory.

### 4. Prove the routing (the completion gate)

A scaffold that doesn't route is worthless. Prove it before declaring done:

1. From the workspace root, give a fresh agent one under-specified prompt that maps to a room ("I want to work on X").
2. Confirm it reads the map, routes to the *right* room, and does **not** read the whole tree (progressive disclosure held).
3. Give it a prompt matching *no* room. Confirm it falls back to the map rather than guessing.

If step 2 reads everything or step 3 strands the agent, the routing is wrong — fix the map before finishing. This is [`folder-workspace`](../folder-workspace/SKILL.md)'s completion criterion, applied to the thing you just generated.

**Done when** you have observed a correct route to a room and a correct fallback on a no-match prompt.

## Converting an existing folder

Same flow, but step 2 reads what's already there first: map the existing folders to rooms, propose naming conventions that match files already present (don't rename en masse — describe what's there), and write the map *over* the existing structure. The point of ICM is you know your own files better than any agent; the scaffold just gives the agent the map to them.

**No authority without evidence. A scaffold is done when a fresh agent routes through it, not when the folders exist.**
