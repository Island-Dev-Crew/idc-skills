---
name: idc-skill-authoring
description: The IDC canon for skills specifically — folder anatomy, progressive disclosure, the invocation choice and router skills, the Codex openai.yaml sidecar, fleet distribution across Codex/Claude/Pi/Hermes, and the evidence discipline. Read whenever a SKILL.md is being created, edited, reviewed, distributed, or debugged, or the user says "create a skill", "new skill", "restructure a skill", "why isn't my skill triggering", or "distribute this skill". Differentiator - the skill-only mechanics live here (authoring and structure); to improve a skill against measured evals, route to skill-tune; for the universal levers that apply to any agent doc, this points to writing-for-agents.
---

# IDC Skill Authoring — the skill layer

The first island: it authors every other one. It is the **skill-specific** layer — folder anatomy, progressive disclosure, invocation, the Codex sidecar, fleet distribution, and the IDC evidence discipline. For the universal writing levers — the two loads, information hierarchy, leading words, completion criteria, pruning, failure modes — read [`writing-for-agents`](../writing-for-agents/SKILL.md), the single source of truth for anything an agent reads. Those levers are not repeated here; a skill is just one kind of agent doc, and the vocabulary lives in one place.

The root virtue is **predictability** — the agent taking the same *process* every run. Everything below serves it, and binds it to the IDC rule: **no authority without evidence.** A skill claims a discipline; it earns the claim by demonstrating that discipline in its own construction.

## 1. What a skill is

A folder with a `SKILL.md` (YAML frontmatter + markdown), plus optional `scripts/`, `references/`, and `assets/` loaded on demand, and an `agents/openai.yaml` sidecar for Codex (§4).

```
my-skill/
├── SKILL.md              # required: metadata + instructions
├── agents/openai.yaml    # Codex UI metadata + invocation policy (§4)
├── scripts/              # optional: deterministic code (validators, helpers)
├── references/           # optional: detail reached by a pointer, one level deep
└── assets/               # optional: templates, static files
```

**Progressive disclosure** is the loading architecture — three tiers:

- **Discovery (~100 tokens, always loaded):** only `name` + `description` sit in the system prompt. The agent knows the skill exists and when it applies.
- **Activation (<5k tokens, on match):** the request matches the description; the agent reads the full `SKILL.md`.
- **Execution (unbounded, on demand):** the agent reads `references/*` or runs `scripts/*` only as needed. Files cost nothing until accessed — so bundled content has no practical limit.

**The description routes; the body executes. Get both right independently.**

## 2. Frontmatter — the skill-specific rules

Write the description per the pointer rules in [`writing-for-agents`](../writing-for-agents/SKILL.md) (what + when + differentiator + real trigger phrases; never summarize the workflow, or the agent follows the summary and skips the body). The traps that silently prevent a *skill* from loading:

- `name` is lowercase-hyphen, 1–64 chars, **exactly the folder name**.
- No `<` or `>` in frontmatter — they can inject into the system prompt.
- Never put `: ` (colon-space) inside an unquoted `description` — any spec-compliant YAML parser rejects it as a nested mapping (verified on PyYAML and js-yaml — not Pi-specific). Use ` - ` or single-quote the whole value and double inner apostrophes.
- Invalid YAML fails silently — the skill just never loads.

## 3. Invocation and router skills

Two choices, trading the two loads (defined in [`writing-for-agents`](../writing-for-agents/SKILL.md)):

- **Model-invoked** (omit `disable-model-invocation`): keeps a live `description` so the agent — or another skill — can fire it autonomously. You can still type its name; model-invocation only ever *adds* agent reach. Costs context load every turn. A model-invoked all-reference skill is also a home for shared reference other skills invoke.
- **User-invoked** (`disable-model-invocation: true`): strips the description from the agent's reach; only you, typing its name, invoke it, and no other skill can. Zero context load, but you become the index. The `description` becomes human-facing — a one-line summary, triggers stripped.

Pick model-invocation only when the agent must reach the skill itself, or another skill must. When user-invoked skills outnumber what you can remember, cure the pile-up with a **router skill**: one user-invoked skill that names the others and when to reach each. It can only hint, never fire them — user-invoked skills have no description for anything but the human to reach.

Corollary for authors: a skill body that instructs invoking a user-invoked skill (`disable-model-invocation` / `allow_implicit_invocation: false`) is a silent no-op for any agent — no description means no autonomous reach. Say so in the body and tell the human to run it instead.

## 4. The Codex sidecar — `agents/openai.yaml`

`disable-model-invocation` is a Claude Code / Pi extension; **Codex ignores it.** Without a sidecar, a user-invoked skill still shows up to Codex's model for implicit invocation. Ship an `agents/openai.yaml` beside every `SKILL.md` so the set works in both harnesses from one source:

```yaml
# model-invoked skill — interface metadata only
interface:
  display_name: "Cross-Family Review"
  short_description: "A different family reviews at an exact head"
```

```yaml
# user-invoked skill — add the policy block (Codex analog of disable-model-invocation)
interface:
  display_name: "Handoff"
  short_description: "Compact a session into a handoff a fresh agent resumes from"
policy:
  allow_implicit_invocation: false
```

