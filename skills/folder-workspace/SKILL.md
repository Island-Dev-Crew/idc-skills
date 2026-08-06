---
name: folder-workspace
description: The ICM folder-as-workspace discipline — folders and markdown as the agent's architecture, routed by a three-layer map so one agent becomes the agent each task needs, without building agent swarms. Use when organizing a project for an AI, deciding folder structure or naming conventions, routing an agent to the right context, or when the user mentions "folder as workspace", "ICM", "interpretable context methodology", "map", "router", or "become the agent". Differentiator - the architecture substrate the other islands route within (the map is an auditable routing contract, not just convenience); to generate a new workspace, route to workspace-scaffold.
---

# Folder Workspace — the folder is the architecture

The substrate island. It fuses Jake Van Clief's **Interpretable Context Methodology (ICM)** — folders and markdown as agent architecture — with the forge's evidence discipline, so the workspace an agent routes through is also the place its evidence lives. The thesis both sides reached independently: **the repo is the memory.** Jake reached it from folder/context architecture; the archipelago reached it from evidence/review. This island is where they meet.

The move ICM makes: stop building an agent (or a swarm) for each task. Instead, structure the folder so **one agent becomes the agent each task needs** by reading its way there. A fresh model in a fresh session, given only the folder, becomes the specialist — because the folder routes it. This is [`writing-for-agents`](../writing-for-agents/SKILL.md)'s information hierarchy made *spatial*, and it survives model updates because your context, not the model, is the durable value.

## The three layers

Every ICM workspace runs on three routing layers. Most people build only one or two; the third is what makes it composable.

```
workspace/
  AGENTS.md          ← LAYER 1: THE MAP. The canonical map, loads for every seat.
  CLAUDE.md          ←   (a one-line redirect to AGENTS.md, so Claude Code loads it too)
  rooms/
    writing/CONTEXT.md   ← LAYER 2: THE ROOMS. Read on the way to a task.
    production/CONTEXT.md
  <the actual files>  ← LAYER 3: THE WORKSPACE. Where work and outputs live.
```

- **Layer 1 — the map.** The canonical map is a root `AGENTS.md`, loaded at session start by every seat. It carries the **floor plan**: the folder structure, the naming conventions, and — the heart of it — the **routing table**. It never carries the work itself. Because Claude Code reads `CLAUDE.md` first, keep a one-line `CLAUDE.md` that redirects to it — `Read AGENTS.md and follow it.` — so the same map serves every seat. (The two files are interchangeable mirror images; this island keeps the map in `AGENTS.md` and the redirect in `CLAUDE.md` so nothing mislocates it.)
- **Layer 2 — the rooms.** Per-area `CONTEXT.md` files reached *by* the map. The agent reads a room only when the task routes it there — progressive disclosure, so it never burns tokens on a room it isn't in.
- **Layer 3 — the workspace.** The actual files. Outputs land here, named by the convention the map declares, so the next session finds them without a database.

## The routing table — the most important pattern

The map's core is a table: *for this task, read these files; skip those; you might need these skills.* Without it the agent reads everything (token burn) or guesses wrong. With it, the agent routes in one hop.

```markdown
## Routing
| When the task is…      | Read                       | Skip            | Skills                |
|------------------------|----------------------------|-----------------|-----------------------|
| write a blog post      | rooms/writing/CONTEXT.md   | production/*    | writing-for-agents    |
| build an animation     | rooms/production/CONTEXT.md| writing/*       | —                     |
| anything not listed    | (go back to this map)      |                 |                       |
```

Three rules borrowed from the reaction-video operator, welded to the forge:

- **Start here — the purpose gate.** The map's first line tells the agent what to read *and why*, so it never reads for no reason. "Don't read information without a purpose."
- **If it's not here, go back.** Every room ends by pointing home: *"For anything not in this room, return to the root map."* Recursive fallback — the agent is never stranded.
- **The map is a routing contract, not decoration.** State enforced-vs-advisory: a routing rule is **advisory** unless a boundary lint (see [`deep-modules`](../deep-modules/SKILL.md)) actually forbids a cross-room import. Never imply the map is enforced when nothing enforces it — that is the laundering the archipelago forbids.

A full map you can copy is in [references/map-template.md](references/map-template.md).

## Become the agent, not a swarm

*"Why not just have Claude become the agent you need when you're working in the workspace?"* One agent walks the folder and **becomes** the writing agent, the production agent, the review agent — reading its way into each role. Sub-agents it spawns read the same files and become the same thing. You get the leverage of a swarm with none of the opacity: every role is a folder you can read, and if the AI breaks tomorrow the process is still human-readable SOPs.

## Model-agnostic, update-proof

Because the workspace is plain folders and markdown, it works in Claude, Codex, Pi, Hermes, Cursor, or a local model — *"if Claude goes down, you just hop to the other one."* And it survives model updates: the model gets better at executing *your* process, which is the thing not being trained away. Every update that lets you delete a room (the model now does natively what a markdown file used to teach) makes the workspace *smaller* — fewer tokens, cleaner routing.

## Where this sits in the archipelago

folder-workspace is **layer 0** — the ground the loop runs on. [`writing-for-agents`](../writing-for-agents/SKILL.md) writes the map and rooms; [`workspace-scaffold`](../workspace-scaffold/SKILL.md) generates the structure; [`productionize-opinion`](../productionize-opinion/SKILL.md) fills the rooms with your voice; [`handoff`](../handoff/SKILL.md)'s pickup/handoff pair carries state between sessions; [`console-as-code`](../console-as-code/SKILL.md) stamps the map when it must be reproducible; [`workspace-audit`](../workspace-audit/SKILL.md) checks the map still matches the tree; and evidence-packets, verdicts, and register entries all *live in* the workspace. The `CONTEXT.md` at the repo root is this repo's own map.

**Done when** a fresh session, given only the workspace, routes to the right room from one under-specified prompt without reading the whole tree — and the map states which of its rules are enforced and which are advisory.

**No authority without evidence. The map is a routing contract; the tree is the truth.**
