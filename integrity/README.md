# Forge 50 external trust, content integrity, and freshness gate

## 2.0.4 assurance profile

The stable 2.0.4 public release activates signed content integrity and requires
the full content-signing fingerprint plus immutable release identity to match
two out-of-repository publications. It does **not** claim that the production
threshold root, external freshness authority, completed Kimi review,
Windows/NTFS seat, or freshness-authorized four-root parity has passed. In this
profile `contentReady` can be established; `readyToRun=true` cannot. The exact
claim boundary is [documented separately](../docs/2.0.4-release-scope.md).

The complete protocol below ships as reviewed source and remains the active
full-profile mission. Its production activation receives a later immutable
version identity rather than rewriting the 2.0.4 record.

The deferred full-assurance protocol composes three claims that one rollbackable repository must
never collapse into one:

1. An externally installed `verify_external_root.py` first authenticates a
   threshold-signed release statement from a separately obtained root. Its
   canonical output authorizes the exact content key and candidate artifacts;
   it never authorizes installation by itself.
2. `scripts/skill_integrity.py` proves that the current signed content matches
   the canonical manifest. Its report uses `contentReady`; it never emits
   `readyToRun`.
3. An independently installed copy of `bootstrap/idc_verify_fresh.py` proves
   that the manifest and verifier are the newest release authorized by a
   separately signed, expiring release index, and that they match the threshold
   verification result. Only that external launcher can emit
   `readyToRun=true`.

The current Forge content-signing fingerprint is:

```text
SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA
```

That value remains a content identity, not production threshold authority. For
a later full-assurance release, the threshold release statement must authorize
the same fingerprint and exact public-key plus allowed-signers bytes before the
freshness launcher accepts it. Scoped 2.0.4 instead requires direct comparison
of that fingerprint through both external witnesses before content verification.

## Why the split is necessary

A whole-tree rollback restores an old manifest, verifier, installer, hook, and
workflow together. An old in-tree verifier can therefore approve its own old
rules. A monotonic number inside that same tree does not fix the problem.

The root verifier and freshness launcher must live outside every checkout and
be pinned by the operator or platform. The root verifier starts from root bytes
whose digest was checked through two independent channels. The freshness
launcher then authenticates an external release index, compares the exact
threshold result, raw manifest, content key, verifier, launcher, release
sequence, and Git commit, and executes a private captured copy of the content
verifier. Tracked copies are distributable source and fixture material; running
the launcher copy from inside the repository is refused.

## Content integrity: five independently red checks

The release CLI requires the absolute externally selected `ssh-keygen` path and
its protected `sha256:` digest; it never discovers the verification executable
through candidate-controlled `PATH`. `python3 scripts/skill_integrity.py verify
--ssh-keygen /absolute/ssh-keygen --ssh-keygen-sha256 sha256:<digest>` reports
`contentReady=true` only
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

## Threshold result and freshness authority

Before freshness, the external threshold verifier emits canonical
`idc-skills-external-verification/v1` JSON. It binds the initial and final root,
monotonic release sequence, release-statement digest, tag/commit/tree, archive,
manifest, freshness index, registry, install inventory, and content-signing
authority. The protected external root checkpoint serializes concurrent runs
and rejects root rollback/equivocation plus release-sequence rollback or
same-sequence statement equivocation. See [`../trust/README.md`](../trust/README.md).

The launcher validates canonical `idc-skills-release-index/v1` bytes under the
domain-separated OpenSSH namespace `idc-skills-release-index-v1`. Every release
entry binds:

```json
{
  "gitCommit": "40-lowercase-hex",
  "launcherSHA256": "sha256:...",
  "manifestSHA256": "sha256:...",
  "manifestSequence": 2,
  "release": "<next-full-assurance-version>",
  "verifierSHA256": "sha256:..."
}
```

The threshold release statement also binds a canonical
`idc-skills-install-inventory/v1` artifact derived exactly from the signed
manifest:

```json
{
  "authority": "pre-install-expectation-only",
  "manifest": {
    "manifestSequence": 2,
    "sha256": "sha256:...",
    "size": 1234
  },
  "release": "<next-full-assurance-version>",
  "schema": "idc-skills-install-inventory/v1",
  "skills": {
    "count": 50,
    "names": ["agent-guardrails", "..."]
  },
  "targets": [
    {"label": "agents", "releaseParity": "required"},
    {"label": "claude", "releaseParity": "required"},
    {"label": "pi", "releaseParity": "required"},
    {"label": "hermes", "releaseParity": "required"}
  ]
}
```

