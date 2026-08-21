# CODEX DOUBLE-CHECK + BUILD SPEC — 2.0.3 hardening (post-2.0.2 red-team reconciliation)

> Context: 2.0.3 is a candidate, not a shipped release. The registry is release
> `2.0.3`, `manifestSequence: 1`; the checked-in v3 manifest/signature bind the
> 2.0.3 content candidate at 5/5 while external freshness remains pending. The anti-rollback
> implementation is exact at `a58f59e`, with Claude Opus + OpenAI Codex **APPROVE**,
> 100 unit tests plus 20 subtests, and canonical validation 50/50. The guard's
> approved component lineage closes at `d0fac44` with 300/300 native macOS Bash
> 3.2 fixtures. Scanner diff `e98cfac6`, committed as `04a5bd4`, is independently
> approved with 589/589 native macOS Bash 3.2 fixtures.

## Reconciliation of record (historical 2.0.2 findings; not a 2.0.3 release claim)
- CLOSED: anchor swap → FAIL; verifier tamper → FAIL; skill-body tamper → FAIL; **appended second
  signer line → `NOT READY 0/5, FAIL signature`**. The integrity gate holds.
- OPEN (this 2.0.3): (1) git-guard bypasses `git${IFS}push` + `git -c alias.p=push p`; (2) `scan-egress.sh`
  skipped `.sh/.py/.yaml`; (3) no anti-rollback freshness.

