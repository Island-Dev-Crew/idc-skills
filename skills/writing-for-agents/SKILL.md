---
name: writing-for-agents
description: Reference for the universal levers of writing any document an agent reads — an AGENTS.md or CLAUDE.md, a rules file, a doc reached by a pointer. Use when editing AGENTS.md / CLAUDE.md / rules files, or when another skill needs the agent-writing vocabulary. Differentiator - the universal levers live here; skill authoring routes to idc-skill-authoring, which points back to this island for these levers.
---

# Writing for Agents: the universal levers

The single source of truth for how to write any one document an agent consumes. The packaging differs (a skill, an `AGENTS.md`, a `CLAUDE.md`, a rules file, a pointer-reached doc), but the writing does not: the same levers make each one **predictable**, the agent taking the same *process* every run, not producing the same output. When the document is a **skill**, read [`idc-skill-authoring`](../idc-skill-authoring/SKILL.md) for the skill-only mechanics (folder anatomy, invocation, router skills, Codex sidecars, fleet distribution). Everything else is here. Arbitration across two independently-authored documents that both fire on one event is out of scope; that precedence is the installation's own rule-priority convention to state, not a lever this skill supplies.

Lineage: this fuses David Ondrej's and Matt Pocock's public canons and binds them to the IDC rule: *no authority without evidence*, stated enforced-vs-advisory, never implied.

## Context pointers

A **context pointer** is a reference held in the agent's context that names out-of-context material and encodes the condition for reaching it. A skill's description is one; a line in `AGENTS.md` naming a doc is the same object. **The pointer's wording, not its target, decides when the agent reaches the material, and how reliably.** A must-have target behind a weakly-worded pointer is a variance bug: sharpen the wording first; inline the material only if sharpening fails.

A pointer does two jobs: state what the material is, and list the **branches** that should trigger reaching it (a branch is a distinct case the document handles; different runs take different paths). Every word of an always-loaded pointer costs every turn, so it earns harder pruning than the body:

- **Front-load the leading word**: the pointer does its triggering work there.
- **One trigger per branch.** Synonyms renaming a single branch are one branch written twice; collapse them.
- **Branch is keyed to the condition, not the action.** N distinct recognizable conditions that share one downstream action are N branches, each keeping its own trigger: auth, authz, encryption, input-validation, and secrets-handling stay five triggers even though all five route to the same review skill. The collapse rule above fires only on true synonyms of one branch.
- **Cut identity the body already carries.**

## The two loads

Every document and pointer spends one of two budgets. Name which before you spend it.

- **Context load**: always-loaded material on the agent's window: an `AGENTS.md` line, a skill description, anything in context every turn, spending tokens and attention whether or not it fires.
- **Cognitive load**: the cost on the human: which documents exist and when to reach for each. The human is the index. Not a cost to minimise. It is the price of human agency; spend it where human judgement matters, remove it where it does not.

Material reached only through a pointer escapes context load at the price of the pointer's line; material with no pointer rides entirely on cognitive load.

## Information hierarchy

