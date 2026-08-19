# Changelog

## 2.0.2 — 2026-08-19 (candidate until this exact tree is merged and tagged)

- De-slopped all 50 canonical skill bodies while preserving the de-slop commit's frontmatter, fenced code, inline code, commands, URLs, and operational meaning; independent cohort review found no semantic loss.
- Added a dependency-free signed integrity gate over every skill byte, release-control byte, external-reference occurrence, network-command occurrence, remote instruction pin, and exact reviewed fetch/execute exception.
- Added the stable 1Password-held Ed25519 signing anchor, detached OpenSSH signature flow, out-of-band bootstrap instructions, mandatory installed-byte PreToolUse adapter, and fail-closed installer integration.
- Made signed verification default-on for native installs and both export modes with no release-CLI opt-out; exports build only from a staged snapshot bound to the authenticated per-file map. Every unexpected PreToolUse adapter exception collapses to blocking exit 2, explicit-skill/payload disagreement is denied, output is ASCII-safe, and red tests cover each path.
- Added adversarial fixtures for local tamper, new URLs, remote-content drift, forged manifests, attacker-key substitution, manifest-swap and mid-verification file races, wide-encoded payloads, symlink escape, control-file path escape, denied fetch/execute forms, and tampered installation trees. Signature verification, parsing, installer, and hook now share one authenticated manifest snapshot; the complete local tree is recaptured immediately before authorization.
- Closed final cross-family hardening notes: release runtime instructions require HTTPS for both source and final URL with no fixture transport escape, and trusted-file capture compares pre-open path identity to the opened descriptor on platforms without `O_NOFOLLOW`.
- Expanded the git authority classifier from 28 to 37 passing attack/allow fixtures and hardened video capture, credential wizard, UI smoke, scheduling, mutation, redaction, dependency, and spend boundaries across the affected islands.
- Re-pinned the retained David Ondrej and Matt Pocock source archives to exact historical Git blob trees, preserved upstream MIT notices, and recorded the still-unresolved fusion-time ICM commit without substituting a current head.
- Closed the 40/50 semantic-evidence gap: 50 machine-readable records, 150 cases, a deterministic report renderer, and a registry↔record↔full-render byte gate.

Security scope remains bounded: 5/5 proves the signed bytes and remote observations checked at preflight. It does not certify signed intent, protect a compromised signing session, sandbox the agent, prevent same-user post-check mutation, or attest an entire runtime flow.

## 2.0.1 — 2026-08-19

- Closed the independent review's initial validator, installer, routing, provenance, and handoff findings.
