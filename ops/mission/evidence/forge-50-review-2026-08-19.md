# Forge 50 independent review evidence — 2026-08-19

## Scope

- Base reviewed: `2528a28e62940e5bdb29074da4f9da6aa4184df1`
- Local 2.0.2 foundation: `574346ec5b7c50fe7e023d04426ad09072f11209`
- De-slop commit: `31b7598`
- Three independent Luna cohorts covered all 50 islands.
- Preservation checks compared frontmatter, fenced code, inline code, commands, URLs, trigger meaning, and local links; no semantic loss was found in the de-slop change itself.

## Security defects found and repaired

- Git authority classifier quote/backslash/global-option bypasses; matrix expanded 28→37.
- Incomplete database read-only guidance and broad “mechanically impossible” overclaim.
- Unbounded unattended authority/spend/delegation language.
- UI smoke arbitrary origin/driver and missing failed-readiness verdict.
- Video capture stale-output and swallowed-download failures.
- Credential wizard unsafe URL and file-mode behavior.
- Missing secret/PII boundaries in diagnosis and evidence packets.
- Untrusted issue/PR/inbox content not separated from authority.
- Mutation authority gaps in lane/register/merge/prototype workflows.
- Unpinned dependency installation and mutable protocol-source guidance.
- Integrity failures: attacker-controlled CLI fingerprint, optional installed-tree hook, UTF-16/UTF-32 scan bypass, control-file path escape, a manifest-swap time-of-check/time-of-use race, and a live-tree change after first hash.

## Current measured gates before final re-signing

- Unit tests: 74/74 passing after secure-default install/export, hook identity/fail-closed, hermetic Unicode-output, and canonical-LF renderer repairs.
- Git authority fixtures: 37/37 passing.
- Semantic records: 50 records / 150 cases / registry=report exact.
- Canonical validator: 50/50 passing with 13 named compatibility warnings.
- Shellcheck: all eight release shell surfaces pass the exact Ubuntu CI command.
- First PR #3 run: macOS passed; Windows exposed platform-native report newlines; Ubuntu exposed four shellcheck findings. Both red classes were repaired.
- Second PR #3 run: Ubuntu and macOS passed; Windows exposed an ambiguous WSL/Git-Bash test boundary for three POSIX behavior probes. The harness now selects Git Bash explicitly and normalizes its process inputs without skipping the red assertions.
- Signed integrity: the Windows-test-repaired worktree verifies 5/5 and `readyToRun=true` against manifest SHA-256 `50062fb8b07bc0a44d00f1ebc43a36f5cbf522b32c01f7a65f89e12146aea800`.
- Cross-family review: the `1a38915` PASS is void-on-move after the accepted test-control repair; pending the next exact committed candidate.

This file is chronological evidence, not the final verdict. The final exact-head results are appended in the release report and mission state after signature and independent review.