The `policy.allow_implicit_invocation: false` line goes on **user-invoked skills only** — it is what makes `disable-model-invocation` travel to Codex. Put it on a model-invoked skill by mistake and Codex filters the skill out of the model-visible list, so its description can never trigger it (only an explicit `$name` works). Keep `display_name`/`short_description` in sync with the SKILL.md — a stale sidecar naming an old skill is a real bug.

## 5. Fleet distribution — one authored skill, every seat

Author once at the canonical location; symlinks and one copy cover the rest.

| Seat | Skills folder | Notes |
|---|---|---|
| Codex / OpenAI | `~/.agents/skills/` | **canonical** — author here first (reads the `agents/openai.yaml`) |
| Claude Code | `~/.claude/skills/` | symlink → `~/.agents/skills/` — auto-covered |
| Pi | `~/.pi/agent/skills/` | symlink → `~/.agents/skills/` — auto-covered (path is `/agent/` nested) |
| Hermes | `~/.hermes/skills/` | independent copy — the only manual one |

```bash
SKILL=<skill-name>
# 1. author in ~/.agents/skills/$SKILL/ (SKILL.md + agents/openai.yaml)
# 2. verify the .claude symlink once:  ls -la ~/.claude/skills  (expect -> ~/.agents/skills)
# 3. copy to Hermes only (.claude and .pi are symlinks — already covered):
rsync -a --delete ~/.agents/skills/$SKILL/ ~/.hermes/skills/$SKILL/
# 4. verify all four report identical byte counts:
for p in ~/.agents/skills ~/.claude/skills ~/.pi/agent/skills ~/.hermes/skills; do
  echo "$p/$SKILL: $(wc -c < $p/$SKILL/SKILL.md) bytes"; done
```

Traps: `~/.pi/skills/` is the wrong path (Pi loads `~/.pi/agent/skills/` only); `~/.claude/skills` is a symlink, not a folder (a `cp` into it errors "are identical" — skip it); Hermes snapshots skills at session start (restart to see a new one); `SKILL.md` casing matters on case-sensitive volumes. A Claude Code plugin-marketplace bundle is a read-only alternative that auto-pulls updates — offer it for consumers who shouldn't edit. Removing a skill globally is destructive — `rm -rf` from `~/.agents/skills/` (covers the symlinks) and `~/.hermes/skills/`, and confirm with the user first.

## 6. The universal levers — one pointer, not a copy

For description-as-pointer wording, the two loads, information hierarchy, progressive-disclosure-as-hierarchy-protection, completion criteria, leading words, pruning, no-ops, negation, and sprawl — read [`writing-for-agents`](../writing-for-agents/SKILL.md). Keeping them there and pointing here is this island obeying its own single-source-of-truth rule.

Skill-specific reminders that layer on top: **bash-first, prose-second** (the agent pattern-matches on syntax); **push determinism into code** (fragile/repetitive → a script); **build a validation loop** (state verify → fix → re-verify explicitly); **compose primitives, don't bundle** (one skill = one concern); **keep references one level deep** — the bound is chain depth, not file count: any number of sibling `references/*.md` each pointed at directly from `SKILL.md` is fine; a reference file that itself links onward is the violation (never `SKILL.md → a.md → b.md`). A link up to a repo-root substrate file is a single hop, not a chain.

## 7. The IDC evidence layer

The universal rules of the evidence discipline — state enforced-vs-advisory for every rule and never imply it, never launder `unverified` into `verified`, ground vocabulary in [`CONTEXT.md`](../../CONTEXT.md) — live in [`writing-for-agents`](../writing-for-agents/SKILL.md) under *The IDC layer*, because they govern any agent doc, not just skills. Pointing here rather than restating is this island obeying its own single-source-of-truth rule.

The one addition unique to a **skill**: if it encodes an evidence discipline, it **demonstrates that discipline in its own construction** — the review skill was reviewed by a different family; the guard scripts were run and shown to block; the wizard template was `bash -n`'d and its upsert smoke-tested.

## 8. Ship checklist

- [ ] `name` matches the folder; frontmatter YAML valid (no `: ` unquoted, no `<`/`>`)
- [ ] description = what + when + differentiator + real triggers; no workflow summary
- [ ] `agents/openai.yaml` present; `policy.allow_implicit_invocation: false` iff user-invoked; display_name/short_description in sync
- [ ] one concern per skill; references one level deep
- [ ] every skill named for invocation in the body is reachable by the invoker — grep the body for invoke/route/fire targets; if a target is user-invoked (`disable-model-invocation` / `allow_implicit_invocation: false`), the body must say so and tell the human to run it, not assume an agent can fire it
- [ ] completion criteria checkable, exhaustive where it matters; a validation loop documented
- [ ] relative paths only; no human-facing docs inside the folder; no time-sensitive facts; no bundled library source
- [ ] pruned against the `writing-for-agents` failure modes (duplication, no-ops, negation, sprawl, sediment)
- [ ] tested for triggering and execution, against the **weakest** model you'll deploy on
- [ ] if it encodes an evidence discipline, it demonstrates that discipline in its own construction

**No authority without evidence. A skill demonstrates its own discipline.**
