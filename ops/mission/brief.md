# Forge Cross-Harness Gauntlet Brief

## Task

Recursively improve the IDC Skills Forge from its release 2.0.0 baseline so the fifty-skill source remains canonical while installation, validation, and truthful portability work from Windows Codex and across meaningful agent harnesses.

## Supplied evidence

- Public source: `https://github.com/Navigata1/idc-skills-forge`
- Pinned baseline: `c8e94a385dbf6bb65bc605524008967a7f916679`
- Prior Claude audit: 50/50 skills passed its validator, but thirteen user-invoked skills were reported as rejected by claude.ai because `disable-model-invocation` and `argument-hint` are not in the supplied six-key top-level allowlist.
- Prior Codex port: 50 folders and 117 files were copied to the shared agent skill store, with Claude-only frontmatter removed in a temporary port. That proved a port was possible but did not make the repository itself portable.
- Requested targets: Cursor, Grokbot, Buzz, Kimi Code, Amp, Antigravity, VS Code, and any other meaningful harness, in addition to Codex, Claude Code, claude.ai, Pi, Hermes, and OpenClaw.

## Falsifiable bar

1. The repo owns a dependency-free validation command; missing folders, invalid frontmatter, sidecar drift, broken references, bad UTF-8, or profile incompatibility can force a nonzero exit.
2. All fifty canonical islands pass the canonical profile at the final reviewed tree.
3. claude.ai compatibility is produced as a separate deterministic export. Canonical Claude Code invocation keys are never silently deleted or rewritten in place.
4. A Windows-native installer runs without Bash or `rsync`, preserves canonical bytes for native installs, detects drift, is idempotent, and supports dry-run and verify-only modes.
5. Every named harness appears in a versioned support matrix. Positive support claims name an authoritative source and a reproducible probe; unknown or unavailable loaders remain explicitly unknown/unsupported.
6. Gauntlet builders work in isolated branches. A different builder performs blind artifact critique; same-family critique is never presented as a cross-family verdict.
7. Final gate evidence is re-derived from a fresh clone, not admitted from a worktree.

## Round and authority limits

- Maximum builder/critic rounds: 2.
- The cap is advisory in this Codex harness; the orchestrator stops the loop manually.
- No remote push, pull request, release, profile installation, or mutation outside the repo without a later explicit user request.
- Existing skills change only when a validator/eval exposes a concrete failing case and the kept edit clears the same regression set.

## Release 2.0.2 addendum — 2026-08-19

The later user request supplies the previously withheld release authority: finish the signed 2.0.2 candidate, push it, open and merge PR #3 only after the required gates are green, promote the exact merged tree to IslandDevCrew, create tag `2.0.2`, and reinstall the verified Forge into Claude and Codex targets. It does not authorize force-push, credential disclosure, or unrelated mutations.

The additional falsifiable bar is:

1. A canonical manifest inventories exactly fifty skill directories and every regular byte beneath them, rejects links/non-regular files/path escapes, and binds the fixed security control plane.
2. The detached signature verifies with the stable Forge Ed25519 key and exact fingerprint `SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA`; repository code cannot substitute another trust anchor.
3. Five independent checks pass: signature/anchor, local bytes/inventory, reference/network policy, remote immutable pins, and control-plane bytes. Any failure is non-authorizing; no unsigned green exists.
4. Installation verifies before any destination write, compares source/stage/installed bytes, and rolls back the selected destination on failure. A pre-tool hook must be configured with the actual installed skill root.
5. Every claimed attack defense has a red fixture. Same-family review is calibration; a separate Claude-family verdict must bind the exact committed candidate and is void after any repair commit.
6. The exact candidate passes reacceptance from a fresh clone and remains clean. Remote merge, promotion, tag, and installed-copy claims are made only after live remote and local verification.

The trusted bootstrap remains deliberately external: consumers must confirm the public-key fingerprint through a trusted out-of-band channel before executing the repository's verifier. The gate detects specified tampering; it does not prove that signed instructions are benevolent or sandbox the surrounding agent runtime.
