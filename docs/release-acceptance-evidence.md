# 2.0.4 release acceptance evidence

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
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> --json
```

`reviews.json` uses schema `idc-release-reviews/v1`. It contains one candidate
object (`base`, `commit`, `tree`), one external evidence-packet receipt, and
exactly two approvals: `cross-family` and `kimi-k3`. Each approval repeats the
exact candidate, identifies reviewer name, model, and family, sets `voidOnMove`
to true, provides complete finding counts, and binds a strict
`idc-independent-review-receipt/v1` payload to the same evidence-packet digest.
The two reviewers, model families, and receipts must be distinct; the authoring
OpenAI family is rejected as the cross-family seat. Any unresolved blocker,
critical, or high finding refuses the gate.

## Public release record

Run only after an annotated 2.0.4 tag exists locally and resolves to the accepted
candidate:

```text
python3 -I -B scripts/verify_public_release.py /external/publication.json \
  --repo-root /candidate/idc-skills \
  --git /trusted/bin/git --git-sha256 sha256:<git-bytes> \
  --canonical-repository Island-Dev-Crew/idc-skills \
  --site-host <company-site-host> --json
```

`publication.json` uses schema `idc-public-release-evidence/v1`. It binds the
annotated tag, commit, tree, root version/digest, threshold release statement,
threshold-verification receipt, canonical GitHub release and exact asset
inventory, company landing page and root-digest captures, administrative-custody
record, and a DNSSEC or transparency witness containing the same root digest.
Every captured receipt remains outside the candidate. Receipt payloads are
semantic, not arbitrary hash targets: threshold output repeats the candidate,
root, and release-statement digest; GitHub output repeats the candidate, assets,
and tag object; the landing capture must contain the exact release URL, tag,
commit, tree, and root digest; the root endpoint must contain only that digest;
and the independent witness repeats its kind, locator, digest, and verification
result.

## Required order

1. Close G1 root ceremony, G4 real seats, and G5 installed parity at one head.
2. Freeze and clean-clone reaccept that candidate.
3. Send the exact SHA/tree and evidence packet to cross-family and Kimi seats.
4. Verify their external records; a head move voids both.
5. Obtain protected CI and two-party review.
6. Authorize version bump, threshold metadata, tag, and release assets.
7. Publish GitHub, company-site, and second-channel facts.
8. Verify publication and a fresh consumer installation before promotion.

Passing either record establishes only its named gate. It does not authorize the
next mutation.
