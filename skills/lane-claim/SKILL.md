---
name: lane-claim
description: Declare-and-halt coordination for a fleet of agents working one repo across many machines — claim a lane before touching it, halt if it's already claimed, release when done. Use when more than one agent or machine could work the same repo, the user mentions "lane", "lane claim", "fleet coordination", "two machines on one lane", or agents are colliding across machines. Differentiator - IDC-only; solves cross-machine collisions that worktrees (same-machine only) structurally cannot touch.
---

# Lane Claim: declare and halt

An IDC-only island. It exists because the collisions the fleet actually suffered were **cross-machine**: two machines woke on one lane, and duplicate finding IDs were allocated in parallel. Worktrees isolate files on *one* machine and cannot see another machine's work, so they prevent neither. A lane claim is a declaration in shared, durable state that every machine reads before it acts.

A **lane** is a unit of parallelizable work with one owner at a time: a subsystem, a repair, a review round. The rule is **declare-and-halt**: claim the lane before touching it; if it's already claimed by someone else, **halt**. Do not proceed, do not "just take a look."

This is an **advisory, cooperative** protocol, a halt-on-honor coordination, not a lock: nothing here mechanically blocks a colliding write, because the collision it prevents is *cross-machine* and no single machine can bar another. The pushed claim is the evidence every seat reads before acting; the enforcement is each seat honoring it. State that plainly: a reader must not infer a mechanical lock the protocol does not provide.

Claiming, releasing, pulling, committing, and pushing mutate shared state. This skill never grants that authority by being invoked: obtain explicit operator/dispatcher authorization for the exact lane and remote before the first mutation. Without it, perform only the read-only fetch/status inspection and return the proposed claim or release record for approval.

## The claim record

Claims live in the repo (the shared memory every machine can fetch), not in any one agent's context. A claim is a small file or a row keyed by lane id:

```
ops/lanes/<lane-id>.claim.json
{
  "lane":      "2C-repair",
  "seat":      "Claude Fable 5",        // who — named by family, as the ceremony names seats
  "machine":   "nuc",                   // where — the physical machine holding the lane
  "head":      "<SHA the lane started from>",
  "claimed":   "<ISO-8601 UTC>",        // when — absolute, never "today"
  "status":    "active"                 // active | released | reclaimed
}
```

The claim answers **who / where / from-what-head / since-when** for every lane in flight. That is exactly the shape a close-out report (and Buzz's dispatch loop) consumes.

A claim file present but unparseable, or missing a required field above, is **active-unknown**: halt, do not claim over it, and surface it to a human (or the force-reclaim authority, see Stale claims below) with the file contents as evidence. Never silently overwrite or delete an unreadable claim.

## Procedure

### 1. Fetch before you claim

```bash
git fetch origin
git pull --ff-only origin main          # read the current shared truth first
ls ops/lanes/                           # what is already claimed
```

Never claim from a stale tree; a claim written against week-old state is the exact cross-machine race this island prevents.

### 2. Claim, or halt

- **Lane free** (no active claim, or your own released claim) → write the claim file, commit it alone (`git add ops/lanes/<lane>.claim.json && git commit`), push it. The pushed claim is the declaration; an unpushed claim binds nobody.
- **Lane already active under another seat/machine** → **halt.** Report who holds it and since when. Do not edit files on that lane. Pick a different free lane or wait for release. Two seats on one lane is split ownership, and split ownership is how the duplicate-ID and double-work incidents happened.

**Done when** your authorized push of the claim succeeds *and* a re-fetch shows no competing active claim landed first. If a competing claim raced you to the push, yield: park the rejected claim commit on a clearly named local branch so it is recoverable, return the checkout to the verified remote head through the repo's approved reconciliation path, then halt and report who won. Never use `reset --hard` as a generic cleanup recipe; if unrelated local work exists, stop and reconcile by hand.

### 3. Work the lane

Do the lane's work against the head recorded in the claim. All evidence, verdicts, and finding IDs for this lane belong to this claim's seat and machine; that provenance is what the `finding-register` and `cross-family-review` islands mark.

### 4. Release

```bash
# set status: released in the claim file, commit alone, push
git add ops/lanes/<lane>.claim.json && git commit -m "release lane <lane>"
git pull --ff-only origin main && git push origin main
```

If the pull fails, rebase instead. `git pull --rebase origin main` is safe here because the release commit touches only the claim file. Then push. If the claim file itself conflicts, stop and inspect before resolving.

A released lane is free for the next seat. Leave the claim file in place (released, not deleted) so the lane's history stays legible: who held it, when, from what head.

## Stale claims

A claim nobody is releasing strands the lane: the halt rule is unconditional, and an abandoned machine will never push a release. Judge staleness by activity, not the clock alone: no commits on the lane since the claim's recorded head, past the fleet's normal work cycle. Only a human operator (or a designated dispatcher seat) may force-reclaim, and only after confirming the claiming machine is actually gone, not mid-work. To force-reclaim: set `status: reclaimed`, add `reclaimed_by` and `reclaimed_from`, commit alone, push, and notify. A force-reclaim without that provenance is a protocol violation, not a shortcut.

## The boundary with worktrees

| Collision | Cured by |
|---|---|
| Two agents, one machine, editing the same files | worktrees (file isolation), see `worktree-fleet` |
| Two **machines** on one lane | **lane-claim** (declare-and-halt) |
| Duplicate finding IDs allocated in parallel | `finding-register` ID sweep, gated by lane ownership |

Worktrees and lane claims are complementary, not alternatives. Use worktrees for same-machine parallelism; use lane claims so two machines never wake on the same work.

**No authority without evidence. A claim binds nobody until it is pushed.**
