# Changelog

## 2.0.3 — 2026-08-19 (candidate until external freshness, merge, promotion, and tag)

Pre-sign reconciliation: the anti-rollback implementation is exact at
`a58f59e` with Claude Opus + OpenAI Codex **APPROVE**, 100 unit tests plus 20
subtests, and canonical validation 50/50. The independently approved guard
lineage closes at `d0fac44` and passes 300/300 native macOS Bash 3.2 fixtures.
The independently approved scanner diff `e98cfac6` is committed at `04a5bd4`
and passes 589/589 native macOS Bash 3.2 fixtures. The checked-in 2.0.2/v2
manifest/signature remain historical until the final 2.0.3/v3 biometric
ceremony; this entry is still a candidate record, not a shipped-release claim.

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
