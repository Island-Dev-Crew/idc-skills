# Changelog

## 2.0.4 — 2026-08-25 (stable limited-trust, content-authenticated release)

This release delivers the hardened Forge 50 under a deliberately bounded
public assurance profile. The owner-held Forge key authenticates one canonical
manifest at sequence 2, and the full signing fingerprint plus immutable release
identity must be published through two out-of-repository channels before public
promotion. The exact scope and deferred gates are normative in
[`docs/2.0.4-release-scope.md`](docs/2.0.4-release-scope.md).

- Repaired the Kimi evidence contract with 31 source-bundle-bound preserved
  records, revision-scoped citations, exact fixture/output digests, semantic
  capture bindings, and negative tests that reject missing paths, invalid
  ranges, mismatched bytes, symlink escape, unbounded output, and invented
  execution claims.
- Added external threshold-root metadata, rollback-safe root rotation, release
  statements, protected checkpoints, and tests for self-signed forged trees,
  equivocation, expiry, skipped rotation, partial threshold, and substitution.
- Closed the declared Git grammar at 395 cases and the static egress grammar at
  619 cases; moved waivers outside candidate content, pinned waiver runtimes,
  installed a strict guard entrypoint, and added sealed-browser WebRTC and
  overflow controls across mobile, tablet, desktop, and print.
- Bound hook identity, POSIX mode intent, trusted runtimes, secret transport,
  URL parsing, broken-pipe semantics, and the same-UID residual to executable
  tests and explicit platform-evidence requirements.
- Completed Forge-50 provenance and executable dependency records; vendored the
  Archipelago protocol at an exact upstream commit; hardened intake evidence,
  authority hierarchy, and exact-blob console assembly.
- Added signed external-record verifiers for exact-head cross-family/Kimi
  approvals, mandatory eleven-lane and 31-finding packet coverage, and GitHub +
  company-site + independent-witness publication consistency under a disjoint
  externally pinned observer key.
- Serialized the final freshness checkpoint transition through consumer
  completion so an older concurrent run cannot overwrite a newer installed
  generation; the publication observer is now disjoint from root,
  release-role, and threshold-bound content-signing keys.
- Made the G6 runbook commands executable rather than illustrative by naming
  every required external authority, root, Git, OpenSSH, and digest argument;
  parser checks remain distinct from human proof of organizational independence.
- Added the self-contained flagship release-control report. It passes the
  enhanced-report structural rubric, static zero-egress scan, and sealed Chrome
  matrix; its Tier B motion source is a complete finite 900-frame sequence.
- Closed the post-review release-artifact seam with production-format manifest,
  registry, index, and inventory parsers; deterministic private-key-blind index
  and exact-tree archive builders; annotated-tag, signature, expiry, commit,
  tree, key, and cross-artifact semantic joins; and launcher pins over the exact
  threshold implementation bytes.
- Made installed-fleet parity an explicitly observation-only result. It now
  requires the freshness handoff to equal the bound index digest, checks four
  physically distinct non-overlapping roots outside the candidate, rejects
  every extra file or symlink, and binds candidate plus manifest/index/inventory
  digests. An externally protected signed or witnessed capture remains required
  before that JSON becomes release evidence.
- Bounded strict Git-grammar input at 64 KiB and added availability regressions
  so oversized input fails closed without an operating-system argument-size
  crash; release-artifact fixtures now derive their validity window from test
  runtime instead of expiring on a fixed calendar date.

Public promotion still requires the owner-held final content signature, exact
candidate commit and tree, clean-clone reproduction, protected CI and review,
two matching external fingerprint/release-identity publications, an immutable
tag, exact release assets, and post-publication observation.

The production 2-of-3 root ceremony, completed eleven-lane Kimi acceptance,
independent Windows/NTFS seat, freshness-authorized four-root parity, disjoint
publication observer, and full `readyToRun=true` path are explicitly deferred.
They are not represented as passing 2.0.4 gates and will receive a new immutable
version identity when completed.

## 2.0.3 — 2026-08-19 (published 2026-08-22)

Signed-content reconciliation: the anti-rollback implementation is exact at
`a58f59e` with Claude Opus + OpenAI Codex **APPROVE**, 100 unit tests plus 20
subtests, and canonical validation 50/50. The independently approved guard
lineage closes at `d0fac44` and passes 300/300 native macOS Bash 3.2 fixtures.
The independently approved scanner diff `e98cfac6` is committed at `04a5bd4`
and passes 589/589 native macOS Bash 3.2 fixtures. The v3 manifest and detached
signature bind release 2.0.3 at sequence 1 and 5/5. Public main, annotated tag,
and installed fleet later converged on commit
`26b9285c1fe11a3ef875a34ff30faa0275eddf24`; that 2026-08-22 promotion
supersedes the candidate-state wording retained in earlier construction logs.

