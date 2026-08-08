---
name: merge-resolve
description: Resolve an in-progress git merge or rebase by tracing every conflicting hunk back to the intent that authored it — the commit, PR, or issue — then keeping both intents where they compose and recording the trade-off where they collide, and running the project's checks before finishing. Use when a merge or rebase is mid-conflict and the user says "resolve conflicts", "fix the merge", "finish the rebase", or "merge conflict". Differentiator - each hunk is resolved against its traced originating intent and the merge is never aborted, where diagnose debugs bugs and transport-complete ships the resolved commit live.
---

# Merge Resolve — resolve to intent, never abort

A conflict is two intents disagreeing about the same lines. You cannot resolve it by picking the prettier diff; you resolve it by knowing *why each side wrote what it wrote*. The spine of this skill is **intent** — every hunk is traced to the change that authored it before a single line is chosen. **Never `git --abort`.** Abort throws away the resolution work and the intent you recovered; always finish the merge or rebase.

The covenant: a resolution is **verified** only once the project's checks pass on it. A hunk you resolved without recovering its intent is **advisory** — say so; never launder a guess into a verified merge.

## 1. See the current state

Deterministic — read the conflict before theorizing about it:

```bash
git status --short                      # UU/AA/DU markers = the conflicting paths
git diff --name-only --diff-filter=U    # just the unmerged files
git log --oneline --left-right --merge  # commits unique to each side, this conflict only
grep -rn '^<<<<<<<\|^=======\|^>>>>>>>' $(git diff --name-only --diff-filter=U)  # every hunk
```

Note whether you are in a merge (`.git/MERGE_HEAD` exists) or a rebase (`.git/rebase-merge/`) — the finish step differs (§5).

## 2. Trace each hunk to its intent

For **both** sides of every conflicting hunk, recover *why* the lines exist — not just what they say:

```bash
git log -L '<start>,<end>:<file>' <side>   # the line-range history on one side
git blame -L <start>,<end> <side> -- <file>  # the commit that touched these exact lines
git log --merge -p -- <file>               # both sides' commits, with messages, for this file
```

Read the commit message; follow it to the PR or issue/ticket it references. The goal is a one-line statement of intent per side — "left widened the timeout for slow CI, right renamed the field". Understand deeply; do not skim.

## 3. Resolve each hunk against its intent

- **Both intents compose** → keep both. The common case: two independent changes that only textually overlap. Weld them so both survive.
- **Intents collide** → keep the one matching the *merge's stated goal* (the branch you are merging in, the ticket driving the rebase), and **record the trade-off** in the commit body: which intent was dropped, and why. A dropped intent that goes unrecorded is a silent regression.
- **Never invent new behaviour** to bridge them — resolving is choosing and combining existing intents, not authoring a third.
- A hunk whose intent you could not trace is resolved **advisory**: mark it (a `TODO(merge)` line or an explicit note to the user), never present it as settled.

Remove every `<<<<<<<`/`=======`/`>>>>>>>` marker, then confirm none survive:

```bash
grep -rn '^<<<<<<<\|^=======\|^>>>>>>>' $(git diff --name-only) && echo "MARKERS REMAIN" || echo "clean"
```

## 4. Run the project's checks — this is the evidence

Discover the checks from the environment, do not assume them: `package.json` scripts, `Makefile`, `justfile`, CI config, `--help`. Run them in the cheap-to-expensive order the project defines — typically typecheck, then tests, then format/lint. Fix whatever the merge broke. **Green checks are what turns the resolution from claimed to verified**; a merge you did not run checks on is unverified, and you say so.

## 5. Finish — stage and complete

```bash
git add <the files you resolved>          # never `git add -A` in a shared checkout
git diff --cached --check                 # refuse trailing conflict cruft / whitespace errors
# merge:  git commit         (record dropped intents + any advisory hunks in the body)
# rebase: git rebase --continue  # then repeat from §1 for the next conflicting commit
```

For a rebase, loop §1–§5 until `git status` reports no rebase in progress. **Never `git rebase --skip`** — skipping drops a commit's intent whole; resolve it instead. The merge/rebase is done only when the working tree is clean, no markers remain, and the checks are green.

## Hard rules

- Never `git --abort`, never `git rebase --skip`. Finish the resolution you started.
- Every dropped intent is recorded in the commit body; every untraceable hunk is marked advisory.
- Resolution is verified only by passing project checks — never report a merge "resolved" without them.

**No authority without evidence. The passing checks are the evidence; a clean-looking diff is not.**
