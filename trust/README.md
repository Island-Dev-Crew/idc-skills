# IDC external threshold trust

## 2.0.4 publication boundary

The stable 2.0.4 public content-authenticated release ships this threshold
machinery as tested source but does not represent it as production-activated.
Its public trust anchor is the existing Forge content-signing fingerprint,
published with the exact release identity through two channels outside GitHub.
It does not emit or claim the production threshold result
`externalTrustVerified=true`, and it cannot authorize `readyToRun=true`.

Production 2-of-3 custody, threshold release signatures, the disjoint
publication observer, completed Kimi acceptance, Windows/NTFS evidence, and
freshness-authorized fleet parity remain open for a later immutable release.
See the [2.0.4 release scope](../docs/2.0.4-release-scope.md).

Every command example below belongs to that deferred full-assurance profile and
uses `<next-full-assurance-version>` instead of reusing the immutable 2.0.4 tag.

This directory defines public formats and tooling. It deliberately contains no
production root metadata and no private key. A repository cannot appoint the
first key trusted to authenticate itself.

## Trust flow

1. Obtain `1.root.json` outside the candidate repository. Verify its SHA-256
   through two channels under separate administrative control.
2. Install the reviewed verifier and its Python runtime, Git, and OpenSSH paths
   through an external protected wrapper. Pin the exact Git and `ssh-keygen`
   executable digests. The verifier rejects an initial root inside the candidate.
3. Apply only sequential `N+1` root files. Every rotation must meet the previous
   root threshold and the new root's own threshold. The final root must be live.
   Persist the verifier's external `idc-skills-root-checkpoint/v3`; it prevents a
   later mirror from withholding an already accepted rotation or substituting a
   different root at any checkpointed intermediate version.
4. Verify the threshold-signed release statement. It binds the tag, commit,
   tree, archive, integrity manifest, freshness index, registry, four-root
   pre-install expectation inventory, and the exact content-signing public key
   and allowed-signers bytes. The inventory describes what all four release
   seats must contain; it is not evidence that installation occurred.
5. Treat `externalTrustVerified=true` only as eligibility to begin content
   verification. It is never install authority. The content/freshness checks
   and exact-object installer must still pass before `readyToRun`.

