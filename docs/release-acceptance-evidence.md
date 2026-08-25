# 2.0.4 release acceptance evidence

> **Profile boundary:** this document defines the stronger production-threshold
> acceptance ceremony. Stable 2.0.4 is being published under the narrower
> [public content-authenticated profile](2.0.4-release-scope.md). None of the
> production 2-of-3, complete Kimi, Windows/NTFS, freshness-authorized fleet,
> publication-observer, or `readyToRun=true` conditions below is represented as
> a 2.0.4 PASS. Completion of this document's full ceremony receives a later
> immutable version identity.

Release evidence remains outside the candidate repository. Committing a receipt
that purports to approve its own eventual head creates a circular or stale
claim. Every external receipt is a bounded regular file, captured byte-for-byte,
and named by absolute path, size, and SHA-256 in the corresponding record.

The repository verifiers prove that captured records are strict, internally
consistent, bound to the clean local candidate, and free of unresolved
blocker/critical/high findings. They do not create independent authorship,
administrative separation, threshold custody, or network publication facts.

## Exact-head review record

Run from a clean checkout of the reviewed candidate with an absolute,
digest-pinned Git executable:

```text
python3 -I -B scripts/verify_release_reviews.py /external/reviews.json \
  --repo-root /candidate/idc-skills \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --review-authorities /trusted/reviews/authorities.json \
  --review-authorities-sha256 sha256:<authority-record-bytes> \
  --ssh-keygen /trusted/bin/ssh-keygen \
  --ssh-keygen-sha256 sha256:<ssh-keygen-bytes> --json
```

`reviews.json` uses strict outer schema `idc-release-reviews/v2`. It contains one
candidate object (`base`, `commit`, `tree`), one external evidence-packet
receipt, and exactly two approvals: `cross-family` and `kimi-k3`. Each approval
repeats the exact candidate, identifies reviewer name, model, and family, sets
`voidOnMove` to true, provides complete finding counts, and carries a `coverage`
object. Coverage must contain, in order, all 11 lanes `K3-204-0` through
`K3-204-10`; every lane must be `complete` and name at least one indexed
evidence artifact. It must also contain, in order, all 31 reconciliations
`K3-203-001` through `K3-203-031`; each must provide a non-empty rationale, at
least one indexed evidence artifact, and exactly one accepted disposition:
`fixed`, `false-positive`, `not-reproduced`, or `accepted-residual`. Any missing
lane, finding, disposition/evidence, or unresolved blocker, critical, or high
finding refuses the gate.

Each approval binds a strict `idc-independent-review-receipt/v2` payload to the
same evidence-packet digest. The payload repeats the exact candidate, review
identity, verdict, finding counts, timestamps, move policy, and detailed
coverage; it also names the packet digest and a non-empty string `limitations`
array. Each outer receipt record binds the payload and its detached signature
by absolute path, size, and digest. Reviewer names, families, and receipt
identities must be distinct.

The evidence packet is a bounded ZIP with exactly one
`evidence-index.json`; every other regular entry is named, sized, and hashed in
that index. The index uses `idc-review-evidence-packet/v2`, repeats the exact
candidate, and declares exact ordered ID arrays for all 11 K3-204 lanes and all
31 K3-203 reconciliations. Every evidence path used by either review's detailed
coverage must resolve to an indexed packet artifact. Traversal, links,
duplicates, encryption, unsafe compression ratios, extra entries, and ignored
checkout payloads are refused.

Reviewer identity is not accepted from the receipt's self-description. The
externally pinned `idc-review-authorities/v1` file names one distinct non-OpenAI
family, principal, and hash-bound allowed-signers file for each review kind.
The two authority principals, families, and underlying signing-key blobs must
all be disjoint. Each `idc-independent-review-receipt/v2` is signed with
OpenSSH namespace `idc-independent-review-receipt-v2`; the verifier checks that
detached signature with the pinned principal before interpreting the receipt.
These mechanisms prove authority-key possession and exact-byte binding. The
human ceremony remains responsible for establishing that the keys and
reviewers actually belong to independent seats.

## Public release record

Run only after an annotated 2.0.4 tag exists locally and resolves to the accepted
candidate:

```text
python3 -I -B scripts/verify_public_release.py /external/publication.json \
  --repo-root /candidate/idc-skills \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --canonical-repository Island-Dev-Crew/idc-skills \
  --site-host <company-site-host> \
  --trusted-root /trusted/idc/1.root.json \
  --trusted-root-sha256 sha256:<out-of-band-root-pin> \
  --ssh-keygen /trusted/bin/ssh-keygen \
  --ssh-keygen-sha256 sha256:<ssh-keygen-bytes> \
  --observer-authority /trusted/publication/observer-authority.json \
  --observer-authority-sha256 sha256:<observer-authority-record-bytes> --json
```

