---
name: console-as-code
description: Assemble an agent's operating prompt from versioned blocks living in the repo — BOOT, covenants, lane definitions — stamped with the assembly SHA, instead of hand-pasting from chat. Use when a fleet's operating prompt drifts between machines, when the user mentions "console-as-code", "prompt drift", "prompt assembler", "BOOT block", or wants the control plane versioned. Differentiator - IDC-native; makes every operating prompt an auditable, SHA-stamped artifact so the same console assembles identically on every seat.
---

# Console as Code — the prompt is an artifact

An IDC-native island, named in the Garnet×Buzz synthesis as *"the first IDC-skills candidate to graduate into Garnet ops."* It cures **prompt drift**: the failure mode where an agent's operating prompt — its BOOT sequence, covenants, lane rules — is hand-assembled and copy-pasted between machines, so no two seats run quite the same console and nobody can say which version produced a given result. The cure is to move the blocks into the tree and assemble them with a SHA-stamped tool, so **every prompt is an auditable artifact**.

The whole idea: a console is not typed, it is *built* — from versioned source, reproducibly, with the assembly stamped so a reader can recompute exactly what any seat was running.

## The shape

```
console/
  blocks/
    00-boot.md           # the wake sequence
    10-covenants.md      # the standing rules (no authority without evidence, …)
    20-lanes.md          # lane definitions the fleet coordinates on
    30-seats.md          # named seats and their families
  console.lock           # the assembled console + its stamp (generated, committed)
  assemble.sh            # concatenates blocks in order, stamps the SHA
```

Each block is a single source of truth for one concern (BOOT, covenants, lanes, seats). The console is their ordered concatenation. The **stamp** is the SHA-256 of the assembled text plus the git commit the blocks came from — so "which console was this seat running?" is answerable to the byte.

## Assemble

```bash
# Refuse to run outside a git repo — there is nothing to stamp against.
git rev-parse --is-inside-work-tree >/dev/null 2>&1 \
  || { echo "refusing to assemble: not a git repository — run \`git init\` and commit the blocks first" >&2; exit 1; }
# Refuse to stamp a dirty tree: a commit id that does NOT contain these exact blocks
# would be a lying stamp — the reader who checks it out and re-assembles gets a
# different SHA. Fail closed instead. (This is the evidence discipline, mechanized.)
git diff --quiet && git diff --cached --quiet \
  || { echo "refusing to assemble: uncommitted block changes — commit the blocks first" >&2; exit 1; }
# Refuse on case-folded block name collisions — a case-insensitive filesystem
# (default macOS) collapses differently-cased names to one inode, so the same
# blocks/ directory would silently assemble to a different console on such a seat.
dupes=$(ls console/blocks/*.md | xargs -n1 basename | tr 'A-Z' 'a-z' | sort | uniq -d)
[ -z "$dupes" ] \
  || { echo "refusing to assemble: case-folded block name collision — $dupes" >&2; exit 1; }
# concatenate blocks in filename order, stamp the result
cat console/blocks/*.md > console/console.assembled
SHA=$(shasum -a 256 console/console.assembled | cut -d' ' -f1)
GIT=$(git rev-parse --short HEAD)
{ echo "<!-- console.lock — assembled from $GIT — sha256:$SHA -->"; cat console/console.assembled; } \
  > console/console.lock
rm console/console.assembled
echo "assembled console: sha256:$SHA @ $GIT"
```

The `console.lock` is committed. A seat boots from `console.lock`, never from a chat paste. When a block changes, re-assemble — the stamp changes, and the diff on `console.lock` shows exactly what every seat's console will now say.

## The discipline

- **Blocks are the single source of truth.** Never edit `console.lock` by hand — edit a block and re-assemble. A hand-edit breaks the stamp's promise (the lock no longer equals its blocks).
- **The stamp is the identity.** When a result is reported, name the console stamp that produced it, the way a [`cross-family-review`](../cross-family-review/SKILL.md) verdict names its head. "Which console?" is then never a guess.
- **One block, one concern.** BOOT, covenants, lanes, seats stay separate files — so a covenant change is a one-block diff, not a needle in a pasted wall of text. Filenames must be unique case-insensitively — `assemble.sh` refuses to build otherwise, since case-insensitive filesystems collapse them to one file.
- **Ground the fleet's vocabulary here.** The blocks are where the [`CONTEXT.md`](../../CONTEXT.md) ubiquitous language lives for the operating prompt, so every seat speaks one tongue — the drift cure at the word level, not just the block level.
- **The stamp proves integrity, not safety.** It attests the assembled text byte-matches the committed blocks — not that the blocks are safe content. Because the console becomes an agent's operating prompt, commit access to a block is a prompt-injection surface; review block diffs with the same scrutiny as any other prompt change.

These rules are **advisory** — nothing mechanically blocks a hand-edit of `console.lock`; the only detection is recomputing the stamp from the blocks and comparing (the dirty-tree gate above is the one *enforced* step). State that plainly; a stamp whose blocks were bypassed is exactly the unverified-worn-as-verified failure the archipelago forbids. A seat that wants this mechanized rather than advisory can recompute `shasum -a 256` over the blocks at boot and compare to the embedded stamp before trusting the console.

## Where this plugs in

Console-as-code is the control-plane companion to the evidence layer, and the boundary is strict: it is convenience, never a trust input. A gate never reads the console to decide a verdict — the same one-way rule the synthesis set for a separate `garnet-ops` control repo (*nothing in the evidence kernel reads the control plane*). The console assembles the prompt; [`evidence-packet`](../evidence-packet/SKILL.md) and [`archipelago`](../archipelago/SKILL.md) decide what's true. [`handoff`](../handoff/SKILL.md)'s wake protocol reads the assembled console's BOOT block from the tree, never from a summary.

**No authority without evidence. Edit the block, re-stamp, never hand-edit the lock.**
