# STATE — 2.0.3 hardening (durable, survives context compaction)

Snapshot as of the Codex double-check verdict. State, not instructions.

## Where things stand
- **2.0.2 is SHIPPED**: public `Island-Dev-Crew/idc-skills` main `76a7bf0`, staging `Navigata1/idc-skills-forge` main `76a7bf0`, annotated tag `2.0.2` -> `00f26a1`. `verify` READY 5/5 with a real 1Password signature. Signing key fingerprint `SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA` (1Password item "Forge 50 SSH Key"), anchor `keys/allowed_signers` (principal `idc-skills`).
- **2.0.2 CRITICAL is CLOSED** (proven by tamper tests): anchor swap -> FAIL, verifier tamper -> FAIL, skill-body tamper -> FAIL, appended second signer -> FAIL. The integrity gate holds.
- **Branch `v2.0.3-hardening` @ `9ff1d6a`** (NOT on either remote, NOT pushed). Working tree clean at start of fixes.

## Multi-model chain (the discipline)
Kimi K3 red-teams -> Codex builds/reconciles -> Claude(4.8) verifies -> repeat. No family certifies its own work. `[cyber]` classifier swaps Claude Opus->4.8 on security content regardless of model picked; irrelevant to correctness because the chain catches misses. CCG hook (`~/.claude/hooks/ccg/skill-router.js`) reshaped 2026-08-20 to inject CLEAN ENGLISH authorized-governance context on security keywords (not the Chinese red-team cheat-sheets); backup `.bak-2026-08-19`.

## What 2.0.3 must close (Codex CHANGES_REQUIRED verdict against `9ff1d6a`)
Codex PASSED: guard fixtures 45/45, unit 74/74, validator 50/50, shellcheck/bash/diff clean, simple `${IFS}`+simple alias-def blocked, direct `.sh`/`.py` egress detected, integrity correctly RED 3/5 until re-sign.

BLOCKING (must fix before sign/push):
1. **Guard** still misses: multiline commands, `!git push` shell-command aliases, whole-tree pathspec variants, dynamic variables, malformed hook payloads. New IFS/alias rewrites also **block benign text** (false positives) — must fix both directions.
2. **Scanner** structurally incomplete: extensionless scripts, UPPERCASE extensions, symlinked payloads, some binary files -> false greens. **No scanner regression tests committed** (must add red-before-green).
3. **Anti-rollback**: "highest local tag" design is UNTRUSTWORTHY — local tags are attacker-writable, annotated tags not inherently immutable, whole-tree rollback restores the old verifier too. `manifestSequence` helps only PARTIAL rollback. Whole-tree needs a **trusted out-of-repo floor or signed release index**. (PROVEN: full checkout of tag 2.0.2 verifies READY 5/5 -> rollback hole real.)
4. **Release order WRONG**: current spec signs manifest BEFORE bumping registry.json + changelog, which invalidates the signature. Correct order: finalize version+sequence+changelog+ALL control files -> generate manifest -> sign -> verify.

## Files in play
- `skills/agent-guardrails/scripts/block-dangerous-git.sh` (+ `test-block-dangerous-git.sh`, 45 fixtures) — Claude built IFS+alias defenses; Codex says incomplete + false positives.
- `skills/self-contained-ship/scripts/scan-egress.sh` — Claude expanded extensions; Codex says still incomplete + no regression tests.
- `scripts/skill_integrity.py` — where anti-rollback goes (Codex builds after design fixed).
- `CODEX-DOUBLE-CHECK-SPEC-2.0.3.md` — the spec; needs #3 redesign + #4 order fix.
- `skills/registry.json` release currently `2.0.2` (bump to `2.0.3` LAST, before manifest gen).

## Correct release sequence (Codex's, adopted)
1. Repair guard + scanner with red-before-green fixtures. 2. Replace "highest local tag" with explicit external freshness-floor contract. 3. Bump release/schema/sequence + changelog. 4. Generate manifest -> sign -> verify. 5. Independent exact-head review before ANY PR/release.

## Round-2 progress (Claude, after Codex CHANGES_REQUIRED)
- **#1 guard DONE + tested (55/55).** Rewrote tokenizer to quote-aware `shlex` (fixes the over-block false positive: commit messages no longer trip it), added `!`-shell-alias detection, whole-tree pathspecs (`.`/`:/`/`*`/`:(top)`), documented residuals. Fixed a missing-last-token bug in the tokenizer read loop.
- **#2 scanner DONE + tested (6/6, `test-scan-egress.sh`).** Content-based enumeration (not extension) closes extensionless/UPPERCASE/novel; symlinks flagged; binaries reported UNSCANNED not silent-green.
- **#3 anti-rollback RE-SPEC'd for Codex** (my "highest local tag" was wrong): external freshness floor — env/OS-pinned `IDC_SKILLS_MIN_SEQUENCE` + signed `releases.json` index published outside the tree. Honest floor: fully-offline whole-tree rollback undetectable.
- **#4 release order FIXED in spec:** finalize registry+sequence+changelog+all controlFiles FIRST, THEN manifest → sign (signature is the LAST mutation), THEN independent review → PR.
- Branch `v2.0.3-hardening` HEAD after this commit. `verify` intentionally RED (controlFiles changed; re-sign is Codex's finalized-order release step). Codex now: verify #1/#2, build #3 anti-rollback, do the correct-order re-sign, ship.

## Do NOT
Push/tag/merge/promote/sign without the full loop. Don't self-certify. Don't bump registry AFTER manifest gen (sign is last). Anti-rollback via local tags = false confidence — use an external floor.
