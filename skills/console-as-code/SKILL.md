---
name: console-as-code
description: Assemble an agent's operating prompt from versioned blocks living in the repo — BOOT, covenants, mission loop, and seat definitions — stamped with the assembly SHA, instead of hand-pasting from chat. Use when a fleet's operating prompt drifts between machines, when the user mentions "console-as-code", "prompt drift", "prompt assembler", "BOOT block", or wants the control plane versioned. Differentiator - IDC-native; makes every operating prompt an auditable, SHA-stamped artifact so the same console assembles identically on every seat.
---

# Console as Code: the prompt is an artifact

An IDC-native island, named in the Garnet×Buzz synthesis as *"the first IDC-skills candidate to graduate into Garnet ops."* It cures **prompt drift**: the failure mode where an agent's operating prompt (its BOOT sequence, covenants, lane rules) is hand-assembled and copy-pasted between machines, so no two seats run quite the same console and nobody can say which version produced a given result. The cure is to move the blocks into the tree and assemble them with a SHA-stamped tool, so **every prompt is an auditable artifact**.

The whole idea: a console is not typed, it is *built*, from versioned source, reproducibly, with the assembly stamped so a reader can recompute exactly what any seat was running.

## The shape

```
console/
  blocks/
    00-boot.md           # the wake sequence
    10-covenants.md      # the standing rules (no authority without evidence, …)
    20-mission.md        # the forge mission loop
    30-seats.md          # named seats and their families
  console.lock           # the assembled console + its stamp (generated, committed)
  assemble.sh            # concatenates blocks in order, stamps the SHA
```

Each block is a single source of truth for one concern (BOOT, covenants, mission, seats). The console is their ordered concatenation. The **stamp** records the SHA-256 of the assembled text plus the exact Git tree object containing the blocks, so "which console was this seat running?" is answerable to the byte.

## Assemble

```bash
# macOS / BSD Perl shasum contract
IDC_CONSOLE_GIT=/absolute/path/to/git \
IDC_CONSOLE_SHA256=/absolute/path/to/shasum \
IDC_CONSOLE_SHA256_KIND=shasum \
./console/assemble.sh

# GNU coreutils alternative
IDC_CONSOLE_GIT=/absolute/path/to/git \
IDC_CONSOLE_SHA256=/absolute/path/to/sha256sum \
IDC_CONSOLE_SHA256_KIND=sha256sum \
./console/assemble.sh
```

`console/assemble.sh` is the executable contract. It reads sorted exact `HEAD` blobs rather than a worktree glob; rejects dirty, untracked, ignored, skip-worktree, assume-unchanged, case-colliding, non-Markdown, and unsupported Git objects; and requires explicit absolute Git and SHA-tool paths. By default it safely probes the two supported SHA-256 interfaces; set `IDC_CONSOLE_SHA256_KIND` to `shasum` or `sha256sum` to require one explicitly.

The `console.lock` is committed. A seat boots from `console.lock`, never from a chat paste. When a block changes, re-assemble: the stamp changes, and the diff on `console.lock` shows exactly what every seat's console will now say.

## The discipline

- **Blocks are the single source of truth.** Never edit `console.lock` by hand; edit a block and re-assemble. A hand-edit breaks the stamp's promise (the lock no longer equals its blocks).
- **The stamp is the identity.** When a result is reported, name the console stamp that produced it, the way a [`cross-family-review`](../cross-family-review/SKILL.md) verdict names its head. "Which console?" is then never a guess.
- **One block, one concern.** BOOT, covenants, mission, and seats stay separate files, so a covenant change is a one-block diff, not a needle in a pasted wall of text. Filenames must be unique case-insensitively; `assemble.sh` refuses to build otherwise, since case-insensitive filesystems collapse them to one file.
- **Ground the fleet's vocabulary here.** The blocks are where the [`CONTEXT.md`](../../CONTEXT.md) ubiquitous language lives for the operating prompt, so every seat speaks one tongue: the drift cure at the word level, not just the block level.
- **The stamp proves integrity, not safety.** It attests the assembled text byte-matches the committed blocks, not that the blocks are safe content. Because the console becomes an agent's operating prompt, commit access to a block is a prompt-injection surface; review block diffs with the same scrutiny as any other prompt change.

These rules are **advisory**: nothing mechanically blocks a hand-edit of `console.lock`; detection requires rerunning the hardened assembler and comparing the generated lock. Its dirty-tree, untracked/ignored-entry, index-flag, case-fold, object-shape, and digest checks are the **enforced** steps: they fail closed and exit non-zero. State that plainly; a stamp whose blocks were bypassed is exactly the unverified-worn-as-verified failure the archipelago forbids.

## Where this plugs in

Console-as-code is the control-plane companion to the evidence layer, and the boundary is strict: it is convenience, never a trust input. A gate never reads the console to decide a verdict, the same one-way rule the synthesis set for a separate `garnet-ops` control repo (*nothing in the evidence kernel reads the control plane*). The console assembles the prompt; [`evidence-packet`](../evidence-packet/SKILL.md) and [`archipelago`](../archipelago/SKILL.md) decide what's true. [`handoff`](../handoff/SKILL.md)'s wake protocol reads the assembled console's BOOT block from the tree, never from a summary.

**No authority without evidence. Edit the block, re-stamp, never hand-edit the lock.**
