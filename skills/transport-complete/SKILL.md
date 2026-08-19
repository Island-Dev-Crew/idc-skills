---
name: transport-complete
description: Ship a change and babysit it until it is verifiably live — commit, push, watch CI, confirm the deploy promoted the exact SHA, and prove production serves it — fixing failures along the way. Use after the user gives an explicit go-ahead and says "push", "ship it", "deploy", "push to prod", or "get this live". Differentiator - "done" means a health check passes for the exact pushed SHA, not that the push succeeded; pushing always requires the user's explicit go-ahead first.
---

# Transport Complete — pushed-and-verified or not done

The covenant: **transport is not complete until the exact change is verifiably live.** A green push is not done. A green CI is not done. Done is a health check passing for the *exact SHA* you pushed. This fuses David Ondrej's *prod-push* babysitting loop with IDC's transport covenant: a report of "shipped" without a live check is the precise defect the fleet exists to prevent.

**Never push without the user's explicit go-ahead.** This skill is the procedure for *after* they give it. Never force-push. Never push side branches unless that is the repo's model.

## State check — how does this repo ship?

Before touching git, learn the repo's actual shipping model; do not assume:

```bash
git branch --show-current
ls .github/workflows/ 2>/dev/null                    # what CI runs, what gate is required
grep -lE '^[[:space:]]*push:' .github/workflows/*.y*ml  # which of those actually trigger on push
git remote -v                                        # where main lands
```

Identify: the required CI check name (capture it as `WORKFLOW`; step 3 filters on it), whether deploy is push-triggered (Vercel-style) or manual, and the production health endpoint. Bind `WORKFLOW` **only** to a check whose `on:` block triggers on push to the ship branch; a schedule-only or `workflow_dispatch`-only workflow is not a gate for your SHA. This is a precondition on step 2: never push until a push-triggered required gate is named. If you can't name all three, ask; shipping blind is how the exact-SHA guarantee is lost.

This loop is GitHub Actions + `gh` CLI specific. If `ls .github/workflows` turns up no workflow that triggers on push to main (the directory is empty, or every file fires only on `schedule:`/`workflow_dispatch:`), the repo has no GH push gate (it may ship on GitLab CI, CircleCI, Jenkins, or nothing). STOP and tell the user; do not improvise an equivalent procedure or push blind.

## The loop — repeat until the exact change is live

