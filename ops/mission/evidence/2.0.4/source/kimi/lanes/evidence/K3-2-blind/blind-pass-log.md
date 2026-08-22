# K3-2 Blind pass log (recorded BEFORE opening tests/ or fixture matrices)

Anchor state at this point: tag obj/commit/tree, tag ssh signature, manifest sha256+sig,
releases.json sha256+sig, launcher/verifier pinned hashes all VERIFIED (see evidence/K3-2-setup/).
Only source read so far: bootstrap/idc_verify_fresh.py (full, 1597 lines). tests/ NOT yet opened.

## Blind map of the launcher trust order (from source only)

1. `verify_release(repo_root, config_path, ...)`: repo_root resolved strict; config_path = absolute();
   launcher_path = absolute(__file__) unless overridden. Both must be OUTSIDE repo
   (`_path_is_within`, uses resolve + samefile walk for nearest-existing-parent).
2. Launcher + config read via `_read_regular_snapshot` (O_NOFOLLOW, lstat/fstat dev+ino match,
   optional nlink==1); both must be owner-controlled, not group/world writable.
3. `parse_config`: exact keys; pins executables {python,git,sshKeygen} as absolute paths OUTSIDE the
   repo with per-file sha256, owner-controlled, not 022-writable, X_OK; running interpreter must be
   samefile(configured python); consumerPath/consumerHome external dirs; source = file
   (absolute, outside repo) or https (https scheme only, hostname in lowercase allowedHosts,
   no userinfo, no fragment, port None|443, maxRedirects 0-3); checkpointPath absolute & outside repo;
   bootstrapIndexSHA256 + minimum{Index,Manifest}Sequence floors.
4. Repo anchors read: keys/idc-skills-signing.pub + keys/allowed_signers; `validate_anchor` pins
   compiled-in EXPECTED_SIGNING_FINGERPRINT (SHA256:LBkF4ekX...) via ssh-keygen -lf in scrubbed env
   (PATH=os.defpath-resolved or pinned sshKeygen dir, HOME/TMPDIR redirected to 0700 temp).
   => Root of trust for the FIRST fetch = compiled-in fingerprint constant + externally protected
      config (bootstrapIndexSHA256) + pinned executable hashes. The repo supplies the public key but
      it is bound to the compiled-in fingerprint.
5. manifest.json + .sig read; `verify_signature` (ssh-keygen -Y verify, namespace "file", temp-dir
   files, scrubbed env); `parse_manifest` (schema idc-skill-integrity/v3, profile=release,
   skillCount=50, repositoryFiles non-empty).
6. Captured launcher/verifier/pubkey/allowed_signers bytes must equal manifest.repositoryFiles
   records (size+sha256) => installed launcher self-checks against signed source bytes, and
   verifierSHA256/launcherSHA256 index pins bind these via the newest-entry tuple comparison.
7. mode=offline: staged copy verified, manifest+verifier re-read after; returns readyToRun=False,
   freshness=UNVERIFIED, exit 3. Consumer NEVER authorized offline. Fail CLOSED.
8. Online: capture_index_source (file: single-link regular snapshots; https: pinned redirect handler,
   ProxyHandler({}) disables proxy env, 20s timeout, reads maximum+1, post-fetch final-URL recheck).
   index sha256 -> verify_signature(namespace idc-skills-release-index-v1) -> parse_index
   (canonical-JSON only, dup-key reject, schema, sequences strictly increasing+unique, unique names,
   generated<=now+300s, validUntil>now, validUntil>generated, lifetime<=31d, exact-second RFC3339).