`publication.json` uses strict schema `idc-public-release-evidence/v2`. It binds
the annotated tag, commit, tree, root version/digest, threshold release
statement, threshold-verification receipt, canonical GitHub release and exact
asset inventory, company landing page and root-digest captures,
administrative-custody record, and a DNSSEC or transparency witness containing
the same root digest.
Every captured receipt remains outside the candidate. Receipt payloads are
semantic, not arbitrary hash targets: threshold output repeats the candidate,
root, and release-statement digest; GitHub output repeats the candidate, assets,
and tag object. The landing observation is strict
`idc-site-landing-receipt/v2` JSON repeating the exact landing URL, release URL,
candidate, and root rather than merely containing convenient HTML substrings.
The root endpoint must contain only the expected digest, and the independent
witness repeats its kind, locator, digest, observation time, and successful
verification result. Every time-bearing public observation must be within the
verifier's 24-hour evidence window (with only bounded future clock skew).

The publication verifier independently checks the externally pinned trusted
root and OpenSSH threshold on the release statement. A self-asserted
`externalTrustVerified` boolean or a freshly rehashed unsigned statement cannot
create publication authority. It also rejects ignored candidate payloads and
normalizes malformed URLs into a clean refusal.

V2 additionally requires `observerAttestation`. The separately pinned
`idc-publication-observer-authority/v1` file must be an owner-controlled external
record with `independent=true`, a named non-IDC/non-OpenAI family and principal,
and a hash/size-bound single-key allowed-signers file. Its signing-key blob must
be disjoint from every root-metadata key, including both root and release-role
keys, and from the content-signing fingerprint bound into the threshold release
statement. The attestation payload is byte-canonical
`idc-publication-observation/v1`: it repeats the candidate and root, release
statement digest, channel locators, and the digests of all threshold, GitHub,
site, and second-channel receipts. Its detached signature is verified under
OpenSSH namespace `idc-publication-observation-v1` before the record can pass.
This proves possession of the externally pinned observer key and binds the
captured facts; it does not make a self-described observer independent or turn
an invalid underlying receipt into a publication fact.

## Scoped 2.0.4 publication evidence

The limited-trust sequence is defined in
[`docs/2.0.4-release-scope.md`](2.0.4-release-scope.md). Preserve the exact
owner-signed manifest, clean-clone result, protected CI/review result, GitHub
tag/assets observation, and both external fingerprint/release-identity
observations. Those receipts prove only their named content and publication
joins. Do not run the strict review, platform, threshold, freshness, or public
release verifiers with partial, self-issued, or fabricated records.

## Full G0-G6 assurance order — deferred

1. Establish the production 2-of-3 root under separate custody and publish its
   exact digest through two independently administered channels. Repository
   bytes cannot supply this initial authority.
2. Finalize every controlled `2.0.4` byte and local construction gate. Generate
   the content manifest, obtain the owner-held biometric signature as the last
   candidate-byte mutation, commit those exact bytes, and create an unpublished
   annotated tag at that commit.
3. Clean-clone reaccept the exact commit and tag. Build the deterministic
   archive, pre-install inventory, signed-history release index, and threshold
   release statement; obtain the index and release-role signatures.
4. Run the externally pinned threshold and freshness path, real macOS and
   Windows seats, and the freshness-routed four-root install/parity capture.
   Preserve parity only inside signed or independently witnessed external
   evidence; its standalone JSON is observation-only.
5. Send the exact commit/tree/tag and indexed evidence packet to two disjoint
   non-OpenAI seats, including Kimi; keep authority keys and allowed-signers
   records outside Git. Verify both detached signed receipts. A controlled-byte
   or tag-target move voids the affected downstream evidence.
6. Obtain protected CI and two-party review. Merge only if the protected path
   preserves the accepted commit.
7. Publish the already accepted annotated tag and exact threshold-bound assets
   on GitHub, link them from the company endpoint, and re-observe the unchanged
   root digest through both pre-established trust channels.
8. Obtain the
   independent observer's detached signature over their exact canonical receipt
   digests and channel locators.
9. Verify publication with the externally pinned observer authority and verify a
   fresh consumer installation before promotion.

Passing either record establishes only its named gate. It does not authorize the
next mutation.
