# CODEX DOUBLE-CHECK + BUILD SPEC — 2.0.3 hardening (post-2.0.2 red-team reconciliation)

> Context: 2.0.2 shipped (public `main` `76a7bf0`, tag `2.0.2` → `00f26a1`, `verify` READY 5/5 with a
> real signature). Kimi K3's red-team ran against the pre-release snapshot `574346e`; Claude (4.8)
> reconciled every finding against the **released** code with reproducible tests. 2.0.2's CRITICAL
> (forged green light / anchor swap / appended-signer) is CLOSED. This 2.0.3 hotfix closes the three
> proven-still-open items. Claude built two of them on branch `v2.0.3-hardening`; you double-check
> those, build the third, regenerate + sign the manifest, and run the release loop.

## Reconciliation of record (proven against released 2.0.2, not claimed)
- CLOSED: anchor swap → FAIL; verifier tamper → FAIL; skill-body tamper → FAIL; **appended second
  signer line → `NOT READY 0/5, FAIL signature`**. The integrity gate holds.
- OPEN (this 2.0.3): (1) git-guard bypasses `git${IFS}push` + `git -c alias.p=push p`; (2) `scan-egress.sh`
  skipped `.sh/.py/.yaml`; (3) no anti-rollback freshness.

## 1. Double-check what Claude built on `v2.0.3-hardening` (verify, don't trust)
Claude addressed BOTH review-round-2 findings (false positives AND missing classes); RE-VERIFY, don't rebuild:
- **`skills/agent-guardrails/scripts/block-dangerous-git.sh`** — now **quote-aware `shlex` tokenization**
  (the real fix for the over-block finding: a commit MESSAGE mentioning `git config alias.p push` is ONE
  token and no longer trips detection), plus `${IFS}` neutralization, **alias-injection detection incl.
  `!`-prefixed shell-command aliases** (`config alias.x '!git push'`), and **whole-tree pathspecs**
  (`.`, `:/`, `*`, `:(top)`). Fixtures: **`test-block-dangerous-git.sh` now 55/55** (was 37) — includes
  false-positive regressions (commit messages that must NOT block). The header now documents the true
  residuals a string classifier cannot close (dynamic `$C push` indirection, `eval`/`sh -c`, renamed binary,
  prior-command alias, malformed payload → fail-open). RE-RUN the suite; attack for a NEW class; keep advisory.
- **`skills/self-contained-ship/scripts/scan-egress.sh`** — now enumerates by **CONTENT, not extension**
  (every regular file classified text-vs-binary via `grep -I`), closing extensionless / UPPERCASE / novel
  extensions. **Symlinks are flagged** (they break self-containment); **binaries are reported UNSCANNED**
  (not a silent green). New regression suite **`test-scan-egress.sh` 6/6** (extensionless, UPPERCASE,
  symlink, binary, waiver, clean). RE-RUN it. Kimi's protocol-relative-pixel / timing / DNS channels remain
  partly regex-residual — decide in-scope vs documented-residual.

## 2. BUILD — anti-rollback freshness (the design item; yours to implement in `skill_integrity.py`)
**Problem:** `verify` re-reads the repo each run; a repo-editor can present any *previously valid, signed*
state and it lights green. There is no freshness binding.

**The honest constraint (state it in code + docs, do not paper over it):** if an attacker rolls back the
**whole** repo — old manifest AND old `skill_integrity.py` together — an in-repo counter cannot detect it,
because the verifier is rolled back too. True anti-rollback needs a freshness reference the *victim* trusts
that is NOT inside the rolled-back tree.

**Implement — layered, weakest-to-strongest; ship at least (a)+(b):**
- **(a) Monotonic `manifestSequence`** (integer) in the signed manifest, incremented every release, plus a
  `MIN_MANIFEST_SEQUENCE` constant in `skill_integrity.py` (itself a signed controlFile). `verify` fails if
  `manifestSequence < MIN_MANIFEST_SEQUENCE`. Defeats a partial rollback (old manifest against a current
  verifier). Document that it does NOT defeat a whole-tree rollback.
- **(b) External freshness FLOOR — the real whole-tree defense (Codex's correction; my earlier
  "highest local tag" idea was WRONG — local tags are attacker-writable, annotated tags are not inherently
  immutable, and a whole-tree rollback restores the old verifier too).** The floor must live OUTSIDE the
  rolled-back tree and be trusted by the victim. Implement a checked contract, strongest-available-wins:
  1. **Env/OS-pinned floor:** `verify` reads `IDC_SKILLS_MIN_SEQUENCE` (env, or an OS-keychain entry) and
     fails if `manifestSequence < floor`. The operator/CI sets it once per release; it is not in the repo,
     so a tree rollback cannot lower it. Fail-closed only when the floor is *present*; absent → advisory
     warning (offline/first-run), never a silent pass.
  2. **Signed release index (preferred for CI/public):** a tiny append-only `releases.json` — `{release,
     manifestSHA, manifestSequence}` per release — signed with the SAME 1Password key and published to a
     location the tree rollback can't rewrite (a protected branch, a GitHub Release asset, or a pinned raw
     URL). `verify --index <url|path>` fails if the tree's manifest is behind the index's newest entry, or
     if its manifestSHA doesn't match the index. This is the auditable external reference.
  3. State the honest floor: fully offline with no env floor and no index, whole-tree rollback is
     undetectable — say so; do not imply otherwise.
- **(c) Optional TUF-style timestamp role** — note as future work; build only if judged worth the weight.
Add red fixtures (fail-before, pass-after): rollback to an older signed manifest with a current verifier →
FAIL under (a); a tree behind the env floor → FAIL under (b.1); a manifest behind / mismatching the signed
index → FAIL under (b.2); no floor + no index offline → advisory WARN, exit documents "freshness unverified".

## 3. Re-sign + release loop — CORRECT ORDER (Codex finding #4: my earlier order signed before bumping)
Claude's edits changed controlFiles, so `verify` is now RED locally (local_bytes) by design — that means the
manifest must be regenerated + re-signed. **The signature must be the LAST mutation.** Any file change after
signing (a version bump, a changelog line, a sequence field) invalidates the signature and yields a false
"needs re-sign" or, worse, a shipped mismatch. So finalize EVERYTHING first:
1. Finish (1)-verify + (2)-build. Re-run `pytest`, `validate_skills.py` (50/50), guard fixtures (55/0),
   scanner fixtures (`test-scan-egress.sh`, 6/0), integrity fixtures, shellcheck.
2. **Finalize ALL content FIRST:** bump `registry.json` release → `2.0.3`; set the new `manifestSequence`;
   write the changelog; land every control-file edit (guard, scanner, `skill_integrity.py`, wizard). Nothing
   else may change after this point.
3. **THEN** `skill_integrity.py manifest` → regenerate over the finalized tree; operator runs `sign`
   (1Password biometric); `verify` → READY 5/5. If anything needs changing after this, go back to step 2.
4. Independent exact-head review (a different family than the builder) BEFORE any PR/release action.
5. PR #4 on the forge; merge; promote to `Island-Dev-Crew`; annotated tag `2.0.3`; set the external freshness
   floor / update the signed release index; verified reinstall.
6. Then the loop continues: **Kimi K3 red-teams the real 2.0.3**; anything new → 2.0.4. Nothing is "done"
   until an independent family re-breaks the shipped tag and comes back empty.

## The law
Do not self-certify. The family that built a fix does not sign off on it — Claude built §1, you verify it;
you build §2, Claude (or Kimi) verifies that. A green `verify` proves the manifest is intact and signed; it
does not prove the guard is exhaustive or the scanner complete. State enforced-vs-advisory for each.
