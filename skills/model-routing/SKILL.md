---
name: model-routing
description: Route one task to the cheapest model or tool that still clears its cognitive-demand floor — vision-native vs deep-reasoning vs cheap-bulk — then record why the pick clears the bar. Use when choosing which model runs a step, sizing a model to a task, deciding escalate-vs-downshift after a failure, or the user says "which model", "model routing", "cheapest model that works", "escalate to a bigger model", or "route this to". Differentiator - it selects the model by cognitive demand against a cost floor, where spec-pipeline / archipelago / gauntlet-loop route work between agents and steps but never pick the model a step runs on.
---

# Model Routing — cheapest option above the floor

The orchestration islands decide *what runs next* and *who runs it in parallel*; none of them decide *which model or tool a single step runs on*. That is this island's one concern: given a task, name its cognitive demand, set a **floor** — the minimum capability that produces a correct-enough result — and pick the **cheapest** option that clears it. Then record why, because a routing choice is a claim like any other.

Model-agnostic by construction: route on **axes**, never on a vendor's name. A catalog of model names and prices is a time-sensitive fact that rots — keep it out of this skill and read it from the environment (the provider's live pricing, a `models.json` the caller owns) at decision time.

## The demand axes

Classify the task on the axes it actually loads. Most tasks load one dominantly:

- **Vision-native** — the input *is* an image, PDF, screenshot, chart, or video frame. A text-only model cannot clear this floor at any price; the axis is a hard gate, not a preference.
- **Deep-reasoning** — multi-step proof, architecture, ambiguous spec, long-context synthesis, adversarial review. The floor is a frontier reasoning model; a cheap model fails silently by sounding fluent while being wrong.
- **Cheap-bulk** — classification, extraction, reformatting, routing, short deterministic transforms over many items. The floor is low and volume is high, so overspend here is the common, invisible waste.
- **Tool-not-model** — a regex, parser, SQL query, or deterministic script clears the floor with zero inference. When code is exact and repeatable, routing to *any* model is over-provisioning; route to the tool.

Also floor-setting, independent of axis: **latency** (an interactive path caps how slow a model may be), and **context window** (input that will not fit is a hard gate, same shape as vision).

## The rule

1. **Name the demand.** Which axis dominates, and what is the failure mode if under-provisioned?
2. **Set the floor.** The minimum capability that clears the task — stated as a checkable bar (e.g. "reads the chart's axis labels", "holds 200-pages in context", "matches the labeled set at 95%"), not a vibe.
3. **Pick the cheapest option that clears the floor.** Above the floor, cost decides. Below it, price is irrelevant — a cheaper model that fails the task costs infinity, not less. When multiple gates fire, the floor is the strictest across all of them; pick the cheapest option that clears *every* floor.
4. **Record why.** One line: `task → axis → floor → chosen option → what cleared it`. That line is the evidence the route was reasoned, not guessed.

Escalation is the same rule re-run, not a reflex: when the floor pick fails, the evidence is the *observed failure* (a wrong answer, a refusal, a truncation), and you re-route to the next tier above the floor — carrying the failure as the reason. Downshift symmetrically: if a cheaper tier clears a captured probe, the probe is the evidence to move down.

## Worked routes

Each ends on the recorded line — the artifact that proves the pick was reasoned:

- Extract line-items from 4,000 scanned invoices → **vision-native** (hard gate: input is an image) → floor "reads printed cells from a scan" → cheapest model that clears vision → *cleared: sampled 20 scans, all cells read correctly*.
- Reconcile two conflicting spec documents into one contract → **deep-reasoning** → floor "holds both docs in context and surfaces every contradiction" → frontier reasoning tier → *cleared: caught the three seeded contradictions in a probe*.
- Tag 50k support tickets by product area → **cheap-bulk** → floor "matches the labeled set at 95%" → cheapest small model → *cleared: 96.4% on a 500-ticket labeled probe; the frontier model was over-provisioned*.
- Strip HTML tags from a feed → **tool-not-model** → floor "exact, repeatable" → a parser, no inference → *cleared: deterministic, unit-tested*.
- Reconcile a scanned 300-page contract against its amendments → **three gates fire at once** (vision-native: the input is a scan · deep-reasoning: cross-clause contradictions · context: 300 pages exceeds a small window) → floor is the union "reads scanned pages AND holds the whole document AND surfaces every conflict" → cheapest model clearing *all three* (a long-context vision-capable frontier tier) → *cleared: read a sampled page, held the full doc, caught two seeded amendment conflicts in a probe*.

## Enforced vs advisory

Every rule here is **advisory** — this skill is a reasoning discipline, not a hook; nothing mechanically blocks a wrong route. What makes it auditable is the recorded line: a route with no `axis → floor → why` is `unverified` and must be marked so, never laundered into a justified choice. If you want the floor *enforced*, that is a separate gate the caller wires (a validator that rejects a step whose model is below its declared floor) — say so explicitly rather than implying this skill provides it.

The one falsifiable check this skill offers: for a downshift or a "this cheap model is fine" claim, run the model against a labeled probe that could fail, and keep the output. No probe, no downshift — the claim stays `unverified`. Note the asymmetry: cheap-bulk is probe-verifiable against a labeled set that exists cheaply, while deep-reasoning is floor-by-precaution because a cheap oracle is costly or absent — so it rarely downshifts, and seeded checks (as in the reconcile route above) are its closest available probe form.

**No authority without evidence. A route names its floor and records what cleared it, or it is unverified.**
