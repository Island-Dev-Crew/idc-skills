# Forge 50 content integrity and freshness gate

Release 2.0.3 separates two claims that one rollbackable repository must never
collapse into one:

1. `scripts/skill_integrity.py` proves that the current signed content matches
   the canonical manifest. Its report uses `contentReady`; it never emits
   `readyToRun`.
2. An independently installed copy of `bootstrap/idc_verify_fresh.py` proves
   that the manifest and verifier are the newest release authorized by a
   separately signed, expiring release index. Only that external launcher can
   emit `readyToRun=true`.

The trusted Forge signing fingerprint is:

```text
SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA
```

## Why the split is necessary

A whole-tree rollback restores an old manifest, verifier, installer, hook, and
workflow together. An old in-tree verifier can therefore approve its own old
rules. A monotonic number inside that same tree does not fix the problem.

The freshness launcher must live outside every checkout and be pinned by the
operator or platform. It authenticates an external release index, compares the
exact raw manifest, verifier, launcher, release sequence, and Git commit, then
executes a private captured copy of the authenticated content verifier. The
tracked launcher is distributable source and fixture material; running that
copy from inside the repository is refused.

## Content integrity: five independently red checks

`python3 scripts/skill_integrity.py verify` reports `contentReady=true` only
when all five checks pass:

1. **Signature:** the independently known fingerprint, `idc-skills` principal,
   `file` namespace, detached signature, v3 schema, canonical JSON, and strict
   positive `manifestSequence` agree.
2. **Local bytes:** all 50 registered skill trees and the complete Git-tracked
   release closure match signed SHA-256, size, and canonical POSIX-mode records.
   Inventory drift, unsafe
   file types, symlinks, case collisions, Unicode-normalization collisions,
   and mid-check mutation force red.
3. **External-reference set:** every HTTP(S) reference and detected network
   command occurrence is signed and classified.
4. **Remote content pins:** every `runtime-instruction` is re-fetched and must
   match its signed digest and final URL. Informational references and fixed API
   endpoints remain explicit allow-list entries, not pretend-pinned responses.
5. **Fetch/execute policy:** reviewed download/execute classes are denied unless
   the exact signed occurrence is an approved inert example or setup operation.

Fixture keys can prove the five-check implementation, so a fixture may be
`contentReady`. Fixture profile, wrong fingerprint, wrong cardinality, or stale
sequence can never satisfy the external release launcher.

## Freshness authority

The launcher validates canonical `idc-skills-release-index/v1` bytes under the
domain-separated OpenSSH namespace `idc-skills-release-index-v1`. Every release
entry binds:

```json
{
  "gitCommit": "40-lowercase-hex",
  "launcherSHA256": "sha256:...",
  "manifestSHA256": "sha256:...",
  "manifestSequence": 1,
  "release": "2.0.3",
  "verifierSHA256": "sha256:..."
}
```

The launcher requires its own installed bytes, the captured content verifier,
and the captured signing-anchor files to equal their signed Git-tracked source
records before either verifier mode can execute. It also requires that complete
execution closure to equal the newest entry's manifest and exact Git tree.
Ignored and untracked live extras are excluded rather than treated as
executable release content. The index is
strictly canonical, has unique increasing manifest sequences, carries its own
monotonic `indexSequence`, and expires within at most 31 days. A checkpoint
stores the accepted index sequence, exact index digest, and release history.
Lower replay, same-sequence/different-digest equivocation, or changed/removed
history fails closed. A first run has no history, so its external configuration
must pin the exact bootstrap index digest.

Index and manifest signatures use the same stable key but different namespaces:

```text
manifest: file
index:    idc-skills-release-index-v1
```

The launcher captures every signed input once, verifies the signature before
parsing it, rejects in-tree authority paths and unsafe external files, uses
bounded reads and HTTPS host/redirect policy, and builds a private execution
snapshot from the exact signed tracked-file closure. Ignored caches, local
secrets, and other untracked bytes never enter that snapshot. It binds the
signed closure to Git tree blobs without `git status`, filters, hooks, or
worktree conversions, and updates the checkpoint only after content and
freshness both pass.

## External deployment

Install the reviewed launcher source outside the repository into an
owner/admin-controlled directory. Install a canonical configuration outside the
repository as well. Its exact schema is:

```json
{
  "bootstrapIndexSHA256": "sha256:<exact-current-index>",
  "checkpointPath": "/absolute/protected/state/checkpoint.json",
  "consumerHome": "/absolute/operator-home",
  "consumerPath": [
    "/absolute/protected/bash-bin",
    "/absolute/protected/node-bin"
  ],
  "executables": {
    "git": {
      "path": "/absolute/protected/git",
      "sha256": "sha256:<exact-git-bytes>"
    },
    "python": {
      "path": "/absolute/protected/python3",
      "sha256": "sha256:<exact-python-bytes>"
    },
    "sshKeygen": {
      "path": "/absolute/protected/ssh-keygen",
      "sha256": "sha256:<exact-ssh-keygen-bytes>"
    }
  },
  "minimumIndexSequence": 1,
  "minimumManifestSequence": 1,
  "requireGitCommit": true,
  "schema": "idc-skills-freshness-config/v1",
  "source": {
    "allowedHosts": ["raw.githubusercontent.com"],
    "indexURL": "https://raw.githubusercontent.com/OWNER/REPO/trust-index/releases.json",
    "maxRedirects": 0,
    "signatureURL": "https://raw.githubusercontent.com/OWNER/REPO/trust-index/releases.json.sig",
    "type": "https"
  }
}
```

