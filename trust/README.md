# IDC external threshold trust

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
   Persist the verifier's external root checkpoint; it prevents a later mirror
   from withholding an already accepted rotation or equivocating at its version.
4. Verify the threshold-signed release statement. It binds the tag, commit,
   tree, archive, integrity manifest, freshness index, registry, and four-root
   installation inventory.
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
  --release-statement /release-assets/2.0.4.release.json \
  --archive /release-assets/idc-skills-2.0.4.tar.gz \
  --manifest /candidate/integrity/manifest.json \
  --freshness-index /release-assets/releases.json \
  --registry /candidate/skills/registry.json \
  --install-inventory /release-assets/install-inventory.json \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen --ssh-keygen-sha256 sha256:<ssh-keygen-bytes>
```

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
competing source of truth.

## Security boundaries

- Canonical JSON is signed with the `idc-skills-root-v1` or
  `idc-skills-release-statement-v1` namespace.
- Key IDs are lowercase SHA-256 of the canonical public-key object.
- Metadata is bounded, exact-field, strict UTF-8, non-symlink, and stable-snapshot
  read. Release artifacts are streaming-hashed with mutation detection.
- The monotonic root checkpoint is atomically replaced in an existing protected
  external directory only after the full release statement verifies.
- Git and OpenSSH are absolute, external, owner-controlled, executable, and
  digest-pinned. The external wrapper remains responsible for starting the
  pinned Python interpreter in a clean loader environment.
- Expiry limits repository withholding/freeze exposure but cannot force a
  compromised mirror to serve a new root. Emergency threshold compromise still
  requires an out-of-band root replacement.

The executable adversarial contract is `tests/test_trust_root.py`. The JSON
Schemas are documentation aids; `scripts/trust_root.py` is the stricter runtime
validator.