This is a pre-install expectation only. It says which manifest-derived skill
inventory every release-parity seat must contain; it does not claim that a host
was inspected or that installation succeeded. The later
`idc-fleet-parity-report/v1` is an observation-only result and binds its exact
candidate, manifest, index, and install-inventory digests. It always carries
`readyToRun=false`: the report bytes do not authenticate their own producer.
The parity process requires its freshness handoff to equal the bound index
digest, rejects aliased, overlapping, candidate-contained, symlinked, or
non-directory fleet entries, and checks four physically distinct roots. Even
so, a copied standalone JSON file is not an attestation. Preserve it inside the
protected freshness-launcher capture and bind that capture into the separately
signed platform/release evidence. The observation is deliberately downstream
of freshness and is never fed back into a manifest, index, inventory, or release
statement. Documentation schemas are
[`../trust/release-index.schema.json`](../trust/release-index.schema.json) and
[`../trust/install-inventory.schema.json`](../trust/install-inventory.schema.json);
the exact-field canonical parsers in `scripts/trust_root.py` remain the runtime
authority.

The launcher requires its own installed bytes, the captured content verifier,
and the captured signing-anchor files to equal their signed Git-tracked source
records before either verifier mode can execute. It also requires those anchor
bytes, manifest, index, release, and Git commit to equal the externally
threshold-authorized result, and requires the complete execution closure to
equal the newest entry's manifest and exact Git tree.
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
freshness both pass. At the final transition, the same exclusive checkpoint
lock is the consumer-generation fence: it remains held through the staged-tree
recheck and any authorized installer/consumer completion, so an older verified
run cannot resume after a newer run and overwrite the newer installed bytes.

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
  "minimumManifestSequence": 2,
  "requireGitCommit": true,
  "schema": "idc-skills-freshness-config/v3",
  "source": {
    "allowedHosts": ["raw.githubusercontent.com"],
    "indexURL": "https://raw.githubusercontent.com/OWNER/REPO/trust-index/releases.json",
    "maxRedirects": 0,
    "signatureURL": "https://raw.githubusercontent.com/OWNER/REPO/trust-index/releases.json.sig",
    "type": "https"
  },
  "thresholdReceipt": {
    "path": "/absolute/protected/evidence/<next-full-assurance-version>.external-verification.json",
    "sha256": "sha256:<exact-canonical-verification-result>",
    "size": 1234
  },
  "thresholdVerification": {
    "arguments": [
      "--repo", "/absolute/idc-skills",
      "--trusted-root", "/absolute/protected/trust/1.root.json",
      "--trusted-root-sha256", "sha256:<out-of-band-root-pin>",
      "--root-update", "/absolute/protected/trust/2.root.json",
      "--root-checkpoint", "/absolute/protected/state/root-checkpoint.json",
      "--release-statement", "/absolute/protected/releases/<next-full-assurance-version>.release.json",
      "--archive", "/absolute/protected/releases/idc-skills-<next-full-assurance-version>.tar.gz",
      "--manifest", "/absolute/idc-skills/integrity/manifest.json",
      "--freshness-index", "/absolute/protected/releases/releases.json",
      "--registry", "/absolute/idc-skills/skills/registry.json",
      "--install-inventory", "/absolute/protected/releases/install-inventory.json",
      "--git", "/absolute/protected/git",
      "--git-sha256", "sha256:<exact-git-bytes>",
      "--ssh-keygen", "/absolute/protected/ssh-keygen",
      "--ssh-keygen-sha256", "sha256:<exact-ssh-keygen-bytes>"
    ],
    "trustModule": {
      "path": "/absolute/protected/idc-threshold/trust_root.py",
      "sha256": "sha256:3ea9fcedcdca6ac643f44bd66aeb0556178537eb4d8c0f7e7ae63b58b99b9c47"
    },
    "verifier": {
      "path": "/absolute/protected/idc-threshold/verify_external_root.py",
      "sha256": "sha256:8bc90f03f059753e45d07d12df38358cfc6c9244809e95e8b0d10138608af728"
    }
  }
}
```

An external protected file pair may be used instead with `source.type=file`,
absolute `indexPath`, and absolute `signaturePath`. Repository-relative or
repository-resolving authority paths are refused.

`thresholdVerification` accepts only bounded flag/value pairs naming every
shown input exactly once, except `--root-update`, which may be omitted or
repeated for at most 32 sequential updates. Its Git and OpenSSH paths/digests
must equal `executables`; its repository must equal the candidate; and its
trusted root and root checkpoint must remain outside the candidate. The
verifier and trust-module records have exactly `path` and `sha256`, must be
adjacent external single-link files named `verify_external_root.py` and
`trust_root.py`, and must match the two launcher-pinned implementation digests
shown above. The verifier must also be executable.

For each reproduction, the launcher captures and re-hashes those exact external
bytes, stages them together in a fresh private temporary directory as mode 0700
and 0600, and runs the staged verifier under the configured Python with `-I -B`,
a minimal environment, a bounded output, and a timeout. It does this once before
content verification and again immediately before the checkpoint/consumer
transition. Both stdout byte streams must equal the externally pinned
`thresholdReceipt`, and the receipt/config bytes must remain unchanged between
runs. Parsing equivalent JSON is not sufficient.

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
Consumers launched through this authority also receive
`IDC_GUARD_STRICT=1`, making unsupported dangerous-Git grammar and guard
transport/runtime failures fail closed for that child. Persistent installed
hooks must point instead at the verified installation's
`agent-guardrails/scripts/block-dangerous-git-strict.sh`. The installer
byte/mode-verifies this durable wrapper; on every hook invocation it exports
`IDC_GUARD_STRICT=1` and executes the adjacent classifier, failing closed if the
classifier cannot run. Installation does not silently register or rewrite
harness hook settings. Direct use of `block-dangerous-git.sh` remains the
explicit advisory path for compatibility and cannot infer external authority
from its own bytes.

The signed runtime contract is [`runtime-requirements.json`](../runtime-requirements.json):
Python 3.10 and Bash 3.2 are minimum floors, with Python 3.12 used by the
cross-platform CI matrix. Falling below a floor fails closed; a listed minimum
does not claim that every OS/runtime combination has been physically tested.
The exact macOS and Windows candidate must still satisfy the external
[`platform-evidence.schema.json`](../ops/mission/evidence/platform-evidence.schema.json)
gate. Windows verification authenticates the manifest's POSIX-mode intent and
exact bytes, while real NTFS ACL proof remains a separate required record under
[`windows-metadata-policy.json`](windows-metadata-policy.json).

Owner-controlled user files protect against repository rollback but not an
attacker acting as the same OS user. The verifier re-hashes the private staged
closure immediately before a child action, but repository code cannot make a
hostile same-UID process unable to race or replace user-owned trust state.
Stronger claims require admin-owned POSIX paths, Windows ACL enforcement,
process isolation, or CI/platform state outside candidate control.
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

## Scoped 2.0.4 promotion ceremony

The limited-trust 2.0.4 sequence is normative in
[`docs/2.0.4-release-scope.md`](../docs/2.0.4-release-scope.md): close and stage
the exact inventory, regenerate and owner-sign the manifest, commit and replay
one clean tree, require protected CI/review, publish two matching external
fingerprint/release-identity witnesses, then publish and re-observe immutable
GitHub objects. This ceremony proves content and publication comparisons only.
It does not invoke or borrow the success label of the external threshold public
release verifier.

## Deferred full G0-G6 assurance ceremony

1. Establish the production 2-of-3 root under separate custody and publish its
   exact digest through two independently administered channels. No private key
   or PIN enters Git, chat, logs, or candidate evidence.
2. Finalize every repository byte, next full-assurance version identity, sequence, test, document,
   state record, and generated report. Generate the v3 manifest, then perform
   the owner-held biometric content signature as the last candidate-byte
   mutation.
3. Commit that exact manifest and signature. Create the annotated tag for that new version
   locally at that commit, but do not publish it. Replay the commit and tag from
   an ordinary clean clone. The tag is now an input to artifact construction,
   not yet a public release claim.
4. From that clean exact commit/tree and unpublished annotated tag, build the
   deterministic archive, the manifest-derived pre-install inventory, and the
   canonical release index. For a non-genesis index, require the latest signed
   previous index plus the externally digest-pinned checkpoint that accepted its
   complete history. Sign the new index under
   `idc-skills-release-index-v1`.
5. Build the threshold release payload only after the archive, inventory, signed
   index, manifest, registry, commit, tree, and local annotated tag agree. Obtain
   the required detached release-role signatures under
   `idc-skills-release-statement-v1`; no builder opens a private key.
6. Run the external threshold verifier, capture its canonical result outside
   Git, hash-bind that result and the exact verifier/module/arguments in
   freshness configuration v3, and require both launcher reproductions to be
   byte-identical before it produces `readyToRun=true`.
7. Install only through that freshness authority. Prove four physically
   distinct fleet roots match and preserve the observation-only post-install
   fleet-parity JSON inside an externally protected capture, including the exact
   candidate, manifest, release-index, and pre-install-inventory digests. Sign
   or witness the enclosing evidence record; the parity JSON cannot authenticate
   itself. Then obtain the platform, protected-CI, hostile/Kimi, and two distinct
   signed non-OpenAI exact-head review receipts. Any head or tag-target move
   voids the affected evidence.
8. Merge only through a protected path that preserves the accepted commit. If
   merge strategy creates a different commit, or any accepted byte changes,
   return to manifest generation and rebuild every downstream artifact and
   receipt. Otherwise publish the already accepted annotated new-version tag and
   the exact threshold-bound assets on GitHub, plus the root digest on the
   separately administered company endpoint and independent
   DNSSEC/transparency witness.
9. Within the bounded observation window, verify the signed release statement,
   immutable published tag, assets, structured site receipts, both trust
   channels, and a fresh public consumer install before describing a later
   immutable release as full-G0-G6 or production-assurance accepted. A
   published release tag is permanent: never move, replace, delete, or reuse
   it; corrections receive a new release identity.

Any repository mutation after manifest signing returns to step 2. Any final
commit or local tag-target rewrite after artifact construction returns to step
2. Passing a gate never authorizes the next mutation by itself.

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
