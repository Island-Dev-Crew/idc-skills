---
name: prototype
description: Build a throwaway prototype to answer one design question — a single shareable HTML file for a logic/state question, or several switchable UI variants for a look question — then fold the answer into main and keep the prototype itself as evidence on a throwaway branch. Use when the user wants to sanity-check whether a state model feels right, or explore what a UI should look like, or says "prototype", "mock this up", "spike it", or "let's see it". Differentiator - throwaway code that answers a question; the prototype is a primary source you can re-run, not a deleted sketch.
---

# Prototype — throwaway code that answers a question

A prototype is **throwaway code that answers a question.** The question decides the shape, and getting the shape wrong wastes the whole prototype. Distinct from [`spec-pipeline`](../spec-pipeline/SKILL.md), which builds the real thing — a prototype builds a *disposable* thing to learn one fact fast, then throws the code away and keeps the fact.

## Pick the branch — the question decides

Identify which question is being answered, from the prompt, the surrounding code, or by asking if the user is around:

- **"Does this logic / state model feel right?"** → build a **single shareable HTML file**: free-play buttons plus a few tabbed guided walkthroughs that push the state machine through the cases that are hard to reason about on paper, drivable by a non-developer. One file they double-click — no build step.
- **"What should this look like?"** → generate **several radically different UI variants on one route**, switchable via a URL search param and a floating bottom bar, so the user flips between them and reacts.

The two branches produce very different artifacts. If the question is genuinely ambiguous and the user isn't reachable, default by the surrounding code — a backend module leans logic, a page or component leans UI — and **state the assumption at the top of the prototype.**

## Rules for both branches (advisory — nothing here is mechanically checked)

1. **Throwaway from day one, and marked as such.** Put it next to the code it's prototyping for (context is obvious), but name it so a casual reader sees it's a prototype, not production. Obey the project's routing convention for a UI route; don't invent new top-level structure.
2. **Trivial to run.** One command from the task runner (`pnpm <name>`, `bun <path>`), or a single HTML file the user double-clicks. No thinking required to start it.
3. **No persistence by default.** State lives in memory — persistence is the thing the prototype is *checking*, not something it depends on. If the question genuinely involves a DB, hit a scratch store named `PROTOTYPE — wipe me`.
4. **Skip the polish.** No tests, no error handling beyond what makes it runnable, no abstractions. The point is to learn something fast.
5. **Surface the state.** After every action (logic) or on every variant switch (UI), render the full relevant state so the user sees what changed.

## Capture — the prototype is a primary source

This is the step that makes a prototype worth more than a sketch. When it's answered its question:

1. **Fold the validated decision into the real code** — that's what main keeps.
2. **Capture the prototype itself as a primary source**: commit it to a throwaway branch, *out of main*, and leave a context pointer to that branch on the implementation issue. A prototype that encodes a decision more precisely than prose (a state machine, a reducer, a real interaction) is evidence a reader can *run* — more trustworthy than a paragraph describing it.
3. **Capture the answer**: the verdict and the question it settled, in the issue or a commit.

Main keeps only the validated decision; the disposable code lives on its branch as the primary source, reachable but never merged.

**Done when** the prototype answered its one question, the validated decision is folded into real code, and the prototype is captured on a throwaway branch with the question-and-verdict recorded — not when the prototype is "finished," because a prototype is never finished, only answered.

**No authority without evidence. A prototype you can run beats a paragraph you have to trust.**
