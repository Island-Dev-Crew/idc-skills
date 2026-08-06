# Map template — a copy-me root map

Loaded by `folder-workspace` on demand. Copy this to a workspace root as `AGENTS.md` (and add a one-line `CLAUDE.md` that redirects to it). One level deep from `SKILL.md`.

## The redirect (`CLAUDE.md`)

```markdown
Read AGENTS.md in this folder and follow it. (This project routes every seat through one map.)
```

## The map (`AGENTS.md`)

```markdown
# <Workspace name> — the map

## Start here
You are in <workspace name>. Read this map, find your task in the routing table
below, read ONLY what it names, then act. Do not read a room you were not routed
to — every unread room is tokens saved.

## Floor plan
rooms/writing/     — drafts, the voice, the blog/newsletter process
rooms/production/  — builds, specs, animations, outputs
inbox/             — raw capture (transcripts, notes) waiting to be distilled
evidence/          — evidence-packets and verdicts (do not edit by hand)

## Naming conventions
- Drafts:      rooms/writing/<slug>-draft.md, -v2, -v3
- Newsletters: rooms/writing/YYYY-MM-DD-<slug>.md
- Outputs:     rooms/production/out/<slug>-<YYYYMMDD>.<ext>
An agent MUST name new files this way, so the next session finds them without a database.

## Routing
| When the task is…       | Read                         | Skip           | Skills                 |
|-------------------------|------------------------------|----------------|------------------------|
| write / edit copy       | rooms/writing/CONTEXT.md     | production/*   | writing-for-agents     |
| build / render          | rooms/production/CONTEXT.md  | writing/*      | —                      |
| capture raw material    | inbox/CONTEXT.md             | everything else| productionize-opinion  |
| prove a change          | evidence/CONTEXT.md          | —              | evidence-packet        |
| anything NOT listed     | return to this map           |                |                        |

## Enforcement
Advisory: this map has no hook — an agent honors the routing by reading it. The one
enforced boundary, if wired, is the deep-modules boundary lint over rooms/. State that
plainly; never imply the routing is mechanically enforced when it is not.
```

## Each room (`rooms/<name>/CONTEXT.md`)

```markdown
# Room: <name>
Purpose: <one line — what work happens here>.
Load: <the files in this room worth reading, and when>.
Skip: <what NOT to read from here>.
Process: <the ordered steps for this room's work>.
Naming: <the convention for files this room produces>.

For anything not in this room, return to the root map (../../AGENTS.md).
```

The room's closing line is the recursive fallback — it is what keeps an agent from being stranded when a prompt doesn't match this room.
