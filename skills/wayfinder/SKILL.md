---
name: wayfinder
description: Plan a chunk of work too big for one agent session — chart it as a shared map of decision tickets on the issue tracker, then resolve them one at a time until the way to the destination is clear. Use when a loose, foggy idea is bigger than a single spec, spans many sessions, or the user says "wayfinder", "help me plan this big thing", "chart this", or "I don't know where to start". Differentiator - plans across sessions by resolving decisions, not slices of a build; it plans the way, it does not charge the destination.
disable-model-invocation: true
---

# Wayfinder — chart the way, don't charge the destination

A loose idea has arrived, too big for one agent session and wrapped in fog: the way from here to the **destination** isn't visible yet. Wayfinding finds that way. It sits *above* [`spec-pipeline`](../spec-pipeline/SKILL.md) — spec-pipeline builds one feature; wayfinder charts a whole effort as a **shared map** of **decision tickets** (questions whose resolution is a *decision*, not a slice of build) and works them one at a time until the route is clear.

Two leading words carry it: **fog of war** (what you can tell is coming but can't yet pin down) and the **frontier** (the decisions you can take *now*). You plan by clearing fog into frontier, one ticket at a time.

## Plan, don't do

Wayfinder is **planning** by default: each ticket resolves a decision; the map is done when nothing is left to decide before someone goes and builds. The pull to just do the work is the signal you've reached the edge of the map — hand off to `spec-pipeline`. Produce decisions, not deliverables.

## The map

The map is a single issue on the repo's tracker, labelled `wayfinder:map` — the canonical artifact, loaded once per session. It is an **index, not a store**: each decision lives in exactly one place (its ticket); the map only gists and links. Refer to every ticket by its **name** (title), never a bare `#42` — a wall of ids is illegible; names read at a glance.

```markdown
## Destination
<what reaching the end looks like — the spec, decision, or change this effort finds its way to>
## Notes
<domain; skills every session should consult; standing preferences>
## Decisions so far
- [<closed ticket name>](link) — <one-line gist of the answer>
## Not yet specified
<the fog: in-scope questions you can't ticket sharply yet — graduates as the frontier advances>
## Out of scope
<work ruled beyond the destination — closed, never graduates>
```

Each **ticket** is a child issue sized to one ~100K-token session; its body is the **Question**. Tickets carry a `wayfinder:<type>` label and use the tracker's **native** blocking so the frontier renders visually. A ticket is **unblocked** when every ticket blocking it is closed; the **frontier** is the open, unblocked, unclaimed children. A session **claims** a ticket by assigning it *before* any work, so concurrent sessions skip it.

## Ticket types — where the other islands plug in

Every ticket is **HITL** (worked *with* a human who speaks for themselves) or **AFK** (agent alone). Wayfinder is the capstone that dispatches to the rest of the archipelago:

- **Research** (AFK) — a fact a decision waits on. Resolved by a [`research`](../research/SKILL.md) subagent.
- **Prototype** (HITL) — "how should it look / behave?" Raise fidelity with a [`prototype`](../prototype/SKILL.md); link it as an asset.
- **Grilling** (HITL) — conversation, the default. Invoke [`grill`](../grill/SKILL.md) and [`domain-modeling`](../domain-modeling/SKILL.md). The agent never answers the human's side.
- **Task** (HITL or AFK) — manual work that must happen before a decision can be made (sign up for a service, provision access, move data so its shape is visible). The one type that *does*; it earns its place by unblocking a decision.

## Fog of war

The map is *deliberately* incomplete — don't chart what you can't yet see. Resolving a ticket clears the fog ahead of it, graduating whatever's now specifiable into fresh tickets. The test of **fog vs ticket** is whether you can state the question *precisely now* — not whether you can answer it. Ticket when the question is sharp (even if blocked); leave it in **Not yet specified** when it isn't. Fog only gathers *toward* the destination; work beyond the destination is **Out of scope** — closed, never graduating.

## Invocation

**Chart the map:** name the destination (grill + domain-modeling — the destination fixes scope, settle it first); grill again breadth-first to surface the frontier; create the map; create the tickets you can specify now, then wire blocking in a second pass; fire research subagents; stop — charting resolves nothing.

**Work through the map:** load the low-res map; choose the frontier ticket (claim it first); resolve it, zooming into related tickets on demand and invoking the skills Notes names; record the resolution (answer comment, close the issue, append a context pointer to Decisions-so-far); graduate any fog the answer sharpened.

**Never resolve more than one ticket per session** (except research). One session, one decision — that is what keeps the map honest.

Enforced-vs-advisory: the claim (assign-before-work), the one-ticket-per-session rule, and the `wayfinder:*` labels are **advisory and cooperative** — nothing on the tracker mechanically blocks an unclaimed pickup or a multi-ticket session. The assigned ticket is the evidence each session reads before acting; the enforcement is each session honoring it. The tracker's native blocking only *renders* the frontier — it doesn't bar a violation. State this the way [`lane-claim`](../lane-claim/SKILL.md) does; a reader must not infer a mechanical lock the tracker doesn't provide.

**No authority without evidence. A decision lives in exactly one ticket; the map only points.**
