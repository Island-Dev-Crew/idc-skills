---
name: to-questionnaire
description: Turn a decision you can't answer alone into a Markdown questionnaire for the one person who can — filled in async, or worked through together. The inverse of grill - it mines someone else, not you.
disable-model-invocation: true
---

# To Questionnaire — mine someone else

The inverse of the [`grill`](../grill/SKILL.md) island. A grill interrogates *you* about the subject; this turns a decision you *can't* answer alone into a **questionnaire** — a Markdown document you hand to the one person who holds the missing knowledge, filled in async or worked through together in a meeting.

**Grill the send, not the subject.** You can't answer questions about the subject — that's the whole point — so interviewing you about it is useless. Interview yourself (via the user) only about the **send**, which you always can answer: who it goes to, and what you need back. The questions in the document then aim at the **gap** between what the recipient knows and what you need.

## Process

1. **Who is it going to?** In one exchange, get the recipient's role, expertise, and relationship to you — this fixes the questionnaire's tone and how much context it must carry. **Done when** you know who the recipient is and what they know that you don't.
2. **What do you need back?** In one exchange, get the specific decisions or facts you can't resolve alone and need from this person. **Done when** you have a concrete list of what you must walk away able to do or decide.
3. **Write the questionnaire.** Draft questions aimed at the gap from steps 1–2, using the structure below. Write it to `to-questionnaire-<slug>.md` in the current directory (slug from the topic) and report the path. **Done when** the file exists and every item named in step 2 is covered by a question.

## Document structure

Frame it as a **discovery questionnaire**: you lack context, the recipient holds it. Order questions most-important-first — async means you may only get one pass — and group under `##` headings by theme once there are more than a handful.

```
# <Questionnaire title>

**Purpose:** why this exists and the decision riding on it.
**From:** <you> — **To:** <the recipient> — **How your answers will be used:** <where they go>

## Context
One paragraph orienting a recipient who wasn't in your head. Enough to answer well, not a page.

## How to answer
Deadline and rough effort. Partial answers and "I don't know" are useful — flag anything you're unsure of rather than skipping it.

## <Theme heading>
One `##` section per theme, questions most-important-first. Every question is one idea — never compound — with an answer stub directly beneath, and a one-line _why this matters_ only where the question could be misread or invite a throwaway answer.

### <A single, non-compound question>
_Why this matters: <only if it could be misread>._
>

## Anything else?
A closing catch-all: anything we didn't ask that we should know?
```

## Why it exists

This is a patch for agents being hard to collaborate with when a stakeholder isn't AI-native — no shared Slack thread to tag an agent into. A Markdown doc travels anywhere: paste it into a Google Doc, hand it over, pull the answers back into the [`grill`](../grill/SKILL.md) or [`spec-pipeline`](../spec-pipeline/SKILL.md) that needed them. A skill to someday delete, when collaboration gets easier.

**No authority without evidence. Grill the send, not the subject.**
