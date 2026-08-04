---
name: idc-skill-authoring
description: The IDC canon for writing, editing, reviewing, and distributing agent skills — anatomy, progressive disclosure, leading words, the two loads, failure modes, and fleet distribution. Read whenever a SKILL.md is being created, edited, reviewed, or debugged, or the user says "create a skill", "new skill", "improve this skill", "why isn't my skill triggering", or "distribute this skill". Differentiator - this is the island that authors every other island; it fuses the Ondrej and Pocock canons and adds IDC's evidence discipline and fleet distribution.
---

# IDC Skill Authoring — the canon

This is the first island. Every other skill in this archipelago was authored under it, and any new one should be. It fuses two public canons — David Ondrej's *effective-agent-skills* (anatomy, checklists, security) and Matt Pocock's *writing-great-skills* (the vocabulary of predictability) — and binds them to the IDC rule: **no authority without evidence.** A skill claims a discipline; it earns the claim by demonstrating that discipline in its own construction.

A skill exists to wrangle **determinism** out of a stochastic system. The root virtue is **predictability** — the agent taking the same *process* every run, not producing the same *output*. Every lever below serves it.

## 1. What a skill is

A folder with a `SKILL.md` (YAML frontmatter + markdown), plus optional `scripts/`, `references/`, and `assets/` loaded on demand.

```
my-skill/
├── SKILL.md          # required: metadata + instructions
├── scripts/          # optional: deterministic code (validators, helpers)
├── references/       # optional: detail loaded only when a pointer fires
└── assets/           # optional: templates, static files
```

Progressive disclosure is the architecture. Three tiers:

- **Discovery (~100 tokens, always loaded):** only `name` + `description` sit in the system prompt. The agent knows the skill exists and when it applies.
- **Activation (<5k tokens, on match):** the request matches the description; the agent reads the full `SKILL.md`.
- **Execution (unbounded, on demand):** the agent reads `references/*` or runs `scripts/*` only as needed. Files cost nothing until accessed.

**The description routes; the body executes. Get both right independently.**

## 2. The two loads

Every design choice spends one of two budgets. Name which before you spend it.

- **Context load** — tokens sitting in the window every turn. A **model-invoked** skill (no `disable-model-invocation`) keeps its description live so the agent — or another skill — can fire it autonomously. That reach costs context every turn.
- **Cognitive load** — *you* remembering the skill exists. A **user-invoked** skill (`disable-model-invocation: true`) strips the description from the agent's reach; only you, typing its name, invoke it. Zero context load, but you become the index.

Pick model-invocation only when the agent must reach the skill on its own, or another skill must. If it only ever fires by hand, make it user-invoked and pay no context load. When user-invoked skills outnumber what you can remember, cure the pile-up with a **router skill**: one user-invoked skill that names the others and when to reach each.

## 3. Writing the description

Three jobs, no more: **what** the skill does, **when** to use it (trigger phrases), and the **differentiator** vs neighbours (prevents routing conflicts).

Pattern: `X via Y. Use for [situations]. Differentiator - [no Z / faster than W / handles V].`

- **Front-load the leading word** — the description does its invocation work there.
- **One trigger per branch.** Synonyms renaming one branch are duplication; collapse them.
- **Never summarize the workflow.** If the description lists the steps, the agent follows the summary and skips loading the body. Describe *what* and *when*, never *how*.

