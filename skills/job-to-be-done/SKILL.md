---
name: job-to-be-done
description: The pre-build triage that asks whether a thing should be built or automated at all, and where the human stays in the loop — the delegation, complexity, and outcome questions, the 90/10 rule, and augment-don't-just-automate. Use before building an automation, agent, or tool, or when the user mentions "should I build this", "job to be done", "is this worth automating", "do I need an agent", or is about to over-engineer. Differentiator - an advisory triage positioned upstream of grill and spec-pipeline, not a mechanical gate; its best outcome is often "don't build it".
---

# Job To Be Done: should this be built at all?

The upstream triage, advisory and not wired in. Nothing invokes it automatically, so run it yourself before [`grill`](../grill/SKILL.md) interrogates *how* to build a thing and [`spec-pipeline`](../spec-pipeline/SKILL.md) builds it: this island asks whether it should be built at all, because most AI initiatives fail by automating the wrong thing, not by botching execution. Jake Van Clief's framing, welded to the forge: the best outcome here is frequently **"don't build it,"** recorded with its reason.

The leading story: a client asks for a better drill because they dislike the holes it makes. Don't build a better drill. Ask *why they need a hole.* They need to hang a painting. They don't need a drill at all; they need 3M tape. **You could be automating something that never needed to exist.** Optimize the job to be done, not the tool someone named.

## The three questions

Put every candidate through these before a line is built:

1. **Delegation**: is your time better spent on this, or offloaded? Being the expert in AI for your domain does not mean you are the one who should build it. Weigh opportunity cost; sometimes the answer is *hire a person and direct them.*
2. **Complexity**: does this need the complexity being proposed? A swarm, an n8n flow, a custom Python service, a vector DB, each is a *solution to a specific problem* (scheduling, triggers, retrieval). If you can't name the problem it solves for *you*, you don't need it. "Just pay for the tool" (Monday, Zapier) is often cheaper than rebuilding it. Exception: when the complex thing is the deliverable product itself, apply this test to the product's users' job to be done, not the builder's; the swarm being the product is a pass, not a red flag.
3. **Outcome**: what is the actual outcome, and is automation the shortest path to it? Often a structured folder plus one agent gets the same outcome as the software someone wanted to build, so skip the software.

**When several candidates pass**: a build verdict isn't a scheduling decision. Sequencing across candidates is out of scope here; break ties with the Delegation question's opportunity-cost lens.

## The 90/10 rule

Aim for **~90% ordinary process and code, ~10% AI on top**. The 90% is deterministic, inspectable, and cheap; the 10% is where the AI makes it feel like magic. Teams that invert this, with AI doing everything, get hollow output and token burn. Engineers already work this way; it's why their pilots survive. A hard external constraint (regulatory, compliance, safety) can legitimately push the split past 90/10; when it does, record the constraint in the verdict reason alongside the split.

## The ladder: how much structure is warranted

Automation has rungs: **chat → saved prompt or skill → folders + one agent → framework code.** Climb only when the rung below is genuinely automated *and* repeating. A workflow done twice is scaffolding, not architecture, and if the whole job fits in one saved prompt, that prompt *is* the answer; don't build a workspace around it. The Complexity question is really "which rung does this actually need?", and the honest answer is usually one rung lower than what was proposed. (The ladder triages *which* rung; [`folder-workspace`](../folder-workspace/SKILL.md) owns how to build the top one.)

## Augment, don't just automate

The goal is **augmentation**, amplifying a human, not pure automation that removes them. If you automate everything, you built a tool, not a leverage system, and you lost the human judgement that was the durable value ([`productionize-opinion`](../productionize-opinion/SKILL.md)). Humans are compute-efficient: a $40k/year person copy-pasting can beat an API bill and a fragile pipeline. Keep the human in the compute layer where judgement matters; put the machine where the toil is.

## The one question to ask first

*"What is one workflow you would hand off tomorrow, that you'd give away because you don't want to deal with it, but that is genuinely important?"* Start there. That workflow is the real job to be done.

This island is **entirely advisory**: nothing here is mechanically enforced; it is a thinking gate, and its only output is a recorded verdict a human weighs. Say so; don't imply a triage question blocks anything.

**Done when** the candidate has a stated verdict (build / delegate / buy / don't-build) with the reason recorded, and (if building) the 90/10 split, the rung on the ladder the build lands on (saved prompt / folder + one agent / framework), and the point where the human reviews are named. A "don't-build" verdict with its reason is a *successful* outcome of this island, not a failure.

**No authority without evidence. The decision not to build is a decision; record it with its reason.**
