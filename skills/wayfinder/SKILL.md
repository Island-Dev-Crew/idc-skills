---
name: wayfinder
description: Plan a chunk of work too big for one agent session — chart it as a shared map of decision tickets on the issue tracker, then resolve them one at a time until the way to the destination is clear. Use when a loose, foggy idea is bigger than a single spec, spans many sessions, or the user says "wayfinder", "help me plan this big thing", "chart this", or "I don't know where to start". Differentiator - plans across sessions by resolving decisions, not slices of a build; it plans the way, it does not charge the destination.
disable-model-invocation: true
---

# Wayfinder: chart the way, don't charge the destination

A loose idea has arrived, too big for one agent session and wrapped in fog: the way from here to the **destination** isn't visible yet. Wayfinding finds that way. It sits *above* [`spec-pipeline`](../spec-pipeline/SKILL.md): spec-pipeline builds one feature; wayfinder charts a whole effort as a **shared map** of **decision tickets** (questions whose resolution is a *decision*, not a slice of build) and works them one at a time until the route is clear.

Two leading words carry it: **fog of war** (what you can tell is coming but can't yet pin down) and the **frontier** (the decisions you can take *now*). You plan by clearing fog into frontier, one ticket at a time.

## Plan, don't do

Before charting, judge whether the effort even needs a map: if it fits one grilling session, degrade to a single [`grill`](../grill/SKILL.md)(+docs) session and create no map; wayfinder is the orchestrator only when the work spans sessions.

Wayfinder is **planning** by default: each ticket resolves a decision; the map is done when nothing is left to decide before someone goes and builds. The pull to just do the work is the signal you've reached the edge of the map; hand off to `spec-pipeline`. Produce decisions, not deliverables. The map is complete only when every ticket is closed **and** *Not yet specified* holds no fog still pointing at the destination. Resolving a final ticket can graduate fresh fog into new tickets, so an all-children-closed count is necessary but not sufficient; the handoff waits until there is genuinely nothing left to ticket. Then hand it whole to `spec-pipeline` to synthesize the detailed spec, and close the map issue; it is disposable context that points back to the decisions, not a kept artifact.

## The map

The map is a single issue on the repo's tracker, labelled `wayfinder:map`, the canonical artifact, loaded once per session. It is an **index, not a store**: each decision lives in exactly one place (its ticket); the map only gists and links. Refer to every ticket by its **name** (title), never a bare `#42`: a wall of ids is illegible; names read at a glance.

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

**Map rollover:** when Decisions-so-far nears the tracker's issue-body limit (GitHub: 65,536 chars), archive older closed decisions into a linked child decision-log issue, leaving just a link and a running count; the map stays the low-res index it claims to be, never the store.

Each **ticket** is a child issue sized to one ~100K-token session; its body is the **Question**. Tickets carry a `wayfinder:<type>` label and use the tracker's **native** blocking so the frontier renders visually. A ticket is **unblocked** when every ticket blocking it is closed; the **frontier** is the open, unblocked, unclaimed children. A session **claims** a ticket by assigning it *before* any work, so concurrent sessions skip it. The child graph doubles as a live progress dashboard: read it as an N-of-M closed count (8 / 9), the necessary signal. But the terminal spec handoff waits until every child is closed *and* no destination-bound fog remains in *Not yet specified* (see *Plan, don't do*).

## Ticket types — where the other islands plug in

Every ticket is **HITL** (worked *with* a human who speaks for themselves) or **AFK** (agent alone). Wayfinder is the capstone that dispatches to the rest of the archipelago:

- **Research** (AFK): a fact a decision waits on. Resolved by a [`research`](../research/SKILL.md) subagent that leaves a human-readable gist in the ticket comment as the top disclosure layer and links the committed findings file beneath it; the link alone is too low-res to act on. Delegation depth is one: a research subagent may not invoke Wayfinder or spawn another research subagent. Set a round/token ceiling before dispatch, and never use a paid or credentialed backend without the operator's explicit approval or a pre-authorized enforced budget.
- **Prototype** (HITL): "how should it look / behave?" Raise fidelity with a [`prototype`](../prototype/SKILL.md) built against the real code seams it will integrate into: reuse the existing reducer, components, and route, not an isolated throwaway; a divorced prototype gives no real fidelity signal. Link it as an asset.
- **Grilling** (HITL): conversation, the default. Invoke [`grill`](../grill/SKILL.md) and [`domain-modeling`](../domain-modeling/SKILL.md). The agent never answers the human's side.
- **Task** (HITL or AFK): manual work that must happen before a decision can be made (sign up for a service, provision access, move data so its shape is visible). The one type that *does*; it earns its place by unblocking a decision.