```bash
# 0. Fail closed before touching git. Ship from the primary checkout, on the ship branch.
[ "$(git branch --show-current)" = "main" ] || { echo "transport: not on main" >&2; exit 1; }
gd=$(git rev-parse --path-format=absolute --git-dir)
gc=$(git rev-parse --path-format=absolute --git-common-dir)
[ "$gd" = "$gc" ] || { echo "transport: linked-worktree pushes are forbidden" >&2; exit 1; }
# (Worktree pushes carry a stale branch hook — see the worktree-fleet island.)

# 1. Commit ONLY your files. Never `git add -A` / `git add .` / `commit -a` when a
#    shared checkout may hold another seat's WIP. The tree must be clean between pushes.
git add <your files> && git commit
[ -z "$(git status --porcelain --untracked-files=no)" ] || { echo "transport: tree not clean" >&2; exit 1; }

# 2. Sync + push. --autostash is BANNED (replaying dirty edits onto fresh upstream = UU
#    conflicts + orphaned stashes). Never --no-verify. Never weaken a check to go green.
git pull --rebase origin main
git push origin main
SHA=$(git rev-parse HEAD)                     # THIS is the SHA everything below must track

# 3. Find the CI run for this exact SHA on $WORKFLOW, then let it stream to completion.
#    Multiple workflows can share a SHA (lint.yml + test.yml + deploy.yml all trigger on
#    the same push) — filter on the required check name, not just the SHA, and take one run.
RUN_ID=""
for i in 1 2 3 4 5 6; do
  RUN_ID=$(gh run list --branch=main --limit=20 --json headSha,databaseId,workflowName \
    --jq "[.[] | select(.headSha==\"$SHA\" and .workflowName==\"$WORKFLOW\")] | .[0].databaseId // empty")
  [ -n "$RUN_ID" ] && break; sleep 5
done
[ -n "$RUN_ID" ] || { echo "transport: CI run not found for $SHA on $WORKFLOW" >&2; exit 1; }
gh run watch "$RUN_ID" --exit-status

# 4. CI green -> confirm the deploy promoted THIS SHA (not a neighbour).
#    Verify the deployment even for "docs-only" commits — never skip on a judgment call.
DEPLOYMENT_ID=$(gh api "repos/<org>/<repo>/deployments?sha=$SHA&environment=Production&per_page=1" --jq '.[0].id // empty')
[ -n "$DEPLOYMENT_ID" ] || { echo "transport: no Production deployment for $SHA" >&2; exit 1; }
DEPLOY_STATUS=""
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  DEPLOY_STATUS=$(gh api "repos/<org>/<repo>/deployments/$DEPLOYMENT_ID/statuses?per_page=1" --jq '.[0].state // empty')
  [ "$DEPLOY_STATUS" = success ] && break
  case "$DEPLOY_STATUS" in error|failure|inactive) echo "transport: deployment $DEPLOY_STATUS" >&2; exit 1;; esac
  sleep 10
done
[ "$DEPLOY_STATUS" = success ] || { echo "transport: deployment did not reach success" >&2; exit 1; }

# 5. Prove production serves it.
curl -fsS -m 15 https://<prod-host>/<health-path>
SERVED_SHA=$(curl -fsS -m 15 https://<prod-host>/<build-sha-path>)
[ "$SERVED_SHA" = "$SHA" ] || {
  echo "transport: production serves $SERVED_SHA, expected $SHA" >&2
  exit 1
}
```

**Done = green CI + a successful Production deployment + a healthy check, all for the exact `$SHA`.** Then report what shipped.

## Landing work from a worktree

Agents build in worktrees; the loop refuses to run there (a worktree carries its own branch hook and may hold stale safety code). To land it: commit on the worktree's own branch (never commit to main from a worktree), then in the primary checkout (clean tree required) `git pull --rebase`, merge or cherry-pick **your** branch (one at a time, never two seats' branches in one pass), resolve conflicts in the hub, then run the loop from step 2.

## Failure modes

- **CI failed:** `gh run view <id> --log-failed`, reproduce locally (run the failing step), fix, commit, restart the loop. The new push gets a **new SHA**, so track that one.
- **CI green but deploy `failure`:** the build itself broke. Reproduce with the repo's build command; if it's platform-side (env vars, limits), stop and hand the user the deploy logs.
- **CI `cancelled`:** a newer push superseded yours; your commit will never deploy alone. Confirm the newer SHA contains your change (`git merge-base --is-ancestor $SHA <newer>`) and track that SHA.
- **Health returns not-ok / 503:** often migration drift: deployed code expects a migration not yet applied to prod. The deploy still succeeded. Agents never write to prod, so tell the user which migration to apply and stop looping; say health will stay red until they do.
- **Push rejected (non-fast-forward):** someone pushed meanwhile. `git pull --rebase origin main` and push again. If the rebase stops on a conflict (the winning push touched a shared file), resolve the named files, `git add <files>`, `git rebase --continue`; never `git rebase --skip`, never `--autostash`. Then recompute `SHA=$(git rev-parse HEAD)` after the rebase completes and re-run step 3 on the new SHA. If the conflict can't be safely resolved, `git rebase --abort` and hand the user the conflicting paths; do not loop. Advisory: the resolution is operator judgment; `--autostash` stays banned here.

## Hard rules

- Never push without the user's explicit go-ahead. Never force-push. Never push side branches (unless that is the repo's model).
- Never weaken CI to go green: no deleting/skipping tests, no `--no-verify`, no merging around a red check.
- If the change includes a DB migration, the user applies it to prod manually; expect health red until they do, and say so in the report.

**No authority without evidence. A push is not done until production serves the exact SHA.**