9. index floor vs config; NEWEST entry (releases[-1]) must equal {release, manifestSequence,
   manifestSHA256, verifierSHA256, launcherSHA256, gitCommit} of the ACTUAL repo; gitCommit from
   hardened git (in-tree real .git dir required, GIT_CONFIG_NOSYSTEM, empty global/system config,
   empty hooksPath, fsmonitor/untrackedCache off, no replace/lazy-fetch, scrubbed env = only
   PATH/LANG/LC_ALL/TZ; caller's GIT_* env all scrubbed). Whole git tree must equal manifest closure
   exactly (blob sha1 recomputed per file, modes 100644/100755 only).
10. Checkpoint: parent dir mkdir 0700, symlink/writable/owner checks, .lock sidecar (O_NOFOLLOW,
    nlink==1, flock). validate_checkpoint: no checkpoint -> index digest must equal
    bootstrapIndexSHA256; else new indexSequence >= old, same-sequence different-digest rejected,
    every old release entry must appear unchanged in new index (history rewrite/removal rejected).
11. Staged repo: every repositoryFiles entry byte-copied to 0700 temp, perms from manifest,
    manifest+sig injected; content verifier runs as pinned python -I -B on the CAPTURED verifier
    bytes in temp, env scrubbed, HOME/TMPDIR redirected.
12. `_require_content_ready`: content report must be contentReady 5/5 release 50 content-only and
    must NOT contain readyToRun (in-tree verifier emitting whole-tree readiness = error).
    readyToRun=true is emitted ONLY in this launcher, after: index sig+expiry, newest-entry tuple
    equality, git tree equality, checkpoint validation, content 5/5, re-read of
    manifest/verifier/launcher/config (post-verify drift check), RE-PARSE of index (expiry re-check)
    and RE-PARSE of config, checkpoint re-validate+write under second lock, optional consumer run
    (with ANOTHER index re-parse immediately before).
13. Consumer: runs pinned python -I -B -c bootstrap -> runpy on staged_repo/scripts/{install,
    pretooluse-skill-integrity,reaccept}.py; blocks `--repo-r*` arg smuggling; env = scrubbed PATH
    (pinned exe dirs + consumerPath), HOME=consumerHome, TMPDIR=temp; handoff marker env is
    documented as NOT the trust boundary.
14. Checkpoint is written BEFORE consumer runs; consumer exit code is propagated as process exit;
    report includes consumerExitCode.

## Blind hypotheses to test (H#)
- H1 (obj1): index whose newest entry is an OLDER release (e.g. 2.0.2) + repo at 2.0.2 ->
  accepted when checkpoint/bootstrap authorizes that index. Expected: BY DESIGN (index is the
  freshness authority); only interesting if older index passes AGAINST a checkpoint that has seen
  newer (expect reject via indexSequence/history rules).
- H2 (obj2): lower manifestSequence in newest entry -> tuple mismatch reject; lower indexSequence
  -> checkpoint reject; truncation/reorder/duplicate -> parse_index or checkpoint reject.
- H3 (obj3): same-seq different-digest -> explicit reject. Checkpoint roll-back (older checkpoint
  bytes restored) -> likely reject (lower seq vs new index is FINE: old checkpoint + new index is
  normal flow! Rolling checkpoint BACK then presenting the CURRENT index is accepted - check
  whether that re-opens anything: history check requires old entries subset, so a rolled-back
  checkpoint with FEWER entries just re-accepts; a rolled-back checkpoint can't force older index).
- H4 (obj4): boundary arithmetic: expires==now reject, expires==now+1s accept, lifetime
  ==31d accept / 31d+1s reject, generated==now+300s accept / +301s reject, fractional seconds reject.
- H5 (obj5): first run wrong bootstrap digest -> reject; TOCTOU index/sig pair mismatch -> sig
  verify over actual bytes -> reject.
- H6 (obj6): redirect to non-allowed host / http / userinfo / port !=443 -> reject; fragment in
  config URL -> reject. NOTE: redirect handler does NOT check fragment on redirect target (harmless,
  fragments aren't sent). Partial read / oversized body -> >maximum reject. Split origins (index
  host A, sig host B, both in allowedHosts) -> appears ACCEPTED by design (allowedHosts is a set
  shared by both URLs) - check if cross-host substitution of a sig for a different index matters
  (sig won't verify -> reject; but same index bytes served from B = same trust, fine).
- H7 (obj7): config/launcher path inside repo via symlink/mount alias -> _path_is_within catches
  via resolve+samefile. checkpoint parent symlink -> reject. Config itself symlink -> O_NOFOLLOW
  reject. Case-fold: Linux ext4, N/A mostly.
- H8 (obj8): installed launcher bytes != manifest record -> reject (self-check at step 6), and
  != index launcherSHA256 -> tuple mismatch. First-fetch authentication order documented above.
- H9 (obj9): verifier bytes != manifest/index -> reject at step 6/9. Captured verifier is executed
  from temp copy of CAPTURED bytes (not repo re-read) -> no mid-run substitution of the verifier.
- H10 (obj10): consumer executes STAGED snapshot, not live repo -> validate-then-run gap closed for
  repo files; manifest/verifier/launcher/config re-read after content verify; index re-parsed before
  checkpoint write and before consumer. Residual: staged snapshot could be swapped in /tmp? temp dir
  is 0700 under launcher's TMPDIR; consumer bootstrap takes staged path as argv - no re-check that
  staged files unchanged between content verification and consumer exec (same process, 0700 dir,
  attacker would need same-uid write access - out of scope).
- H11 (obj11): GIT_* env scrubbed (env replaced wholesale); hooks/config/fsmonitor neutralized.
  Attempt: poison repo .git/config with hooksPath/fsmonitor/aliases -> ignored. GIT_CONFIG_COUNT
  style env can't survive env replacement. .git as symlink/file/gitfile -> reject. core.worktree
  overridden on CLI. gitattributes irrelevant (no checkout/filter operations; ls-tree only).
- H12 (obj12): env wholesale replacement kills PYTHON*/BASH_ENV/LD_*/NODE_OPTIONS for children;
  ssh-keygen found via os.defpath OR pinned; temp dirs via mkdtemp random. Launcher itself inherits
  caller env (e.g. PYTHONPATH) when invoked - but it must run under pinned python; PYTHONPATH could
  shadow stdlib modules of the LAUNCHER ITSELF? -I not used for launcher; check: launcher is a
  script run by operator; PYTHONPATH could inject a fake `json`/`hashlib`? Worth a look (obj12).
- H13 (obj13): offline/expired/index fetch failure -> exit 2/3, readyToRun False. No fail-open
  path seen.
- H14 (obj14): checkpoint advances before consumer; consumer failure leaves advanced checkpoint.
  Not a rollback vector (checkpoint only records verified signed index).

## Blind suspicion ranking (pre-test)
Most promising: H8/H12 launcher-process env (PYTHONPATH etc. at launcher import time — outside the
scrubbed-child boundary), H6 redirect fragment omission (likely cosmetic), H3 checkpoint
restore-older semantics (likely benign), H5 first-use bootstrap usability (digest must be exact).
