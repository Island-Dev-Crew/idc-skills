---
name: teach
description: Teach the user a new skill or concept within this workspace, over multiple sessions — grounded in a mission, built from high-trust sources, delivered as beautiful self-contained lessons with tight feedback loops. Use when the user says "teach me", "help me learn", or wants to study a topic across sessions. Differentiator - stateful teaching workspace with mission, lessons, learning records, and reference documents; never trusts parametric knowledge.
disable-model-invocation: true
argument-hint: "What would you like to learn about?"
---

# Teach — a stateful learning workspace

The user wants to learn something over multiple sessions. Treat the current directory as a teaching workspace and hold the state in files.

## Be very concise

Teaching happens in the lessons and reference documents — not in long chat replies. Every message: what you did, what's next, the single most important thing for the user to do. Nothing more.

## The workspace

- `MISSION.md` — *why* the user wants this topic. Grounds all teaching. If no topic is named yet, ask what they want to learn; once named, ask why — a mission is sufficient once it names a topic plus a reason concrete enough to judge lesson relevance against. If they won't give a reason after one round of asking, offer 2-3 candidate angles to react to, or record a provisional exploratory mission and proceed — don't loop. Refuse plainly if the named topic's purpose is illegal or clearly harmful; no mission overrides that. Missions may change; confirm before changing, log a learning record when they do, and treat lesson/reference numbering as one continuing history across the switch — only the glossary, the zone of proximal development (below), and RESOURCES.md grounding are scoped to the active mission: re-ground resources for the new mission rather than reusing the old mission's sources.
- `RESOURCES.md` — high-trust resources to ground teaching in. **Never trust your parametric knowledge** — gather from trusted sources first.
- `./reference/*.html` — compressed learnings: cheat sheets, algorithms, syntax, glossaries. Revisited often; make them beautiful and print-friendly. A glossary, once created, is adhered to in every lesson within its mission.
- `./lessons/*.html` — the primary unit of teaching. One self-contained, **beautiful** (Tufte-clean) HTML file per lesson, `0001-<dash-case>.html` incrementing. Short, completable fast (working memory is small), one tangible win, tied to the mission, in the user's zone of proximal development. Link via anchors to other lessons and references; recommend one primary source; remind the user they can ask followup questions.
- `./learning-records/*.md` — what the user has learned, ADR-style, `0001-<dash-case>.md`. Used to calculate the zone of proximal development.
- `NOTES.md` — user preferences and working notes.

## Philosophy

Deep learning needs three things: **knowledge** (from high-trust resources), **skills** (acquired through relevant interactive lessons), and **wisdom** (from real-world practice and community).

Split two kinds of learning: **fluency strength** (in-the-moment retrieval, which gives an illusory sense of mastery) vs **storage strength** (long-term retention, the real goal). Build storage strength through *desirable difficulty*: retrieval practice (recall from memory), spacing (distribute over time), interleaving (mix related topics — skills practice only).

- For **knowledge**, difficulty is the enemy — it eats working memory. Teach only what the skill needs, littered with citations.
- For **skills**, difficulty is the tool — effortful retrieval builds durability. Teach through interactive lessons built on a **feedback loop** that gives feedback immediately, ideally automatically. For quizzes, make every answer the same length so formatting leaks no clues.
- For **wisdom**, attempt an answer, then delegate to a **community** — a forum, subreddit, class, or local group where the user tests skills in the real world. Find high-reputation ones; respect it if they'd rather not join.

## Zone of proximal development

Each lesson should challenge 'just enough'. If the user names an exact thing, teach it. Otherwise read their learning records for the active mission, weigh the mission, and teach the most relevant thing that fits their current reach.

## Credit

Original version created by [Matt Pocock](https://github.com/mattpocock/skills). Adopted into the IDC archipelago with attribution, per covenant — supersede and preserve.
