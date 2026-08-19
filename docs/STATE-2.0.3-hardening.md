# STATE — 2.0.3 hardening (durable, survives context compaction)

State, not instructions. Round 3 of the Kimi→Codex→Claude loop.

## Where things stand
- **2.0.2 is SHIPPED**: public `Island-Dev-Crew/idc-skills` main `76a7bf0`, staging `Navigata1/idc-skills-forge`
  main `76a7bf0`, annotated tag `2.0.2` → `00f26a1`. `verify` READY 5/5 with a real 1Password signature. Key
  fingerprint `SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA` (1Password "Forge 50 SSH Key"), anchor
  `keys/allowed_signers` (principal `idc-skills`).
- **2.0.2 CRITICAL CLOSED** (tamper-proven): anchor swap → FAIL, verifier tamper → FAIL, skill-body tamper →
  FAIL, appended second signer → FAIL. The integrity gate holds.
- **Branch `v2.0.3-hardening`** — NOT on either remote, NOT pushed. Round-2 head was `b5aaa83`; round-3 fixes
  land as the next commit on this branch (run `git rev-parse HEAD` for the exact current hash — this file is
  committed *as* that round-3 head, so it names its parent `b5aaa83`, not a stale head).

## The loop (discipline)
Kimi K3 red-teams → Codex builds/reconciles → Claude verifies → repeat. No family certifies its own work.
Codex re-verified round 2 (`b5aaa83`) and returned **CHANGES_REQUIRED** (8 blocking + anti-rollback spec gaps).
Round 3 below addresses all of them. Claude built the guard/scanner fixes → **Codex verifies** (does not
rebuild); Codex builds the anti-rollback → **Claude/Kimi verify**. Guard/scanner are `advisory`; the integrity
gate is `enforced`.

