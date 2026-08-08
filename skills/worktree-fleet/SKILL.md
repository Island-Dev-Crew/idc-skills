---
name: worktree-fleet
description: Use git worktrees for same-machine parallel agents — with the IDC boundary on where a worktree may and may not produce evidence. Use when starting task work in a shared repo, running parallel agents on one machine, or when the user says "worktree", "parallel agents", or agents overwrite each other. Differentiator - this is the version of the worktree skill that knows when NOT to use itself; worktree artifacts are inadmissible as gate evidence until re-derived from a fresh clone.
disable-model-invocation: true
---

# Worktree Fleet — with a boundary

Git worktrees solve same-machine parallelism cleanly. IDC adopts them for that — and fences them everywhere evidence is produced, because a worktree is institutionalized warm state and warm state has burned this project before. This island is the worktree skill plus the one ruling that keeps it honest.

## Start here — where am I?

```bash
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "not a git repository"; exit 1; }
[ "$(git rev-parse --path-format=absolute --git-dir)" = "$(git rev-parse --path-format=absolute --git-common-dir)" ] \
  && echo "primary checkout" || echo "worktree"
```

- **Primary checkout** → do not edit here. It is the integration point — review, merge, push only. Create a worktree named for the task, bootstrap it (below), `cd` in, work there.
- **Worktree** → proceed with the task.

## What a worktree is

One repo, many folders. `git worktree add` makes an extra checkout on its own branch. All worktrees share one `.git` history but each has its own files, so two agents in two worktrees cannot overwrite each other's files. **They isolate files, not git state** — one shared stash list, one shared config, one shared `.git/info/attributes`. That last clause is the whole boundary below.

## The working model

- **One task = one worktree = one agent session.** Never two agents in one working directory.
- **The primary checkout is the integration point.** It stays on main; used only to review, merge, push. Not a scratchpad.
- **Nothing auto-merges.** A human reviews each worktree's diff, then merges or discards, then removes the worktree.
- **Worktree branches are local and short-lived.** Never push them unless asked. Only main gets pushed. Rebase a stale worktree onto main before merging.

```bash
git worktree list && git branch --list task-x    # check the name is free before claiming it
git worktree add ../repo-task-x -b task-x main   # new worktree + branch off main
git worktree remove ../repo-task-x               # when merged or abandoned
git worktree prune                               # clean stale registrations
```

A branch can be checked out in only one worktree at a time (including main). Two agents racing the same task name hit `fatal: cannot lock ref` — advisory, not enforced: pick a distinct name and `git worktree prune` any half-registered loser.

## Make the worktree complete

A fresh worktree has only tracked files; everything gitignored is missing, and an agent dropped into a bare worktree fails confusingly. Replicate:

1. **Env/secrets** — copy `.env`, `.env.local` from the primary. Copy, never symlink (editing a symlinked env corrupts the original).
2. **Dependencies** — run the install (`npm ci`, `pnpm install`, `uv sync`). Never symlink `node_modules`.
3. **Local DBs/services** — shared server: pin identity (Docker Compose top-level `name:`) so worktrees don't fight over a port. Per-worktree state (SQLite): copy or re-seed.
4. **Ports** — run one at a time, or make the port configurable per worktree.
5. **Generated files/caches** — rebuild in the worktree (`npm run build`, codegen).

Codify it in `scripts/setup-worktree.sh` and run it first in any new worktree. Inside a worktree the primary path is `dirname "$(git rev-parse --path-format=absolute --git-common-dir)"`.

## The IDC boundary — adopted for drafts, forbidden for evidence

Worktrees solve same-machine parallelism; the IDC fleet parallelizes across *machines*, and the collisions actually suffered were cross-machine (two machines on one lane, duplicate ids) — see the `lane-claim` and `finding-register` islands. Worktrees prevent neither. Worse, every worktree shares one `.git/info/attributes`, and a contaminated attribute channel produces false-greens in a byte-level gate — proven by fixture. One contaminated worktree contaminates every scan on the machine.

So the boundary sits here:

- **Allowed:** draft worktrees, exploration, frozen-branch parking — on a development machine.
- **Forbidden:** any machine whose job is measurement or native evidence; any reviewer clone (a reviewer's fresh clone *is* the independence claim — see `cross-family-review`).
- **Inadmissible:** any gate-consumed artifact produced in a worktree is inadmissible until **re-derived from a fresh clone by a record seat** — the fresh-clone seat that produces the `confirmed-by` evidence (see `finding-register`). A green from a worktree is a draft green, not an evidence green.

State this boundary as `enforced` only where a hook actually enforces it; elsewhere it is `advisory` discipline — say which, never imply.

## Merging back

```bash
# from the primary checkout, after reviewing the worktree's diff:
git merge --no-ff task-x        # or --squash
git worktree remove ../repo-task-x
git branch -d task-x
```

## Gotchas

- Gitignored files silently missing is the #1 failure — always bootstrap first.
- Uncommitted work in a removed worktree is gone; commit early — commits live in the shared repo after the folder is gone.
- Long-lived worktrees rot — rebase onto main or restart.
- **Worktrees isolate files, not git state** — one shared stash, one shared config, one shared attributes file. This is why evidence never leaves a worktree unverified.

**No authority without evidence. A worktree green is a draft green until a fresh clone re-derives it.**