This follows the [TUF root-update invariants](https://theupdateframework.github.io/specification/latest/#update-the-root-role)
while retaining OpenSSH sshsig as
the repository's deployed signature primitive. It is a narrow implementation,
not a claim of full TUF client conformance.

## Production root ceremony

Recommended policy is 2-of-3 offline root keys and 2-of-3 release keys, with
each private key in a distinct custody domain. Root keys stay offline. Release
keys may be hardware-backed, but no single workstation or account should hold a
threshold. The ceremony record must contain only public keys, canonical
payload/output digests, signer key IDs, timestamps, witnesses, and dispositions.
Never place a private key, recovery phrase, PIN, or decrypted carrier in Git,
chat, shell history, CI logs, or mission evidence.

The public builder never opens a private key:

```text
python3 -I -B scripts/build_trust_metadata.py root-payload \
  --version 1 --expires 2027-08-22T00:00:00Z \
  --root-key root-a.pub --root-key root-b.pub --root-key root-c.pub \
  --root-threshold 2 \
  --release-key release-a.pub --release-key release-b.pub --release-key release-c.pub \
  --release-threshold 2 --output 1.root.payload.json
```

Each custodian signs the identical payload on an offline seat:

```text
ssh-keygen -Y sign -f /offline/root-a -n idc-skills-root-v1 1.root.payload.json
```

Use `build_trust_metadata.py keyid` to derive each public key ID and `envelope`
to assemble the detached signatures. A first root must self-meet its threshold.
For rotation, the new payload is signed by both the old threshold and the new
threshold. Preserve every numbered root forever; never skip a version.

The two release-artifact formats have strict documentation schemas:

- [`release-index.schema.json`](release-index.schema.json) documents
  `idc-skills-release-index/v1`.
- [`install-inventory.schema.json`](install-inventory.schema.json) documents
  `idc-skills-install-inventory/v1`.

`scripts/trust_root.py` is the stricter runtime authority: it also enforces
canonical byte encoding, sorted and unique release history, timestamp
arithmetic, the exact 50-name manifest-derived inventory, and semantic agreement
among every artifact. The inventory has authority value
`pre-install-expectation-only`. It contains no observation of a host and can
never substitute for the later `idc-fleet-parity-report/v1` result. That later
result is itself `observation-only` and carries `readyToRun=false`; preserve it
inside an externally protected freshness-launcher capture and sign or witness
the enclosing evidence record before treating it as release evidence.

After every controlled repository byte is final, generate and content-sign the
manifest, commit that exact manifest and signature, and create the annotated
release tag locally without publishing it. The archive and release-index
builders require that unpublished annotated tag to peel to the clean candidate
HEAD and tree. If any candidate byte or commit changes, discard the unpublished
tag and restart from manifest generation.

Build the manifest-derived pre-install expectation outside the candidate:

```text
python3 -I -B scripts/build_trust_metadata.py install-inventory \
  --manifest /candidate/integrity/manifest.json \
  --output /release-assets/install-inventory.json
```

Build the deterministic exact-tree archive from the signed candidate:

```text
python3 -I -B scripts/build_trust_metadata.py release-archive \
  --repo /candidate \
  --manifest /candidate/integrity/manifest.json \
  --manifest-signature /candidate/integrity/manifest.json.sig \
  --content-public-key /trusted/content/idc-skills-signing.pub \
  --content-allowed-signers /trusted/content/allowed_signers \
  --expected-content-fingerprint SHA256:<content-key-fingerprint> \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen \
  --ssh-keygen-sha256 sha256:<ssh-keygen-bytes> \
  --output /release-assets/idc-skills-<next-full-assurance-version>.tar.gz
```

For a non-genesis release, build the new index only from the latest signed
index and the externally digest-pinned checkpoint that accepted it. The builder
verifies the previous index signature, requires the checkpoint to identify the
same index sequence, digest, and complete release history, increments
`indexSequence`, and either appends the advancing manifest sequence or retains
an already-identical newest entry. It refuses rollback, history rewriting, and
same-sequence equivocation:

```text
python3 -I -B scripts/build_trust_metadata.py release-index \
  --repo /candidate \
  --manifest /candidate/integrity/manifest.json \
  --manifest-signature /candidate/integrity/manifest.json.sig \
  --content-public-key /trusted/content/idc-skills-signing.pub \
  --content-allowed-signers /trusted/content/allowed_signers \
  --expected-content-fingerprint SHA256:<content-key-fingerprint> \
  --previous-index /trusted/index/releases.json \
  --previous-index-signature /trusted/index/releases.json.sig \
  --previous-checkpoint /trusted/state/freshness-checkpoint.json \
  --previous-checkpoint-sha256 sha256:<checkpoint-bytes> \
  --generated-at <whole-second-UTC> --valid-until <whole-second-UTC> \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen \
  --ssh-keygen-sha256 sha256:<ssh-keygen-bytes> \
  --output /release-assets/releases.json
```

`--genesis` is mutually exclusive with all previous-index inputs and is
accepted only for manifest sequence 1. It is not an upgrade escape hatch.
Sign the new index's exact bytes under its domain-separated namespace:

```text
ssh-keygen -Y sign -f /protected/content-signing-key \
  -n idc-skills-release-index-v1 /release-assets/releases.json
```

Then build the unsigned threshold release payload. The builder verifies the
manifest and index signatures, the clean commit/tree and unpublished annotated
tag, the deterministic archive, the registry, and the manifest-derived
inventory before it hashes the five artifacts. The content key and
allowed-signers file are explicit inputs, so the threshold release role
authorizes exact content-signing bytes rather than accepting whatever key
travels with the candidate:

```text
python3 -I -B scripts/build_trust_metadata.py release-payload \
  --repo /candidate \
  --release <next-full-assurance-version> --release-sequence <monotonic-sequence> \
  --root-version <accepted-root-version> --expires <UTC-expiry> \
  --git-commit <exact-40-hex-commit> --git-tree <exact-40-hex-tree> \
  --archive /release-assets/idc-skills-<next-full-assurance-version>.tar.gz \
  --freshness-index /release-assets/releases.json \
  --freshness-index-signature /release-assets/releases.json.sig \
  --install-inventory /release-assets/install-inventory.json \
  --manifest /candidate/integrity/manifest.json \
  --manifest-signature /candidate/integrity/manifest.json.sig \
  --registry /candidate/skills/registry.json \
  --content-public-key /trusted/content/idc-skills-signing.pub \
  --content-allowed-signers /trusted/content/allowed_signers \
  --expected-content-fingerprint SHA256:<content-key-fingerprint> \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen \
  --ssh-keygen-sha256 sha256:<ssh-keygen-bytes> \
  --output /release-assets/<next-full-assurance-version>.release.payload.json
```

Each release custodian signs those identical canonical bytes with namespace
`idc-skills-release-statement-v1`; assemble the envelope only from detached
signatures. No builder command accepts a private-key path.

The consumer invocation is intentionally explicit. The initial root and state
paths are external; numbered updates and the release statement may arrive from
the distribution channel because earlier trust authenticates them:

```text
/trusted/python3 -I -B /trusted/idc/verify_external_root.py \
  --repo /candidate/idc-skills \
  --trusted-root /trusted/idc/1.root.json \
  --trusted-root-sha256 sha256:<external-pin> \
  --root-update /candidate/trust/2.root.json \
  --root-checkpoint /trusted/idc/state/root-checkpoint.json \
  --release-statement /release-assets/<next-full-assurance-version>.release.json \
  --archive /release-assets/idc-skills-<next-full-assurance-version>.tar.gz \
  --manifest /candidate/integrity/manifest.json \
  --freshness-index /release-assets/releases.json \
  --registry /candidate/skills/registry.json \
  --install-inventory /release-assets/install-inventory.json \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen --ssh-keygen-sha256 sha256:<ssh-keygen-bytes>
```

The canonical v3 root checkpoint has exactly these fields:

```json
{
  "releaseSequence": 3,
  "rootSHA256": "sha256:<accepted-root-envelope>",
  "schema": "idc-skills-root-checkpoint/v3",
  "signedStatementSHA256": "sha256:<canonical-signed-release-payload>",
  "version": 2
}
```

`signedStatementSHA256` hashes the canonical signed release payload, not the
outer envelope, so reordering otherwise equivalent detached signatures does not
create false equivocation. If a later verification ends at a newer root, its
verified sequential update chain must still contain the checkpointed version
with exactly `rootSHA256`; reaching a later version through a substituted
intermediate root is refused. Release-sequence rollback and a different signed
payload at the same release sequence are also refused.

Capture the verifier's canonical `idc-skills-external-verification/v1` output
outside the checkout. The external freshness configuration must hash-bind those
bytes and their path. Before it runs any content verifier or consumer, the
launcher independently checks that this verification result repeats the exact
release/tag, commit, tree, root, release-statement digest, manifest, freshness
index, and threshold-authorized content key plus allowed-signers bytes. The
external verification result is therefore an input to the content/freshness
path, not a decorative report produced beside it. The later publication record
uses a separate time-stamped `idc-threshold-verification-receipt/v1` observation
for its 24-hour public-evidence window; do not substitute one schema for the
other. The external verification result carries `statementSHA256` for the
complete signed envelope and `signedStatementSHA256` for its canonical signed
payload; the latter is the identity persisted in the v3 root checkpoint.

## Independent publication channels

GitHub remains the canonical source and immutable release host. It is not an
independent first-contact channel for a root used to authenticate that same
GitHub repository. Before production acceptance, publish the exact initial-root
digest through two separately administered channels, for example:

- the company website at a stable `/.well-known/` path, deployed with credentials
  and infrastructure separate from the GitHub organization; and
- a DNSSEC-protected TXT record or a transparency-log statement controlled by a
  different credential/custodian.

The company landing page should link the exact immutable GitHub tag and release
assets, display the root version and fingerprint, provide the one-command
verification recipe, link the flagship evidence report, and explain rotation
and emergency recovery. Do not host a mutable second copy of the skill tree as a
competing source of truth. Once a release tag is published, it is immutable:
never move, replace, delete, or reuse it. A correction receives a new release
identity and a newly executed trust ceremony.

## Security boundaries

- Canonical JSON is signed with the `idc-skills-root-v1` or
  `idc-skills-release-statement-v1` namespace.
- Key IDs are lowercase SHA-256 of the canonical public-key object.
- Metadata is bounded, exact-field, strict UTF-8, non-symlink, and stable-snapshot
  read. Release artifacts are streaming-hashed with mutation detection.
- The monotonic root checkpoint is serialized across processes and atomically
  replaced in an existing protected external directory only after the full
  release statement verifies. Its strict `idc-skills-root-checkpoint/v3` record
  binds root version/digest, accepted release sequence, and
  `signedStatementSHA256`; validation binds the checkpointed root even when it
  is an intermediate member of a later verified rotation chain.
- Git and OpenSSH are absolute, external, owner-controlled, executable, and
  digest-pinned. The external wrapper remains responsible for starting the
  pinned Python interpreter in a clean loader environment.
- Expiry limits repository withholding/freeze exposure but cannot force a
  compromised mirror to serve a new root. Emergency threshold compromise still
  requires an out-of-band root replacement.

The executable adversarial contract is `tests/test_trust_root.py`. The JSON
Schemas are documentation aids; `scripts/trust_root.py` is the stricter runtime
validator.