An external protected file pair may be used instead with `source.type=file`,
absolute `indexPath`, and absolute `signaturePath`. Repository-relative or
repository-resolving authority paths are refused.

The authoritative process must be created by an external protected wrapper or
runner that builds its environment from scratch, sets a protected temp root and
home, and then invokes the launcher through the exact absolute Python path named
and hashed in this configuration. Loader variables can execute before Python
code starts; neither a digest check performed by that Python process nor `-I`
can undo pre-start injection. The command examples below assume that clean
external process boundary already exists. Relying on the source file's `env`
shebang—or on candidate-controlled `scripts/install.sh` to bootstrap trust—is
not authoritative. `consumerPath` names only protected directories needed by
reacceptance (for example Bash and Node).
Digest-pinned Python, Git, and OpenSSH directories take precedence. Consumer
children receive a private temp directory, configured home, and a minimal
environment; caller `PATH`, Python loaders, dynamic-loader variables, shell
startup, Node options, Git configuration variables, proxy variables, and TLS
overrides are not inherited.

Owner-controlled user files protect against repository rollback but not an
attacker acting as the same OS user. Stronger claims require admin-owned POSIX
paths, Windows ACL enforcement, or CI/platform state outside candidate control.
The Python runtime and operating system remain part of the trusted computing
base. The launcher does not claim a cross-platform tamper-proof offline floor.
Without a live valid index, freshness is unverified and no child runs.

## Supported operation paths

Use the installed launcher for release verification and every mutating consumer:

```bash
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  verify

/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  install -- --target agents

/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  hook -- --installed-skills /absolute/harness/skills

/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  reaccept
```

`--mode release` is the default. `ci` and `operator` retain the same
fail-closed signed-index requirement in this release; there is no opportunistic
downgrade. `--mode offline verify` performs only the signed five-check content
proof, emits `freshness=UNVERIFIED`, never emits readiness, and exits `3`.
Offline mode never launches a consumer.

The installer still binds staged and installed skill bytes to the authenticated
manifest. Current direct CLI entrypoints refuse when the launcher's syntactic
handoff marker is absent; that caller-supplied marker is forgeable and prevents
only accidental bypass. It neither authenticates the launcher nor upgrades a
content-only invocation to release authority. The only supported authoritative
route is the independently pinned launcher above. The hook returns blocking
exit 2 on an absent marker, malformed input, content red, unknown skill,
installed-byte drift, payload disagreement, or any unexpected exception.

After external bootstrap, `scripts/install.sh` is a convenience delegate. It
requires `IDC_SKILLS_FRESHNESS_PYTHON`,
`IDC_SKILLS_FRESHNESS_LAUNCHER`, and `IDC_SKILLS_FRESHNESS_CONFIG` to name those
external paths and delegates through `python -I -B`. Those variables locate
externally protected artifacts; they do not replace signature, digest, runtime,
path, clean-process-environment, or checkpoint verification.

## Release ceremony

1. Finalize every repository byte, release number, sequence, test, and document;
   stage every new required control so the tracked closure is complete.
2. Generate and biometrically sign the v3 manifest under namespace `file`.
3. Commit the exact manifest and signature, replay that signed candidate from an
   ordinary clean clone, and obtain a different-family exact-head approval. No
   repository-controlled byte may change after this point.
4. Push that exact candidate to staging, require the repository CI, and merge
   through the protected review path. Capture the final staging merge commit and
   prove its tree is byte-identical to the reviewed signed candidate.
5. Build the canonical index entry from that final staging merge and the exact
   manifest, verifier, and externally installed launcher bytes. Sign the index
   under namespace `idc-skills-release-index-v1` as a second approval ceremony.
6. Publish index and signature as one immutable pair/protected staging commit,
   provision the external configuration's bootstrap digest and pinned runtime
   hashes, and run the launcher against an ordinary clean staging clone through
   a protected clean-environment wrapper and that exact Python runtime. Require
   staging `readyToRun=true` before promotion. A failed consumer does not roll
   the accepted freshness checkpoint backward.
7. Promote the exact staging merge and the exact index-pair commit to the public
   repository without rewriting either. Create an ordinary clean public clone,
   switch only the protected source configuration to the public raw URLs, and
   require the same `readyToRun=true` tuple and index digest from the public
   source. Reusing the checkpoint is valid only when index sequence, digest, and
   complete history are byte-identical.
8. Only after the public-source proof may the exact merge be annotated and
   SSH-signed as `2.0.3`, installed, reaccepted, or described as released.

Any repository mutation after manifest signing returns to step 1. Any final
commit rewrite after index construction returns to step 4.

Repository-owned CI can test content integrity and launcher fixtures, but it can
roll back with the candidate. Whole-tree CI authority requires an organization-
required workflow, pinned action/container, or runner policy configured outside
this repository.

## Honest scope

The combined system detects point-in-time byte tamper, signed-policy drift,
added references, reviewed remote-instruction drift, partial rollback, whole-
tree rollback against the external index, index replay after checkpointing, and
same-sequence index equivocation.

It does not prove signed intent is benevolent, protect a compromised signing
session, understand every obfuscation or shell grammar, sandbox the agent,
revoke credentials, survive compromise of the pinned Python/OS trust base,
prevent mutation of an external executable after its final check, make
user-owned trust state safe from that same user, or turn repository-owned CI
into an external root. Use admin-owned runtime/policy paths, least privilege,
sandboxing, scoped identities, network controls, replayable audit records, and
emergency credential/network shutdown for those layers.

No authority without evidence. A signature authenticates reviewed bytes; it
does not turn bytes into truth.
