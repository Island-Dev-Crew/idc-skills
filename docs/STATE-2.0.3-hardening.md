# STATE — 2.0.3 hardening (durable, survives context compaction)

State, not instructions. This is the pre-sign reconciliation snapshot for the
Kimi → Codex → Claude loop.

## Where things stand

- **2.0.3 is a candidate, not shipped.** `skills/registry.json` records release
  `2.0.3` with `manifestSequence: 1`; no public promotion, tag, merge, or
  `readyToRun` claim is made here.
- **The anti-rollback implementation is exact at `a58f59e`.** The supplied
  review record is Claude Opus + OpenAI Codex **APPROVE**. Its matrix is 100
  unit tests plus 20 subtests, and the canonical validator is 50/50.
- **The signed manifest is historical.** The checked-in manifest/signature are
  2.0.2/v2 artifacts. Final 2.0.3/v3 manifest generation and owner biometric
  signing remain pending; the historical signature does not authorize 2.0.3.
- **Guard/scanner R5 is not accepted.** Exact R5 `c721304` returned
  **CHANGES_REQUIRED**. The R6 repair is pending; final values remain
  `FINAL_GUARD_COUNT`, `FINAL_SCANNER_COUNT`, and `FINAL_R6_SHA` placeholders.

## Control boundaries

The external freshness launcher is the only authority that can emit
`readyToRun=true`; the in-tree integrity verifier can establish content only.
Guard and scanner controls remain **advisory** classifiers/rungs. The signed
manifest, external signed index, protected checkpoint, and owner/operator
ceremony remain separate release gates.

## Pre-sign snapshot

At this snapshot, the candidate content is intended to be finalized at
`FINAL_R6_SHA`, with registry release `2.0.3` and `manifestSequence: 1`. The
anti-rollback implementation is approved at `a58f59e`; final R6 evidence is
`FINAL_GUARD_COUNT/FINAL_GUARD_COUNT` and
`FINAL_SCANNER_COUNT/FINAL_SCANNER_COUNT`. The 2.0.2/v2 manifest/signature is
historical evidence only. This paragraph makes no 2.0.3 signature,
`contentReady`, `readyToRun`, release, merge, promotion, tag, or reinstall
claim, and remains a historical snapshot after transport.

## Required order

1. Finish R6 and record its exact counts and SHA.
2. Finalize all docs, mission state/journal, validation records, rendered
   reports, changelog, registry, and control-file content.
3. Regenerate the finalized 2.0.3/v3 manifest and obtain owner biometric
   signing. No controlled-byte mutation follows signing.
4. Reaccept the exact signed commit from a clean clone and obtain the required
   exact-head review/CI evidence.
5. Construct and sign the external release index, provision its checkpoint, and
   obtain external `readyToRun=true`; only then transport, merge, promote, tag,
   and reinstall.

Do not push, merge, promote, tag, or sign while R6 or the final biometric
ceremony is pending. Do not treat local tags or the historical 2.0.2 signature
as anti-rollback authority.