## Round-3 status (Codex CHANGES_REQUIRED against `b5aaa83`)
All 8 blocking findings reproduced first (ground truth), then fixed + locked with red-before-green fixtures.
Verified LOCALLY (pending independent Codex re-verify — NOT self-certified as done):
1–3. **Guard** (`skills/agent-guardrails/scripts/block-dangerous-git.sh`) rebuilt as a thin bash wrapper over
   a scoped **Python classifier**: segment on real separators (incl. **newline**, subshell `(`/`)`, `$(…)`,
   backtick) → find the git invocation IN COMMAND POSITION → classify only its args. Closes multiline (#1),
   missing spellings (#2), scoped-away false positives (#3). Fixtures **97/97**.
4–5. **Scanner** (`skills/self-contained-ship/scripts/scan-egress.sh`): binaries + symlinks + non-regular files
   now **fail closed** (green ⇒ every file scanned-clean or `--allow-binary`-waived), `grep -a` scans binary
   strings, NUL-safe enumeration, bash-3.2 `set -u`-safe (crash gone). Fixtures **21/21**, each class ISOLATED.
   Both scripts shellcheck-clean.
- **Self-red-team (adversarial panel, 8 agents) — closed MORE than Codex's list, before handing back:**
  GUARD: `(git push)` subshell / `<(git push)` process-sub bypass; long-option **abbreviation** (`reset --har`,
  `clean --for`, `checkout --forc`, `branch --dele --forc`); **bundled** checkout/restore force flags (`-fq`,
  `-SW`); the **`switch`** subcommand; **exclude pathspec** `:!`/`:^`; case-variant **`ALIAS.`** config section;
  alias values with a leading global flag (`alias.p=-p push`); bang-alias with a glued `;`; and false positives
  `echo git push` / `grep -r git push` / `alias.unstage='reset HEAD'`. SCANNER: **DOCTYPE-strip laundering**
  (removed the unbounded `<!DOCTYPE …>` strip — external DTD/SYSTEM URLs now correctly flagged), protocol-
  relative `//host` in srcset/poster/action/formaction/@import/image-set/meta-`url=`, `stun:`/`turn:` schemes,
  `fetch()`/XHR **context-free false positives** made URL-contextual, a **FIFO hang** (non-regular files fail
  closed, never read), and a `--allow-binary` glob **laundering an embedded URL** (embedded-URL binaries now
  fail even when glob-waived). Documented residuals kept honest (dynamic/`eval`/`sh -c`/prior-alias/heredoc
  over-block; static-regex obfuscation → rung-2 sealed-load is the enforced proof).
6. **Manifest refusal** (was a hard blocker): the scanner test embedded literal `https://…`/`http://169.254…`
   → `MANIFEST REFUSED — unclassified external reference`. Fixed by assembling every fixture URL from fragments
   at runtime, so the shipped source is inert to the classifier. `manifest --out <tmp>` now prints **MANIFEST OK**.
7. **CI** (`.github/workflows/validate.yml`): now runs `test-scan-egress.sh` and shellchecks both scanner
   scripts; the guard's SC2016 is gone and the test harness's intentional `${IFS}` fixtures carry inline
   disables → full shellcheck list exits 0.
8. **This state file** rewritten (was internally stale: named `9ff1d6a` as head, marked guard/scanner "DONE").
- **Anti-rollback (Codex builds; spec only here)**: §2 of `CODEX-DOUBLE-CHECK-SPEC-2.0.3.md` revised to close
  the 5 spec gaps — verifier-hash bootstrap by an OUT-OF-TREE launcher (the rolled-back-verifier problem),
  OS-protected floor (env var is advisory-only), index anti-replay via `indexSequence` + persisted checkpoint,
  no-silent-downgrade required-by-mode, and full schema/bootstrap/equivocation/external-path/atomic-publish.

## Local proof (round 3)
`pytest` 74 · `validate_skills.py` 50/0 · guard 97/0 · scanner 21/0 · integrity matrix green · `manifest --out`
OK · full shellcheck exit 0 · `verify` **RED by design** (`local_bytes` + `external_reference_set` differ; the
signature itself still PASSes — tamper-evidence working. The finalized-order re-sign reconciles it).

## Files in play
- `skills/agent-guardrails/scripts/block-dangerous-git.sh` (+ `test-block-dangerous-git.sh`, 97 fixtures) (+ SKILL.md doc)
- `skills/self-contained-ship/scripts/scan-egress.sh` (+ `test-scan-egress.sh`, 21 fixtures) (+ SKILL.md doc)
- `.github/workflows/validate.yml` (scanner suite + shellcheck wired)
- `scripts/skill_integrity.py` — where anti-rollback goes (Codex builds after the §2 design)
- `CODEX-DOUBLE-CHECK-SPEC-2.0.3.md` — §1 round-3 re-verify notes, §2 anti-rollback redesign, §3 order
- `skills/registry.json` release currently `2.0.2` (bump to `2.0.3` LAST, before manifest gen)

## Correct release sequence (Codex's, adopted — signature is the LAST mutation)
1. Codex re-verifies §1 (guard/scanner) + builds §2 (anti-rollback) with red fixtures. 2. Finalize ALL content
FIRST: bump `registry.json` → 2.0.3, set `manifestSequence`, changelog, land every control-file edit. 3. THEN
`manifest` → operator `sign` (biometric) → `verify` READY 5/5. 4. Independent exact-head review (different
family than the builder). 5. PR on the forge → merge → promote to `Island-Dev-Crew` → tag `2.0.3` → set the
external freshness floor / signed index → verified reinstall. 6. Kimi K3 re-breaks the shipped 2.0.3; anything
new → 2.0.4.

## Do NOT
Push/tag/merge/promote/sign without the full loop. Don't self-certify. Don't bump registry AFTER manifest gen.
Anti-rollback via local tags = false confidence — use the external floor + out-of-tree launcher. Guard/scanner
stay `advisory`; never imply `enforced`.
