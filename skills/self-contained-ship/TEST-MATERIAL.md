# Shipped scanner test material

`scripts/test-scan-egress.sh` is intentionally shipped test material, not a compact runtime helper. At the 2.0.4 candidate it is 2,146 lines and exercises 607 deterministic cases across the scanner's accepted and rejected grammar. Its size is disclosed because a large executable fixture surface belongs in provenance and review scope; it is not evidence that every possible egress grammar is covered.

Maintenance contract:

- Every new parser claim begins as a red fixture with one discriminating expected result.
- Case counters are derived by the script and the complete suite runs under real macOS Bash 3.2 plus ShellCheck before release.
- Fixture names and diagnostic bytes are untrusted display input; the scanner must keep them encoded and separate from its trusted count channel.
- The suite is part of the signed skill tree, so any fixture edit changes the release manifest and voids prior exact-head review.
- The static scanner remains bounded defense in depth. Human intent review and the sealed runtime load are separate gates; 607/607 is not a sandbox claim.
