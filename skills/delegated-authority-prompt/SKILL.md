---
name: delegated-authority-prompt
description: Compose a minimum-question, maximum-authority delegation prompt — front-load the context, constraints, and decision rights so an agent runs far without check-ins, bounded by explicit stop conditions that make that autonomy safe. Use when handing a task to an agent to run unattended and the user says "delegate this", "write a delegation prompt", "hand this off to run", "let it run without checking in", or "minimum questions, maximum authority". Differentiator - the deliberate inverse of grill; grill front-loads the questions, this front-loads the answers and grants the rest as decision rights, with tripwires the only safe way to trade check-ins for reach.
disable-model-invocation: true
---

# Delegated Authority Prompt — front-load the answers, grant the rest

[`grill`](../grill/SKILL.md) and this island are mirror images. Grill reaches shared understanding by asking *you* every question before the build; this reaches it by **answering** those questions inside the prompt, so a delegated agent never has to stop and ask. Grill's yield is questions; this yield is a **mandate** — a brief that grants an agent authority to run far without check-ins, made safe by the stop conditions that bound it.

The trade is exact: every question you would have asked becomes one of three things — front-loaded context, a granted decision right, or a named stop condition. Nothing is left to a mid-run check-in you didn't choose.

The one law: **authority is only as safe as its stop conditions.** Maximum autonomy without tripwires is not delegation, it's abdication. Grant wide reach; bound the blast radius explicitly.

## The five slots

A delegation prompt is five slots. Fill them and the agent runs.

1. **Objective + definition of done** — the completion criterion, checkable and exhaustive (see [`writing-for-agents`](../writing-for-agents/SKILL.md)). The load-bearing slot: a fuzzy *done* invites either premature completion or endless churn, and a delegated agent has no one to ask which.
2. **Context pack** — everything the agent would otherwise stop to ask: the facts, the constraints, the environment, the *why* behind each. Front-load the non-obvious; leave one-command lookups to the environment (it is a source of truth too). A question you pre-answer is a check-in you deleted.
3. **Decision rights** — what the agent may decide unilaterally, each with the default to pick when unsure. This *is* the authority grant: name the space it owns so it doesn't stall at every fork.
4. **Stop conditions** — the tripwires that make the grant safe. The agent runs free until it hits one, then halts and escalates. These bound the blast radius; without them, wide authority is unbounded risk.
5. **Evidence contract** — what to capture to prove each claim, and the honesty rule: mark unverified work `unverified`, never launder it into `verified`. A delegated agent that self-reports "done" with no captured check has earned no authority.

## Composing — drain the question list

Compose the mandate by draining the questions you would otherwise grill. For each:

- **Answerable from the environment or your own knowledge?** → front-load it into the context pack.
- **A judgment the agent can safely own?** → grant it as a decision right, with a default.
- **A fork where a wrong turn is expensive or irreversible?** → make it a stop condition, not a decision right.

When the list is empty, no open question remains that would force an unplanned check-in. That is the minimum-question property: you asked yourself everything up front so the agent need ask nothing.

## Stop conditions — enforced vs advisory

A tripwire is worth only what enforces it. State for each which it is — never imply:

- **enforced** — a mechanism actually halts on it: a guard hook that blocks the tool call, a required-approval gate, a sandbox that denies the operation. [`agent-guardrails`](../agent-guardrails/SKILL.md) is how a limit becomes mechanically impossible to cross rather than politely requested. Verify before you label: run the tripwire against a probe that *should* trip it and confirm the harness actually halts — many harnesses do not hard-stop a child agent on a budget/round cap, they only nudge. If you cannot confirm the stop fires, it is advisory.
- **advisory** — the prompt asks the agent to stop and only its compliance holds the line. Most "check in before X" lines are advisory, and so is a budget/round cap until you have proven the harness enforces it; say so, and never dress an advisory tripwire as enforced.

Default tripwires to include: irreversible actions (delete, deploy, spend, send), scope drift beyond the objective, the definition of done unreachable without a new decision, and the budget/round cap. Carve-out: when the irreversible action *is* the objective (a cleanup that deletes, a deploy you were sent to run), don't route every item to escalation — that is abdication in reverse. Scope it as a decision right with a safe default (e.g. "delete a branch fully merged to main with no open PR — default SKIP if unsure") and reserve the tripwire for the genuinely ambiguous instances.

## The mandate template

```
# MANDATE: <objective>
Definition of done: <checkable, exhaustive completion criterion>

## Context you already have
<facts, constraints, the why — everything not one lookup away>

## You decide (unilaterally)
- <decision> — default when unsure: <default>

## Stop and escalate when
- <tripwire> — [enforced by <mechanism> | advisory]

## Evidence to capture
<what proves each claim; mark anything you could not verify `unverified`>
```

## Where it sits

Not a build loop and not an interview — it composes the prompt, the one thing the neighbours don't. Pair it: run [`grill`](../grill/SKILL.md) first when the brief is thin (you can't delegate a decision you haven't made), then compose the mandate; [`gauntlet-loop`](../gauntlet-loop/SKILL.md) is a build method a mandate can hand to; and a mandate's stop-and-escalate for a stakeholder's call is exactly where [`to-questionnaire`](../to-questionnaire/SKILL.md) picks up.

**No authority without evidence — and no delegated authority without the stop conditions that bound it.**
