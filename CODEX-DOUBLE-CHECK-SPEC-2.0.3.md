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

## 1. Double-check what Claude built on `v2.0.3-hardening` (verify, don't trust) — ROUND 3
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
  `*branch*` substring bug). Fixtures **`test-block-dangerous-git.sh` now 97/97**. Beyond the round-2 probes,
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
  <glob>`**. New regression suite **`test-scan-egress.sh` 21/21**, each class isolated so no assertion is
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
  scripts**; the full shellcheck list exits 0. Confirm: `pytest` 74, `validate_skills.py` 50/0, guard 97/0,
  scanner 21/0, integrity matrix green, `manifest --out <tmp>` OK, `verify` RED-by-design (local_bytes +
  external_reference_set differ until the finalized-order re-sign).

## 2. IMPLEMENTATION RECORD — anti-rollback freshness (Codex-built; independent review required)

> **The design text below is retained as the pre-build decision record, not the
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

### Superseded pre-build design record
Round-2 re-verify verdict: the design is "materially better but not yet safe to implement as written." This
revision closes the five gaps Codex named. Ship **(a)+(b)** with the corrections below; **(c)** optional.

**Problem:** `verify` re-reads the repo each run; a repo-editor can present any *previously valid, signed*
state and it lights green. **The root-of-trust constraint (state it in code + docs, do not paper over it):**
a **whole-tree** rollback restores the old manifest AND the old `skill_integrity.py` together, so the verifier
is rolled back too — an in-repo control cannot detect it, because the thing doing the detecting is also old.
True whole-tree anti-rollback therefore needs BOTH (i) a freshness reference the victim trusts that is not in
the rolled-back tree, AND (ii) an **enforcing component pinned outside the tree** (the tree's own verifier
cannot be trusted to enforce a floor it was rolled back to ignore). This is the TUF shape: no in-tree,
fully-offline verifier can defend against whole-tree rollback — say so, do not imply otherwise.

**(a) Monotonic `manifestSequence`** (integer ≥1) in the signed manifest, incremented every release, plus a
`MIN_MANIFEST_SEQUENCE` constant in `skill_integrity.py` (itself a signed controlFile). `verify` fails if
`manifestSequence < MIN_MANIFEST_SEQUENCE`. Defeats a **partial** rollback (old manifest against a *current*
verifier). Document that it does NOT defeat a whole-tree rollback (the constant rolls back with the file).

**(b) External freshness FLOOR — the whole-tree defense.** Two pieces, both required by their mode:

- **(b0) Verifier-hash bootstrap — CLOSES Codex gap #1 (the verifier rolls back too).** The freshness check
  must NOT be trusted to the tree's own verifier. The external signed index (b2) records the expected
  **`verifierSHA256`** of `skill_integrity.py`. A **trusted launcher that lives OUTSIDE any rolled-back tree**
  — in CI a pinned action/step or container; for the operator a tiny `verify-fresh` wrapper installed in the
  operator's environment, not the repo — (1) fetches the external index + its signature, (2) verifies the
  signature against the out-of-band `keys/allowed_signers` fingerprint, (3) compares the tree's
  `skill_integrity.py` SHA-256 to the index's `verifierSHA256`, and only THEN delegates to the (now-trusted)
  tree verifier with `--index`. Tree verifier hash ≠ index → REFUSE (rolled-back verifier). The launcher is
  the root of trust; document that it must not be sourced from the tree.
- **(b1) OS-protected floor, NOT a bare env var — CLOSES gap #2.** `IDC_SKILLS_MIN_SEQUENCE` (env) is
  **caller-controlled**, so it is **advisory only**: it may RAISE the floor for a run, but its absence or a
  low value is NEVER trusted as "fresh." The AUTHORITATIVE floor is an OS-protected monotonic store outside
  the workspace: a macOS Keychain generic-password item, a root-owned file, or a CI-platform secret managed
  by the provider (not the repo). **Fail-closed when required state is missing** (see modes): a required
  floor that is absent/unreadable → NOT-READY, never a silent pass.
- **(b2) Signed release index — the auditable external reference.** A `releases.json` published where a tree
  rollback cannot rewrite it (a protected branch, a GitHub Release asset, a pinned HTTPS raw URL), signed
  detached with the SAME Forge key + `keys/allowed_signers` principal. Schema — **CLOSES gap #5:**
  ```json
  { "schemaVersion": 1, "indexSequence": 7, "generatedAt": "2026-08-19T00:00:00Z", "validUntil": null,
    "releases": [ { "release": "2.0.3", "manifestSequence": 3,
                    "manifestSHA256": "<hex>", "verifierSHA256": "<hex of skill_integrity.py>",
                    "gitCommit": "<sha>" } ] }
  ```
  and a detached `releases.json.sig` over the **canonical** bytes (sorted keys, LF, no trailing space).
  - **Anti-replay — CLOSES gap #3.** The index carries its OWN monotonic `indexSequence` (+ `generatedAt`,
    optional `validUntil`). The launcher persists a **last-seen checkpoint** (highest `indexSequence` ever
    accepted) in the OS-protected store (b1) and REFUSES any index with `indexSequence` < checkpoint (replay
    of an old, validly-signed index) or a past `validUntil`. First run seeds the checkpoint only under an
    explicit `--trust-on-first-use` (or an operator-supplied initial floor) — document the TOFU risk. Honest
    residual: with neither a persisted checkpoint NOR a live timestamp authority, a one-snapshot replay of an
    old signed index is undetectable; the OS checkpoint closes it for the operator, and CI always fetches the
    current index from the protected branch. State it.
  - **Equivocation — part of gap #5.** Two index entries with equal `manifestSequence` but different
    `manifestSHA256` (or an `indexSequence` collision), OR a tree manifest whose `manifestSequence` matches an
    index entry but whose `manifestSHA256` differs → HARD FAIL (fork/equivocation).
  - **External-path enforcement — part of gap #5.** `--index <path|url>` MUST resolve OUTSIDE `repo_root`
    (reject any path under the tree — else the rollback rewrites the index too); a URL must be HTTPS with a
    pinned host; the `.sig` is fetched from the same external location and verified before any field is read.
  - **Atomic publication — part of gap #5.** Publish `releases.json` + `.sig` atomically (write temp, verify
    the pair locally, rename both) so a verifier never sees a new index with a stale/absent signature; a new
    index whose signature doesn't cover its exact bytes → FAIL.

**No silent downgrade — CLOSES gap #4.** "Strongest-available-wins" is REPLACED by **required-by-mode**:
- `--mode release` / `--mode ci`: the signed index (b2) **and** the verifier-hash bootstrap (b0) are
  REQUIRED; a missing/unreachable/suppressed required source → **FAIL CLOSED**, never a fall-through to a
  weaker check.
- `--mode operator`: the OS floor (b1) OR the signed index (b2) is REQUIRED (fail-closed if neither present).
- `--mode offline`: nothing required, but the result is a distinct `freshness: UNVERIFIED` that is **never
  counted as READY** and prints the honest whole-tree hole. A required source never becomes optional because
  it was suppressed or unavailable.

**(c) Optional TUF-style timestamp role** — future work; build only if judged worth the weight.

**Red fixtures (fail-before / pass-after) — each MUST have a test:**
1. old manifest (lower `manifestSequence`) + current verifier → FAIL under (a).
2. tree `manifestSequence` below the OS/index floor → FAIL under (b1/b2); below only the advisory env → the
   env RAISES the floor but its absence never passes a stale tree.
3. index `indexSequence` < persisted checkpoint → FAIL (b2 replay); expired `validUntil` → FAIL.
4. index entry equal `manifestSequence`, different `manifestSHA256` → FAIL (equivocation).
5. tree `skill_integrity.py` SHA-256 ≠ index `verifierSHA256` → FAIL at the launcher (b0 rolled-back verifier).
6. `--index` path INSIDE `repo_root` → FAIL (refuse in-tree index); new index with stale/absent `.sig` → FAIL.
7. `--mode ci` with the index unreachable → FAIL CLOSED (no downgrade).
8. `--mode offline`, no index, no OS floor → `freshness: UNVERIFIED`, exit distinct-from-READY (documents the
   honest hole), never green.

## 3. Re-sign + release loop — CORRECT ORDER (Codex finding #4: my earlier order signed before bumping)
Claude's edits changed controlFiles, so `verify` is now RED locally (local_bytes) by design — that means the
manifest must be regenerated + re-signed. **The signature must be the LAST mutation.** Any file change after
signing (a version bump, a changelog line, a sequence field) invalidates the signature and yields a false
"needs re-sign" or, worse, a shipped mismatch. So finalize EVERYTHING first:
1. Finish (1)-verify + (2)-build. Re-run `pytest` (74), `validate_skills.py` (50/0), guard fixtures (97/0),
   scanner fixtures (`test-scan-egress.sh`, 21/0), integrity fixtures (matrix green), full shellcheck (exit 0),
   and `manifest --out <tmp>` (must print MANIFEST OK, not REFUSED). CI now runs the scanner suite + shellchecks
   both scanner scripts, so a red-before-green regression is caught in `validate.yml`.
2. **Finalize ALL content FIRST:** bump `registry.json` release → `2.0.3`; set the new `manifestSequence`;
   write the changelog; land every control-file edit (guard, scanner, `skill_integrity.py`, wizard). Nothing
   else may change after this point.
3. **THEN** `skill_integrity.py manifest` → regenerate over the finalized tracked tree; operator runs `sign`
   (1Password biometric); the in-tree `verify` may report only `contentReady=true` at 5/5. If anything needs
   changing after this, go back to step 2.
4. Independent exact-head review (a different family than the builder) BEFORE any PR/release action.
5. PR #4 on the forge; merge; promote that exact commit object to `Island-Dev-Crew` without rewriting it.
6. Construct and biometrically sign the second, domain-separated release index artifact; publish its immutable
   pair, provision the external config/checkpoint, and obtain external `readyToRun=true`. Only then create the
   annotated `2.0.3` tag and run the verified reinstall.
7. Then the loop continues: **Kimi K3 red-teams the real 2.0.3**; anything new → 2.0.4. Nothing is "done"
   until an independent family re-breaks the shipped tag and comes back empty.

## The law
Do not self-certify. The family that built a fix does not sign off on it — Claude built §1, you verify it;
you build §2, Claude (or Kimi) verifies that. A green `verify` proves the manifest is intact and signed; it
does not prove the guard is exhaustive or the scanner complete. State enforced-vs-advisory for each.
