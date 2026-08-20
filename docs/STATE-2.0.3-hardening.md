# STATE — 2.0.3 hardening (durable, survives context compaction)

State, not instructions. This is the final pre-sign reconciliation snapshot for
the Kimi → Codex → Claude loop.

## Where things stand

- **2.0.3 is a candidate, not shipped.** `skills/registry.json` records release
  `2.0.3` with `manifestSequence: 1`; no public promotion, tag, merge, or
  `readyToRun` claim is made here.
- **The anti-rollback implementation is exact at `a58f59e`.** Claude Opus and
  OpenAI Codex independently returned **APPROVE**. Its matrix is 100 unit tests
  plus 20 subtests, and the canonical validator is 50/50.
- **The guard is accepted.** Its approved component lineage closes at
  `d0fac44`; an integration replay on native macOS Bash 3.2 passes 300/300.
- **The scanner is accepted.** Exact reviewed diff `e98cfac6`, committed as
  `04a5bd4`, passes 589/589 on native macOS Bash 3.2. Its three-file review
  scope and opening/closing hashes matched.
- **The signed manifest is historical.** The checked-in manifest/signature are
  2.0.2/v2 artifacts. Final 2.0.3/v3 manifest generation and owner biometric
  signing remain pending; the historical signature does not authorize 2.0.3.

## Control boundaries

The external freshness launcher is the only authority that can emit
`readyToRun=true`; the in-tree integrity verifier can establish content only.
Guard and scanner controls remain **advisory** classifiers/rungs. The signed
manifest, external signed index, protected checkpoint, and owner/operator
ceremony remain separate release gates.

## Pre-sign snapshot

Registry release `2.0.3` and `manifestSequence: 1` are final candidate values.
Anti-rollback is approved at `a58f59e`; guard is 300/300 at approved component
`d0fac44`; scanner is 589/589 at approved diff `e98cfac6` committed as
`04a5bd4`. The final candidate commit is established by the signed v3 manifest
and the external release receipt rather than a self-referential SHA embedded in
its own source tree. The 2.0.2/v2 manifest/signature is historical evidence
only. This paragraph makes no 2.0.3 signature, `contentReady`, `readyToRun`,
release, merge, promotion, tag, or reinstall claim.

## Required order

1. Finalize all docs, mission state/journal, validation records, rendered
   reports, changelog, registry, and control-file content.
2. Run the complete integrated gate suite and commit the controlled bytes.
3. Regenerate the finalized 2.0.3/v3 manifest and obtain owner biometric
   signing. No controlled-byte mutation follows signing.
4. Reaccept the exact signed commit from a clean clone and obtain exact-head
   review plus required staging CI.
5. Merge the byte-identical staging candidate, construct and sign the external
   release index, and obtain staging `readyToRun=true`.
6. Promote the exact merge/index pair, prove the public source returns the same
   readiness tuple, annotate and SSH-sign tag `2.0.3`, then reinstall and verify
   installed bytes.

The owner authorized this release pipeline. The gates still control order: a
failed signature, replay, review, CI, freshness, public-source, or reinstall
check stops promotion without force-push or evidence rewriting.