YAML traps that silently prevent loading:
- `name` is lowercase-hyphen, 1–64 chars, **exactly the folder name**.
- No `<` or `>` in frontmatter — they can inject into the system prompt.
- Never put `: ` (colon-space) inside an unquoted `description` — strict parsers (Pi's) reject it as a nested mapping. Use ` - ` or single-quote the whole value and double inner apostrophes.

## 4. Information hierarchy — the ladder

Content is **steps** (ordered actions) and **reference** (definitions, rules, facts). They mix freely. Rank each by how immediately the agent needs it:

1. **In-skill step** — an ordered action in `SKILL.md`. Each ends on a **completion criterion**: the checkable condition that says the work is done. Make it *checkable* (can the agent tell done from not-done?) and, where it matters, *exhaustive* ("every modified module accounted for", not "produce a change list"). A vague criterion invites **premature completion**.
2. **In-skill reference** — a rule consulted on demand, often a legitimately flat peer-set.
3. **External reference** — pushed into a linked file, reached by a **context pointer**, loaded only when the pointer fires. The pointer's *wording*, not its target, decides how reliably the agent reaches it.

**Progressive disclosure** is the move down the ladder so the top stays legible. The cleanest test is the **branch**: inline what every branch needs, push behind a pointer what only some reach. Keep references **one level deep** — never chain `SKILL.md → a.md → b.md`; the agent may preview nested files only partially and miss the payload. **Co-locate**: keep a concept's definition, rules, and caveats under one heading.

## 5. Do this

- **Bash-first, prose-second.** Concrete commands with inline comments beat explanation. The agent pattern-matches on syntax. Show, don't describe.
- **Push determinism into code.** Anything fragile, repetitive, or where variation is a bug → a script. Markdown is for judgment only.
- **Match strictness to fragility.** Loose heuristics when many approaches are valid (review); templates when there's a preferred pattern (report format); exact scripts and strict step lists when a wrong move is costly (migrations, ceremonies).
- **Build a validation loop.** The single biggest quality lever: state a verify → fix → re-verify loop explicitly. Code skills: tests green + zero type errors. Document skills: a visual QA pass. Data skills: schema validation.
- **State-check before action.** Don't assume setup exists. Verify state with a command, then branch.
- **Leading words.** A **leading word** is a compact concept already in the model's pretraining (*tracer bullet*, *fog of war*, *red*, *tight*) that anchors a whole region of behaviour in the fewest tokens. It serves predictability twice — anchoring execution in the body, anchoring invocation in the description. Hunt restatements ("fast, deterministic, low-overhead" → *tight*) and collapse them into one pretrained token. You win twice: fewer tokens, a sharper hook.
- **Compose primitives, don't bundle workflows.** One skill = one capability or one discipline. Multiple small skills combine at runtime; one large skill is rigid.
- **Persistent artifacts for cross-session memory.** Skills can write repo-level files (CONTEXT.md, ADRs, a finding register) that future sessions read. That is how you give memoryless agents a memory.

## 6. Don't do this — the failure modes

Diagnose a struggling skill against these:

- **Premature completion** — ending a step before it's genuinely done. First sharpen the completion criterion (cheap, local); only if it's irreducibly fuzzy *and* you see the rush, hide the post-completion steps by splitting.
- **Duplication** — the same meaning in two places. Costs maintenance and tokens, and inflates a meaning's rank on the ladder past its worth. Keep every meaning in a **single source of truth**.
- **Sediment** — stale layers that settle because adding feels safe and removing feels risky. The default fate of any skill without pruning discipline.
- **Sprawl** — simply too long, even when every line is live. Cure with the ladder: disclose reference behind pointers, split by branch or sequence.
- **No-op** — a line the model already obeys by default. The test: does it change behaviour vs the default? *Be thorough* to an already-thorough agent is a no-op; the fix is a stronger word (*relentless*), not a new technique. Also don't re-teach what the model knows (no Python syntax, no "what is git").
- **Negation** — steering by prohibition backfires; *don't think of an elephant* names the elephant. Prompt the **positive**; keep a prohibition only as a hard guardrail you can't phrase positively, and pair it with what to do instead.

Structural bans: no human-facing docs inside a skill folder (no README/CHANGELOG); no bundled library source (install it); no absolute paths (relative, forward slashes); no time-sensitive facts ("as of Q4" rots — fetch live or omit).

## 7. When to split

**Granularity** spends a load per cut, so split only when the cut earns it:
- **By invocation** — split off a model-invoked skill when a distinct leading word should trigger it, or another skill must reach it. You pay context load for the new always-loaded description; the reach must be worth it.
- **By sequence** — split a run of steps when the steps still ahead tempt the agent to rush the one in front (premature completion). Hiding them encourages more legwork on the current task.

## 8. Fleet distribution — one authored skill, every seat

Ondrej's four-agent layout (Codex / Claude / Pi / Hermes) maps one-to-one onto the IDC fleet. Author once at the canonical location; symlinks and one copy cover the rest.

| Seat | Skills folder | Notes |
|---|---|---|
| Codex / OpenAI | `~/.agents/skills/` | **canonical** — author here first |
| Claude Code | `~/.claude/skills/` | symlink → `~/.agents/skills/` — auto-covered |
| Pi | `~/.pi/agent/skills/` | symlink → `~/.agents/skills/` — auto-covered (path is `/agent/` nested) |
| Hermes | `~/.hermes/skills/` | independent copy — the only manual one |

```bash
SKILL=<skill-name>
# 1. author in ~/.agents/skills/$SKILL/SKILL.md (canonical)
# 2. verify the .claude symlink once:
ls -la ~/.claude/skills   # expect: ~/.claude/skills -> ~/.agents/skills
# 3. copy to Hermes only (.claude and .pi are symlinks — already covered):
rsync -a --delete ~/.agents/skills/$SKILL/ ~/.hermes/skills/$SKILL/
# 4. verify all four report identical byte counts:
for p in ~/.agents/skills ~/.claude/skills ~/.pi/agent/skills ~/.hermes/skills; do
  echo "$p/$SKILL: $(wc -c < $p/$SKILL/SKILL.md) bytes"; done
```

Traps: `~/.pi/skills/` is the wrong path (Pi loads `~/.pi/agent/skills/` only); `~/.claude/skills` is a symlink, not a folder (a `cp` into it errors "are identical" — skip it); Hermes snapshots skills at session start (restart to see a new one); `SKILL.md` casing matters on case-sensitive volumes. Removing a skill globally is destructive — `rm -rf` from `~/.agents/skills/` (covers the two symlinks) and `~/.hermes/skills/`, and confirm with the user first.

## 9. Ship checklist

- [ ] `name` matches the folder; frontmatter YAML is valid (no `: ` in an unquoted description, no `<`/`>`)
- [ ] description = what + when + differentiator + real trigger phrases; no workflow summary
- [ ] one concern per skill; composes cleanly with neighbours
- [ ] completion criteria are checkable, and exhaustive where it matters
- [ ] a validation loop is documented
- [ ] relative paths only; no human-facing docs, no time-sensitive facts, no bundled library source
- [ ] pruned: no duplication, no no-ops, no negations left unpaired
- [ ] tested for triggering (does it fire from a natural request?) and execution (is the output right?), against the **weakest** model you'll deploy on
- [ ] if it encodes an evidence discipline, it demonstrates that discipline in its own construction

**No authority without evidence. A skill demonstrates its own discipline.**