A document is **steps** (ordered actions the agent performs) and **reference** (definitions, rules, facts consulted on demand), mixing freely: all steps (a recipe), all reference (a review's rules), or both. The core decision is where each piece sits on the **information hierarchy**, a ladder ranked by how immediately the agent needs it:

1. **In-file step**, the primary tier: what the agent does, in order.
2. **In-file reference**: consulted on demand; often a legitimately flat peer-set (every rule on one rung), a fine arrangement.
3. **Disclosed reference**: pushed into a separate file, reached by a pointer, loaded only when the pointer fires, from a sibling file through fully external reference any document can point at.

Push too little down and the top bloats; push too much and you hide material the agent needs. That tension is the whole decision. **Progressive disclosure** is the move down the ladder so the top stays legible; its main job is protecting the hierarchy, not optimising tokens. Branching is the cleanest disclosure test: inline what every branch needs, push behind a pointer what only some reach. **Co-location** is the within-file companion: keep a concept's definition, rules, and caveats under one heading so reading one part brings its neighbours. The test: the document should read like documentation written for the agent. That's a design heuristic for shaping the hierarchy, not a completion criterion; see the next section for how "done" actually gets decided.

## Steps and completion criteria

Every step ends on a **completion criterion**: the condition that says the work is done. Two properties make it a lever:

- **Clarity**: can the agent tell done from not-done? A vague bound ("understanding reached") invites **premature completion**: ending early, attention slipping to *being done*. The visible **post-completion steps** supply the pull; the criterion's clarity is the resistance. Defend in order: sharpen the bound first (local, cheap); only if it's irreducibly fuzzy *and* you see the rush, hide later steps by splitting across a real context boundary (a hand-off or subagent; an inline call clears nothing). Some bars never reduce to a checkable bound; pick the nearest mechanical proxy you can verify (a checklist, a reviewer pass, a second read) and say plainly that the proxy stands in for the judgment call, not the reverse.
- **Demand**: how much it requires. "Every modified model accounted for" forces thorough **legwork** where "produce a change list" does not, and demand is not step-bound: "every rule applied" binds a body of flat reference just as "every step done" binds a sequence.

The strongest criteria are both checkable and exhaustive.

## Leading words

A **leading word** is a compact concept already living in the model's pretraining that the agent thinks with while running the document (*lesson*, *fog of war*, *tracer bullet*, *tight*, *red*). Repeated as a token, never as a sentence, it accumulates a distributed definition and anchors a whole region of behaviour in the fewest tokens, by recruiting priors the model already holds. Coining your own works only if you define it clearly; a made-up word recruits no priors, so reach for an existing one first.

It anchors twice: in the body, *execution* (the agent reaches for the same behaviour every time the word appears); in a pointer, *invocation* (when the same word lives in your prompts, docs, and code, the agent links that shared language to the material and reaches it more reliably). Hunt restatements begging to collapse into one token: "fast, deterministic, low-overhead" → *tight*; "a loop you believe in" → *red* (a fuzzy gate becomes a binary observable state). You win twice: fewer tokens, a sharper hook.

## Pruning

- **Single source of truth.** Keep each meaning in one authoritative place, so changing behaviour is a one-place edit. **Duplication** (one meaning in two places) costs maintenance and tokens and inflates a meaning's rank on the ladder past its worth.
- **The environment is a source of truth too**: `package.json` scripts, config, directory layout, `--help`. A document restating it is a **cache**, earning its load only when the lookup is expensive. Cache what the agent can't find by looking (the unwritten convention, the reason behind a choice, the gotcha no config confesses); leave one-command lookups to the environment, where they can't go stale.
- **Relevance.** Check every line: does it still bear on what the document does? Without pruning the default fate is **sediment**: stale layers that settle because adding feels safe and removing feels risky.
- **No-ops.** Hunt sentence by sentence: a line the model already obeys by default pays load to say nothing. The test (does it change behaviour versus the default?) is model-relative; settle a dispute by running the document, not debating. A leading word too weak to beat the default (*be thorough* to an already-thorough agent) is a no-op; the fix is a stronger word (*relentless*), not a new technique.

## Failure modes

- **Sprawl**: too long, even when every line is live. Attention thins; cure with the ladder (disclose behind pointers, split by branch or sequence).
- **Negation**: steering by prohibition drags the forbidden behaviour into context and makes it *more* available (*don't think of an elephant*). Prompt the **positive**: state the target behaviour so the banned one is never spoken. Keep a prohibition only as a hard guardrail you can't phrase positively, paired with the positive target.

## The IDC layer

Beyond predictability, an agent doc in this archipelago carries the evidence discipline. State **enforced-vs-advisory** for every rule: say whether a hook actually blocks it or it's guidance. Never launder `unverified` into `verified`. Ground the document's vocabulary in the repo's [`CONTEXT.md`](../../CONTEXT.md) ubiquitous language (named seats, no-authority-without-evidence) so every agent doc speaks one tongue, the same grounding [`wait-what`](../wait-what/SKILL.md) reaches for when an answer stops making sense.

**No authority without evidence. The pointer's wording is the variance lever.**