## 1. Guard/scanner reconciliation — final matrices accepted
Round 2 (`b5aaa83`) was re-verified by Codex and came back CHANGES_REQUIRED: the guard still missed
multiline / equivalent-spelling / glued-`-c` classes AND false-positived on non-git text, the scanner
stayed green on binaries and crashed on binary/symlink-only input, and a test fixture poisoned the release
path. Claude round 3 **rebuilt** both (the guard as a scoped model, not a patch). RE-VERIFY, don't rebuild:
- **`skills/agent-guardrails/scripts/block-dangerous-git.sh`** — thin bash wrapper (payload extract + exit
  map) over a small **Python classifier** with a scoped model: **segment** on real shell separators
  (`; & | && ||`, **newline**, and `$(…)`/`` `…` `` boundaries, quote-aware) → **find the git invocation**
  (basename `git`/`git.exe`, through a path or `env`/`command`/`sudo` prefix) → classify **only that
  invocation's** args. Scoping detection to the git word is the real false-positive fix (a commit MESSAGE,
  `echo`, or `python -c` that mentions `alias.p=push` no longer trips it). Now also closes: multiline
  (`echo ok`⏎`git push`), whole-tree pathspec variants (`./`, `./.`, `:(top,glob)**`), branch force-delete
  bundles (`-df`, `-d -f`), `git.exe`, and glued `-calias.p=push`. Alias-value danger is tested by the value
  actually EXPANDING to a guarded subcommand (so `alias.sb=show-branch` is NOT a false positive — the old
  `*branch*` substring bug). R5 `c721304` remains historical **CHANGES_REQUIRED** evidence; the accepted
  guard lineage closes at component `d0fac44` and passes 300/300 native macOS Bash 3.2 fixtures. Beyond the round-2 probes,
  Claude ran an 8-agent **self-red-team** and closed everything it reproduced BEFORE handing back: `(git push)`
  subshell / `<(git push)` process-sub; long-option **abbreviation** (`reset --har`, `clean --for`,
  `checkout --forc`, `branch --dele --forc`); **bundled** checkout/restore force (`-fq`, `-SW`); the **`switch`**
  subcommand; **exclude pathspec** `:!`/`:^`; case-variant **`ALIAS.`** section; alias value with a leading
  global flag (`alias.p=-p push`); glued-`;` bang alias; plus false positives `echo git push` / `grep -r git push`
  / `alias.unstage='reset HEAD'` (git must be in COMMAND POSITION now). Shellcheck-clean (the SC2016 is gone; the
  test harness's intentional `${IFS}` fixtures carry an inline disable). Header documents the honest residuals
  (dynamic `$C push`, `git $(echo)push` word-assembly, `eval`/`sh -c`, prior-command alias, renamed binary,
  double-quoted `$(…)`, unrecognized wrappers; heredoc-body & `push --dry-run` conservative over-blocks;
  python3/jq absent → fail-OPEN). RE-RUN the suite; attack for a NEW *direct* class; keep advisory.
- **`skills/self-contained-ship/scripts/scan-egress.sh`** — enumerates by **CONTENT, not extension**, now
  **NUL-safe** (`find -print0`) so a newline in a filename can't split an entry, and **bash-3.2 `set -u`
  safe** (guarded array expansions — the binary/symlink-only crash is closed). **Secure-by-default on
  binaries:** a green result now means *every file scanned clean or explicitly waived* — a **symlink** fails
  closed, and a **binary** fails closed too (its strings are `grep -a`-scanned so an embedded URL is reported
  and fails; a URL-free binary fails as uncertifiable) until reviewed and waived with **`--allow-binary
  <glob>`**. R5 `c721304` remains historical **CHANGES_REQUIRED** evidence; exact scanner diff `e98cfac6`,
  committed as `04a5bd4`, passes 589/589 native macOS Bash 3.2 fixtures, with each class isolated so no assertion is
  satisfied by a coupled violation. The self-red-team also hardened the scanner: removed the **unbounded
  `<!DOCTYPE …>` strip** (a real laundering bypass — a `<!doctype`-wrapped `fetch()`/`url()`/`@import` was
  erased by the false-positive suppressor; external DTD/SYSTEM URLs are now correctly flagged), added
  protocol-relative `//host` coverage in srcset/poster/action/formaction/@import/image-set/meta-`url=` and
  `stun:`/`turn:` schemes, made bare `fetch()`/`XMLHttpRequest`/`EventSource` **URL-contextual** (a README
  naming them or a same-origin/`data:` fetch no longer false-fails), closed a **FIFO hang** (non-regular files
  fail closed and are never read), and stopped a `--allow-binary` glob from **laundering an embedded URL** (a
  URL-bearing binary fails even when glob-waived). Remaining static-regex obfuscation (runtime string-built
  URLs) is the documented residual — rung 2 sealed-load is the enforced proof.
- **Release-path repairs (were blockers, now fixed):** the scanner test assembles every fixture URL from
  fragments at runtime, so the shipped source carries **no literal `scheme://host`** for the manifest
  classifier to flag — `manifest` now builds clean (was `MANIFEST REFUSED — unclassified external reference`).
  CI (`.github/workflows/validate.yml`) now **runs `test-scan-egress.sh`** and **shellchecks both scanner
  scripts**; the full shellcheck list exits 0. The accepted component evidence is anti-rollback
  100 unit tests + 20 subtests, `validate_skills.py` 50/50, guard 300/300 at
  `d0fac44`, and scanner 589/589 at exact diff `e98cfac6` / commit `04a5bd4`.
  The R5 predecessor `c721304` remains historical CHANGES_REQUIRED evidence.

## 2. IMPLEMENTATION RECORD — anti-rollback freshness (implemented at `a58f59e`; review approved)

> **The design text below is retained as the implementation record, not the
> executable contract.** Implementation review proved that freshness could not
> safely be delegated back to `skill_integrity.py`, that arbitrary TOFU was too
> weak, and that an OS-floor-only operator path left the verifier closure
> unauthenticated. The authoritative 2.0.3 contract is the code plus
> `integrity/README.md`, summarized here.

Implemented contract:

- `scripts/skill_integrity.py` emits report schema v2 with `contentReady` and
  never emits `readyToRun`. Manifest schema v3 carries strict positive
  `manifestSequence`; 2.0.3 is sequence `1`, the first evidenced monotonic
  record—not an invented sequence `3`.
- `bootstrap/idc_verify_fresh.py` is distributable source. Only an independently
  installed copy, invoked through the absolute digest-pinned Python runtime in
  an external canonical configuration, can emit `readyToRun=true`.
- Canonical index schema is `idc-skills-release-index/v1`; `validUntil` is
  mandatory, whole-second UTC, and at most 31 days after `generatedAt`. Every
  newest entry binds release, manifest sequence, raw manifest SHA-256, verifier
  SHA-256, launcher SHA-256, and exact Git commit. Index signatures use the
  separate `idc-skills-release-index-v1` namespace.
- First use requires the exact externally provisioned index digest. The
  protected checkpoint binds index sequence, exact digest, and complete
  accepted history; replay, same-sequence equivocation, or history rewrite is
  red. No `--trust-on-first-use` escape exists.
- The external configuration pins Python, Git, and OpenSSH by absolute path and
  SHA-256, plus protected consumer home/search directories. Candidate Git
  hooks, filters, fsmonitor, replacement/lazy-fetch behavior, caller loader
  variables, and caller `PATH` do not participate in authorization.
- The signed Git-tracked closure binds SHA-256, size, and canonical POSIX mode.
  It is compared to Git tree blobs without worktree conversion, copied to a
  private snapshot, and only that snapshot is verified or consumed. Ignored and
  untracked local files never enter execution.
- `release`, `ci`, and `operator` modes all require the signed live index in
  2.0.3; suppression/unreachability is a hard failure. `offline` is content-only,
  reports `freshness=UNVERIFIED`, never runs a consumer, and exits `3`.
- Repository-owned CI can test content and launcher fixtures but cannot be a
  whole-tree freshness root. That claim requires an organization-controlled
  required workflow, pinned action/container, or runner policy outside candidate
  code.

The RED matrix now covers strict sequence types/floors, first-use pinning,
namespace separation, expiry before state transition, replay/equivocation and
history rewrite, verifier and runtime digest drift, in-tree/case-aliased
authority paths, linked Git metadata, Git fsmonitor/filter non-execution,
ignored-file exclusion, signed mode restoration, post-stage mutation, consumer
root override and environment injection, CI no-downgrade, offline exit `3`, and
an actual captured 50-skill verifier run. Any later wording in this section that
conflicts with this block is superseded.

### Historical design reconciliation

The pre-build proposal used an in-tree `--index` decision, an optional expiry,
an operator-floor fallback, and a TOFU path. Independent review rejected those
elements because the deciding verifier would roll back with the tree, a single
old signed index is replayable on first use, and opportunistic source selection
can silently downgrade authority. None of those mechanisms is part of 2.0.3.

The implemented contract above replaces them with an out-of-tree launcher,
mandatory bounded index expiry, an exact externally provisioned first-use
digest, complete checkpoint history, and the same signed-index requirement in
`release`, `ci`, and `operator` modes. The detailed canonical schemas and
deployment ceremony live in `integrity/README.md`; this file intentionally does
not preserve a second executable-looking schema.

## 3. Signed-content + release loop — CORRECT ORDER
The former 2.0.2/v2 signature did not authorize this 2.0.3 tree; the current v3
signature establishes content authority only. **The final biometric signature
is the last controlled-byte mutation.** Any file change after signing
invalidates it, so finalize EVERYTHING first:
1. Re-run the anti-rollback matrix (100 unit tests + 20 subtests),
   `validate_skills.py` (50/50), guard fixtures (300/300),
   scanner fixtures (589/589), integrity fixtures, full
   shellcheck, and both deterministic renderers.
   and `manifest --out <tmp>` (must print MANIFEST OK, not REFUSED). CI now runs the scanner suite + shellchecks
   both scanner scripts, so a red-before-green regression is caught in `validate.yml`.
2. **Finalize ALL content FIRST:** bump `registry.json` release → `2.0.3`; set the new `manifestSequence`;
   write the changelog; land every control-file edit (guard, scanner, `skill_integrity.py`, wizard). Nothing
   else may change after this point.
3. **THEN** `skill_integrity.py manifest` → regenerate over the finalized tracked tree; operator runs `sign`
   (1Password biometric); the in-tree `verify` may report only `contentReady=true` at 5/5. If anything needs
   changing after this, go back to step 2.
4. Independent exact-head review (a different family than the builder) BEFORE any PR/release action.
5. Transport and merge only after the exact signed candidate, clean-clone replay,
   independent review, required CI, and external freshness handoff are proven.
6. Construct and biometrically sign the second, domain-separated release index artifact; publish its immutable
   pair, provision the external config/checkpoint, and obtain external `readyToRun=true`. Only then create the
   annotated `2.0.3` tag and run the verified reinstall.
7. Then the loop continues: **Kimi K3 red-teams the real 2.0.3**; anything new → 2.0.4. Nothing is "done"
   until an independent family re-breaks the shipped tag and comes back empty.

## The law
Do not self-certify. The family that built a fix does not sign off on it — Claude built §1, you verify it;
you build §2, Claude (or Kimi) verifies that. A green `verify` proves the manifest is intact and signed; it
does not prove the guard is exhaustive or the scanner complete. State enforced-vs-advisory for each.