A ticket's type is a guess until you're in it: if work reveals a Grilling ticket is really "how should it look / behave" (or a Prototype is really a schema/logic call), **re-type it in place**; never force the wrong ceremony onto it. Keep the same issue, its id, and its blocking edges; swap only the `wayfinder:<type>` label and the ceremony you run, and carry the findings so far into the ticket as context. Because nothing closes, nothing auto-unblocks its dependents and the N-of-M count is untouched; the ticket simply stays open on the frontier as its new type. Re-typing changes the ceremony, never the decision: no answer is recorded and nothing enters Decisions-so-far until the ticket is genuinely resolved as its corrected type. If the swap flips an AFK ticket (e.g. Task) into a HITL type, re-check the Session preconditions *at the swap*: an AFK or no-human session must defer the now-HITL ceremony to a session where a human is present, not carry on into it.

Every HITL type needs a human actually present; see Session preconditions below.

## Fog of war

The map is *deliberately* incomplete; don't chart what you can't yet see. Resolving a ticket clears the fog ahead of it, graduating whatever's now specifiable into fresh tickets. The test of **fog vs ticket** is whether you can state the question *precisely now*, not whether you can answer it. Ticket when the question is sharp (even if blocked); leave it in **Not yet specified** when it isn't. Fog only gathers *toward* the destination; work beyond the destination is **Out of scope**: closed, never graduating.

## Session preconditions

Charting and every HITL ticket type need a human actually present to speak for themselves; verify that before Step 1. An AFK or spawned session with no human present must not fabricate the human's side: it may only fire Research subagents and file Task tickets, deferring all Prototype/Grilling/domain-modeling charting to a session where a human has resumed.

## Invocation

**Chart the map:** name the destination (grill + domain-modeling: the destination fixes scope, settle it first); grill again breadth-first to surface the frontier; create the map; create the tickets you can specify now, then wire blocking in a second pass; fire research subagents; stop: charting resolves nothing.

**Work through the map:** load the low-res map; choose the frontier ticket (claim it first); resolve it, zooming into related tickets on demand and invoking the skills Notes names; before recording, re-read the ticket; if it's now assigned elsewhere or already carries a resolution, another session got there first: abort, post your answer as a flagged alternative, and surface the conflict on the map instead of overwriting; otherwise record the resolution (answer comment, close the issue, append a context pointer to Decisions-so-far); graduate any fog the answer sharpened.

**Never resolve more than one ticket per session** (except research). One session, one decision: that is what keeps the map honest. *Creating* tickets is the opposite: uncapped and encouraged. When a decision you can't take here surfaces mid-ticket, file it as a fresh ticket and wire its blocking rather than resolving it inline or letting it slip.

The `wayfinder:map` issue is itself **exempt** from the one-resolve cap; it is the index, not a decision ticket. The terminal spec handoff + map close happen once the **last child ticket** is closed (which lands under the cap in its own session); the handoff-and-close may run in that same session or a fresh one (the operator's call) and does not count as a second resolution.

Enforced-vs-advisory: the claim (assign-before-work), the one-ticket-per-session rule, and the `wayfinder:*` labels are **advisory and cooperative**: nothing on the tracker mechanically blocks an unclaimed pickup or a multi-ticket session. The assigned ticket is the evidence each session reads before acting; the enforcement is each session honoring it. The tracker's native blocking only *renders* the frontier; it doesn't bar a violation. State this the way [`lane-claim`](../lane-claim/SKILL.md) does; a reader must not infer a mechanical lock the tracker doesn't provide. The recovery convention narrows this race but does not fully close it: re-read-before-record catches the sequential case (you see the other session's committed resolution), but a truly simultaneous double-record (both sessions re-read clean, then both write) is a residual open window this cooperative scheme cannot bar. So never clobber a resolution that appears after your claim: flag your answer as an alternative and surface the conflict instead. For the same-instant collision the convention cannot prevent, the owner is defined by discovery: the session that loads the map and finds the doubled state (two gists, or a ticket resolved twice) reconciles it: reopen the ticket, merge the two answers into one recorded decision, and re-close it once.

**No authority without evidence. A decision lives in exactly one ticket; the map only points.**