- Split content integrity from release authority. The in-tree verifier now emits
  `contentReady` under report schema v2; only the independently installed
  freshness launcher can emit `readyToRun=true`.
- Added signed manifest schema v3 with the first evidenced monotonic
  `manifestSequence`, a Git-tracked full-release byte/mode closure, strict
  canonical parsing, and explicit binding of the external launcher and its
  attack fixtures as release controls.
- Added the domain-separated, expiring signed release index and protected
  anti-replay checkpoint. The newest entry binds release, sequence, manifest,
  verifier, launcher, and exact Git commit; replay, equivocation, rewritten
  history, stale first-use state, in-tree authority paths, and missing required
  sources fail closed.
- Added private-snapshot execution with absolute digest-pinned Python, Git, and
  OpenSSH runtimes, candidate Git filter/hook/fsmonitor avoidance, sanitized
  consumer environment, fixed repository-root routing, and exact staged
  installer/hook/reacceptance paths. Offline verification remains explicitly
  freshness-unverified and exits distinctly without running a child.
- Bound the captured launcher, verifier, and signing-anchor bytes back to their
  reviewed signed repository sources before any content verifier can run,
  including offline mode; documented the external clean-process boundary needed
  to exclude pre-start loader injection.
- Hardened the advisory dangerous-Git classifier and static egress scanner with
  expanded macOS Bash 3.2 fixtures, while retaining their honest scope: the Git
  string classifier remains advisory beneath OS/repository controls, and static
  scanner completeness still requires the separate sealed-load runtime rung.
- Repository-owned CI now exercises the content and freshness fixture matrices,
  scanner/guard suites, and release shell surfaces without claiming that
  candidate-owned workflow code is an external whole-tree trust root.

Security boundary: the external launcher, its canonical configuration,
checkpoint, pinned runtime binaries, signing key, and operating system remain
trusted components. User-owned external state does not protect against that same
OS user; admin-owned paths or platform policy are required for the stronger
claim.

## 2.0.2 — 2026-08-19

- De-slopped all 50 canonical skill bodies while preserving the de-slop commit's frontmatter, fenced code, inline code, commands, URLs, and operational meaning; independent cohort review found no semantic loss.
- Added a dependency-free signed integrity gate over every skill byte, release-control byte, external-reference occurrence, network-command occurrence, remote instruction pin, and exact reviewed fetch/execute exception.
- Added the stable 1Password-held Ed25519 signing anchor, detached OpenSSH signature flow, out-of-band bootstrap instructions, mandatory installed-byte PreToolUse adapter, and fail-closed installer integration.
- Made signed verification default-on for native installs and both export modes with no release-CLI opt-out; exports build only from a staged snapshot bound to the authenticated per-file map. Every unexpected PreToolUse adapter exception collapses to blocking exit 2, explicit-skill/payload disagreement is denied, output is ASCII-safe, and red tests cover each path.
- Added adversarial fixtures for local tamper, new URLs, remote-content drift, forged manifests, attacker-key substitution, manifest-swap and mid-verification file races, wide-encoded payloads, symlink escape, control-file path escape, denied fetch/execute forms, and tampered installation trees. Signature verification, parsing, installer, and hook now share one authenticated manifest snapshot; the complete local tree is recaptured immediately before authorization.
- Closed final cross-family hardening notes: release runtime instructions require HTTPS for both source and final URL with no fixture transport escape, and trusted-file capture compares pre-open path identity to the opened descriptor on platforms without `O_NOFOLLOW`.
- Expanded the git authority classifier from 28 to 37 passing attack/allow fixtures and hardened video capture, credential wizard, UI smoke, scheduling, mutation, redaction, dependency, and spend boundaries across the affected islands.
- Re-pinned the retained David Ondrej and Matt Pocock source archives to exact historical Git blob trees, preserved upstream MIT notices, and recorded the still-unresolved fusion-time ICM commit without substituting a current head.
- Closed the 40/50 semantic-evidence gap: 50 machine-readable records, 150 cases, a deterministic report renderer, and a registry↔record↔full-render byte gate.
- Closed the first PR #3 cross-platform reds: the report renderer now writes canonical LF bytes instead of platform-native newlines, with a Windows-sensitive regression, and every release shell surface passes the same strict shellcheck job used by CI.
- Kept the POSIX shell security probes live on Windows without conflating WSL and Git Bash: the test harness resolves Git Bash explicitly, converts drive paths, uses the platform PATH separator, and emits LF-only executable fixtures before asserting the production scripts' exact red exits.

Security scope remains bounded: 5/5 proves the signed bytes and remote observations checked at preflight. It does not certify signed intent, protect a compromised signing session, sandbox the agent, prevent same-user post-check mutation, or attest an entire runtime flow.

## 2.0.1 — 2026-08-19

- Closed the independent review's initial validator, installer, routing, provenance, and handoff findings.
