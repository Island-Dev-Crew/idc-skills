---
name: wizard
description: Generate an interactive bash wizard that walks a human through steps only they can perform — opening each URL, saying what to click, capturing values, and writing them into .env files and GitHub Actions secrets. Use when provisioning infrastructure, setting up credentials or CI secrets, walking an unfamiliar third-party dashboard (Namecheap, Vercel, Stripe, AWS), or running a one-off migration or cutover. Differentiator - work an agent can do, an agent should do; the wizard is only for the clicks, approvals, and dashboard trips you would not hand to an agent.
---

# Wizard — drive the human through the clicks

A **wizard** is a bash script that walks a human, step by step, through a manual procedure that's tedious by hand and tedious to re-explain to an agent every time. It opens each URL, says exactly what to click and copy, captures the values, writes them where they belong (`.env`, GitHub secrets), confirms at every stage, and shows how much is left. It configures third-party services, runs a one-off migration, or moves a project from one state to another — the kind of dashboard trip you would not, and should not, hand to an agent.

The delightful UX is pre-solved by the bundled [template.sh](template.sh) — progress with time-remaining, confirmation gates, cross-platform URL opening (including WSL), hidden secret entry, idempotent `.env` upserts, `gh secret`/`gh variable` writes with graceful degradation, and a closing summary. **Your job is only to scope the procedure and author its stages.** The library above the `STAGES` marker is identical in every wizard; that consistency is the point — never hand-edit it.

A wizard is ephemeral by default — built for one run, saved to a scratch or `scripts/` path, deleted when done. Commit it only when the user wants a repeatable setup path that should live in the repo.

## Process

### 1. Scope the procedure

Work out every manual step the human must take and every value captured along the way. **Read the repo first — don't ask cold:**

- For setup: `.env`, `.env.example`, `.env.*`, `README`, `docker-compose*`, framework config, and `.github/workflows/*` — every `secrets.*` / `vars.*` reference is a value the wizard must produce.
- For a migration or transition: the current state, the target state, and the irreversible actions between them.

Then show the user the ordered list of stages and the values each produces, and confirm — they may add, drop, or reorder. When the agent fires this mid-build, that stage-list confirmation doubles as the proposal.

**Done when** every stage is named in order, and for each captured value you know (a) where the human gets it, (b) where it's written (`.env`, a GitHub secret, both, or nowhere — some stages are pure actions), and (c) whether it's secret (hidden entry) or public.

### 2. Map each stage's journey

For each stage, write the precise path a human follows: which URL to open, what to do there, where a value is shown, which variable it fills — e.g. "Namecheap → Domain List → Manage → Advanced DNS → add A record `@` → `76.76.21.21`". Where you don't know the current UI or exact command, say so and ask the user or check the docs — **never invent steps that may not exist.**

**Done when** every stage traces to concrete instructions a stranger could follow.

### 3. Author the wizard

Copy `template.sh` to the target path. Replace the example stage below the `STAGES` marker with one `stage` per step, in dependency order. Use the library helpers — `stage`, `say`/`step`, `open_url`, `ask`/`ask_secret`, `write_env`, `set_secret`/`set_var`, `confirm` — and set `TOTAL_STAGES` and `TOTAL_MINUTES` to honest estimates (this drives the time-remaining display).

Hold the bar the template sets: open the URL before asking for its value; `ask_secret` for anything secret; `write_env` every persisted value; `set_secret` only the values CI actually needs; `confirm` before any irreversible action. Each `stage` clears the screen so only the current step shows — keep a stage to one focused task so nothing the human needs scrolls away. **Don't touch the library above the marker.**

### 4. Verify and hand off

- `bash -n <script>`; run `shellcheck` if available.
- `chmod +x <script>`.
- **Don't run it end-to-end yourself** — it opens browsers and blocks on human input. Trace it statically: every value from step 1 is captured and lands where step 1 said, and every `set_secret` name exactly matches a `secrets.*` reference in CI.
- Tell the user how to run it. If it's a repeatable setup path, commit it and link it from the README so the next person runs the script instead of asking an agent.

## Where this plugs in

The wizard is the human-only complement to the fleet's automation: [`domain-wire`](../domain-wire/SKILL.md) decides *what* DNS a domain needs per the doctrine; a wizard walks you through *entering* it in the Namecheap and Vercel dashboards and writing the resulting tokens into GitHub secrets. [`transport-complete`](../transport-complete/SKILL.md) ships code an agent wrote; a wizard handles the one-time platform setup an agent can't.

**No authority without evidence. Verify statically — bash -n, shellcheck, trace — before handing it over.**
