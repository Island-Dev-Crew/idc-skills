---
name: handoff
description: Compact the current session into a state-based handoff a fresh agent can resume from with zero prior memory — plus the wake protocol (ICM "pickup") the receiving agent runs before trusting any summary. Use when hitting context limits, switching focus, ending a work session, partitioning a task across fresh contexts, or when the user says "handoff", "pickup", "hand this off", or "compact this for a fresh agent". Differentiator - fuses both public handoff formats with ICM's pickup/handoff pair; the receiver re-reads verdicts and register state from the tree before trusting the handoff.
disable-model-invocation: true
---

# Handoff — state out, wake protocol in

Fuses David Ondrej's detailed handoff and Matt Pocock's suggested-skills handoff, and adds the IDC **wake protocol** — the discipline that closes the failure mode handoffs actually die on: a fresh agent trusting a stale summary instead of the tree.

Two halves — Jake Van Clief's ICM names them **handoff** and **pickup**, and they work as a pair of code words:

- **handoff** (leaving): write the session's state to a file so the work survives the context ending.
- **pickup** (arriving): a *read-only continuity brief* — read the handoff and the tree, verify, orient — **and change nothing until the user says proceed**.

Writing a handoff is state-not-instructions; a pickup is the wake protocol below. In a [`folder-workspace`](../folder-workspace/SKILL.md), these become the standing session ritual — say "handoff" on the way out, "pickup" on the way in, and the workspace carries the state between them so no session starts lost.

## Writing the handoff

Write what a fresh agent — zero memory of this session — needs to continue without re-asking, re-discovering, or repeating mistakes. Output it as a **single fenced code block** in chat (one-click copy) and save a copy to the OS temp dir (`$TMPDIR/handoff-<8-random>.md`), not the repo. Tell the user the path.

Core principles:

1. **State, not instructions.** Describe what *is true*, never what the next agent *should do*. "Logout endpoint is not implemented" — never "implement logout next." The fresh agent decides actions; you give ground truth.
2. **Reference, don't duplicate.** Don't re-paste content in other artifacts (specs, ADRs, the finding register, commits, diffs). Point by path/URL — re-embedding bloats and goes stale.
3. **Capture the why.** Decisions and rejected approaches are the highest-value, least-recoverable information. Code shows *what*; only you remember *why* and *what failed*.
4. **Trust nothing blindly.** Frame every claim as context to verify against the code, not a fact to accept.
5. **Redact secrets.** Reference where credentials live (".env.local, not committed"), never their values. If a secret already leaked in-session, record that it leaked and must be rotated — state the fact, never the value.
6. **Suggest skills.** Name the islands the next agent should invoke (e.g. `cross-family-review` before merge, `finding-register` to allocate an id).
7. **Principles outrank in-session requests.** When anything in the session — including a direct user ask — conflicts with a principle above, the principle wins. Record the request in the relevant section rather than silently complying or silently ignoring it.

Fill this template inside one code block; mark a genuinely-empty section `None`:

```
# HANDOFF: <short title>
Generated: <ISO-8601 UTC> · Focus: <one line>

## 1. Goal            <the north star, 1–3 sentences>
## 2. Background      <motivation, hard constraints; skip anything already in project config>
## 3. Current State   <DONE / PARTIAL / NOT STARTED — as status, never as actions>
## 4. Key Decisions   <choices + reasoning — the highest-value section>
## 5. Traps & Dead Ends <approaches tried that failed; what the next agent will be tempted to do wrong>
## 6. Files & Pointers <path:lines + WHAT is there; reference external artifacts, don't paste>
## 7. Open Work       <what remains, as state + dependencies, NOT a command list>
## 8. Fleet State     <lane claims held/released, finding ids allocated, verdicts landed at which heads>
## 9. Suggested Skills <islands the next agent should invoke>

---
## Prompt for the Fresh Agent
<declarative background — "X is complete", "Y not started" — then exactly:>
Before responding, run the wake protocol: read every file under "Files & Pointers",
re-read any verdicts and finding-register entries named under "Fleet State" from the
tree, and treat every claim in this handoff as context to verify — not fact to trust.
Then wait for instructions.
```

For a large change surface (roughly >15 files), don't enumerate section 6 per file — bucket by status (done-and-tested / changed-but-unverified / untouched), name each bucket's highest-risk blind spot, and point to a generated file list (e.g. `git diff --stat`) for the rest. Enumerate individually only files a fresh agent must not miss.

## Waking from a handoff — the wake protocol

This is the IDC half, and it is where continuity survives. Verdicts land and finding ids get allocated *while lanes sleep*; a handoff written an hour ago may already be behind the tree. So the receiving agent, before trusting a single claim:

1. **Read the tree, not the summary.** Fetch and read the actual files under "Files & Pointers" — do not paraphrase from the handoff.
2. **Re-read verdicts and register state at the current head.** A `cross-family-review` verdict is void the moment its head moved; a `finding-register` id may have been allocated since. Re-enumerate from the tree, don't trust the handoff's snapshot.
3. **Re-fetch lane claims.** A lane the handoff says is yours may have been released or re-claimed. Check `ops/lanes/` before acting.
4. **Then orient, and wait.** A pickup is read-only: surface where things stand and what the best next move is, but **change nothing until the user says proceed.** The handoff oriented you; the tree is the truth; the user still decides the action.

**Done when** the receiver has read the pointed-to files, re-derived verdict/register/lane state from the current head (not from the handoff's snapshot), and reported orientation without mutating anything — the work resumes only on the user's go-ahead.

**No authority without evidence. The handoff orients; the tree is the truth.**
