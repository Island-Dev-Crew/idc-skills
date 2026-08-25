# IDC Skills Forge 2.0.4 — Plan of Attack

**Decision:** stable 2.0.4 publication is authorized only under the bounded content-authenticated profile defined below. Its owner biometric signature, exact commit, review-preserving merge, immutable tag, two external witnesses, and post-publication comparison remain separate scoped promotion gates. Production threshold signing, complete Kimi acceptance, Windows/NTFS evidence, freshness-authorized fleet mutation, and the public-verifier observer remain a later full-assurance sequence. No missing external evidence becomes acceptance.

**Assessment baseline:** immutable public release `2.0.3`, signed tag object `bbdbafebde00f411dfa55584f4943c88e5a0393a`, commit `26b9285c1fe11a3ef875a34ff30faa0275eddf24`, tree `0ca09971998a058ca80c05fbfde4ca4d1178fdf8`.

## Owner scope decision — 2026-08-25

The owner authorized stable 2.0.4 publication under the narrower **public
content-authenticated** profile in
[`docs/2.0.4-release-scope.md`](../../docs/2.0.4-release-scope.md). That profile
requires the owner-held manifest signature, one exact clean-clone-reproduced
tree, protected CI/review, immutable GitHub objects, and two matching
out-of-repository publications of the Forge fingerprint and release identity.

This decision does not close or waive G1-G6. Production 2-of-3 custody, full
Kimi K3 acceptance, independent Windows/NTFS evidence, freshness-authorized
four-root parity, the disjoint publication observer, and `readyToRun=true`
remain pending full-profile gates. They move to a later immutable release
identity after 2.0.4 is published; they may never be backfilled as if they were
part of the 2.0.4 acceptance record.

## Release thesis

2.0.3 is a strong authenticated-content system *after* a consumer possesses a genuinely independent trust anchor. It is not yet a complete first-contact trust system: the repository contains the key, fingerprint, verifier, policy, signatures, and the instructions used to trust them. A repository-bytes attacker can therefore replace and self-consistently re-sign the entire in-band system before the first trusted pin exists. Separately, the Git guard and egress scanner have confirmed parser, encoding, sink, and waiver-authority gaps. Those controls are advisory unless a caller enforces their non-zero exit.

The 2.0.4 objective is not “more green output.” It is a verifiable chain in which the first root is external, every later rotation is authorized by an earlier root, each executed/installed object is bound to the signed release, advisory controls fail closed at an enforced gate, and the evidence package can be recomputed by an independent reviewer.

## Non-negotiable invariants

1. **External first trust:** no repository byte may authorize the initial key used to authenticate that repository.
2. **Exact-object continuity:** the object verified is the object installed or loaded; byte and POSIX-mode identity remain bound through consumption.
3. **Explicit parser grammar:** unsupported or ambiguous Git and egress forms fail closed in strict release gates.
4. **No artifact self-waiver:** untrusted content cannot exempt itself from a security finding.
5. **Evidence is executable:** every cited path and line resolves at its named revision; every fixture digest matches its captured result.
6. **One-head release:** review, evidence, signatures, attestations, and publication all bind to one immutable candidate commit and tree.

## Gate map

| Gate | Outcome | Enforced proof | Owner boundary |
|---|---|---|---|
| G0 | Evidence contract repaired | Evidence validator passes all paths, revisions, ranges, hashes, commands, outputs | Builder may prepare; independent reviewer accepts |
| G1 | First-contact root externalized | Forged in-band repository is rejected before content verification | Root ceremony and root rotation require authorized maintainers |
| G2 | Git guard grammar closed | Expanded 395-case red-before-green and regression corpus passes | No network push in tests; publication remains owner-authorized |
| G3 | Egress detection and waiver authority closed | Expanded 619-case encoding, parser, sink, and signed-waiver corpus passes | Runtime browser proof required for enhanced HTML |
| G4 | Runtime, credential, and helper boundaries hardened | Hook identity/mode, secret custody, URL parsing, runtime, exit semantics, and platform matrix pass | Same-UID boundary is enforced or explicitly advisory |
| G5 | Suite utility/provenance complete | 50/50 byte-and-mode parity; pinned dependencies; disclosures; real platform seats | No claim exceeds inspected provenance |
| G6 | Independent exact-head release review | Cross-family review, evidence packet, blind red-team rerun, signatures and attestations all bind to candidate head | Merge, tag, and publish require separate explicit authorization |

## G0 — Repair the evidence contract first

### Changes

- Add a machine-readable evidence schema containing: finding ID, release revision, source location(s), fixture path, fixture SHA-256, exact command, expected exit, captured output path, and output digest.
- Add `scripts/validate-evidence.py` (or equivalent) that rejects:
  - paths absent at the cited revision;
  - out-of-range lines unless a different, explicit evidence revision is named;
  - fixture hashes that do not match the named bytes;
  - captured output not bound to the same fixture digest;
  - commands that reference absent scripts;
  - ambiguous status such as “confirmed” without a passing discriminator.
- Correct the Kimi reproductions for K3-203-004 through K3-203-008 from the nonexistent `skills/agent-guardrails/scripts/scan-egress.sh` to `skills/self-contained-ship/scripts/scan-egress.sh`.
- Revision-scope K3-203-001's forged-payload line reference instead of attributing line 63 to the 61-line released file.
- Replace or re-run the K3-203-008 `w.html` evidence so `fixture-sha256.txt`, `scan.out`, and the included fixture describe the same bytes.

### Gate

`validate-evidence` passes on the complete red-team package and fails on three negative fixtures: missing path, out-of-range line, and output/fixture digest mismatch.

## G1 — Establish a genuine external root of trust

### Changes

- Keep the existing SSH-signature content verifier, but make its first accepted root an independently distributed object rather than a value learned from the repository.
- Introduce TUF-style root metadata with offline threshold keys, expiry, version, rollback protection, and root rotation authorized by both the previous and new root thresholds.
- Publish the initial root fingerprint through at least two independent channels under separate administrative control. The bootstrap accepts a locally pinned digest or threshold root file; it never copies the trust value from the checkout it is about to verify.
- Generate Sigstore/GitHub artifact attestations for release archives and the 50-skill manifest. Preserve verification bundles and transparency-log inclusion material for offline review. Treat this as an independent provenance signal, not a substitute for a securely bootstrapped root.
- Bind release tag, commit, tree, manifest, freshness index, archive digest, registry, and installation inventory into one release statement.

### Required negative tests

- Replace every in-tree public key, fingerprint constant, policy record, manifest, index, signature, verifier, and setup instruction; self-sign the forged tree. An externally pinned bootstrap must reject it *before* content verification or installation.
- Attempt rollback, same-version equivocation, skipped-root rotation, expired-root use, partial-threshold signing, archive substitution, and tag/tree mismatch.
- Demonstrate recovery and rotation with the old threshold authorizing the new root and the new threshold self-authorizing it.

### Gate

For the later full-assurance profile, an independent reviewer begins with only the documented external root and public distribution endpoints, verifies the new immutable release offline, and rejects every negative fixture. No “trust the fingerprint printed by this checkout” step remains.

## G2 — Replace heuristic Git matching with a declared, fail-closed grammar

### Changes

- Tokenize shell control operators and redirections without requiring surrounding whitespace; recognize attached forms such as `push>/dev/null`.
- Resolve Git `-c alias.<name>=!…` definitions together with invocation arguments. Never treat a bang-alias body as the whole command while discarding call-site verbs.
- Normalize supported global options, subcommands, brace/parameter expansions, and `update-ref` forms. Unknown or ambiguous constructs return `REVIEW/BLOCK` in strict mode.
- Cover `clean.requireForce=false`, repository mutation through plumbing commands, shell functions, aliases, and wrapper paths.
- Keep command execution tests inside disposable local repositories. No test may contact a remote or mutate a user repository.

### Gate

The expanded 395-case suite stays green; every new exploit fixture fails red on 2.0.3 and green on the candidate; parser differential tests prove that semantically equivalent dangerous commands receive the same decision. The release harness enforces the guard exit code.

## G3 — Close egress parser, encoding, sink, and waiver gaps

### Changes

- Scan every candidate in `data:`/`blob:` and comma-separated constructs rather than accepting after the first candidate.
- Parse bare and quoted `<meta http-equiv=refresh>` content consistently.
- Decode or conservatively reject UTF-16/UTF-32/control-byte content containing plausible network syntax. A binary waiver must never apply to a network path merely because NUL bytes are present.
- Detect markup execution/egress sinks, including `srcdoc`, event handlers, SVG/XLink, CSS `url()`, `image-set()`/`-webkit-image-set()`, XML stylesheets, and active embedded content.
- Remove artifact-local authority from `// egress-ok` and `UNCERT`. Store waivers in a separately signed policy keyed to the release revision, file digest, stable finding fingerprint, reviewer, reason, and expiry. `UNCERT` is never waivable.
- Retain static scanning as one gate only. Enhanced HTML also requires a sealed-load runtime test: offline browser, network interception, no unexpected requests, no service workers, no external fonts/assets, and a deterministic CSP.
- Add `-webkit-image-set`, `xml-stylesheet` processing instructions, and multi-URL `attributionsrc` to the fetching model, with supporting-browser fixtures.
- Enforce documented per-file and aggregate scan-byte ceilings. Stream parsing or retain only bounded state and digests; oversized input fails explicitly rather than exhausting the worker.

### Gate

The expanded 619-case suite stays green; all red-team fixtures and new multi-hit/whole-line/encoding variants are red-before-green; tampering with either artifact bytes or waiver policy invalidates the waiver. Browser evidence shows zero external requests at 375, 768, and 1440 px and in print mode.

## G4 — Bind hook decisions, credentials, URLs, and runtime semantics

### Changes

- Extract all supported skill identifiers from the documented event schema. Reject unknown, duplicate, or conflicting representations; require exactly one normalized identity.
- Add canonical `posixMode` to per-skill signed records and hook comparisons; reject unsafe group/world-writable modes. Define a separate, authenticated Windows metadata policy.
- Normalize broken-pipe and wrapper failures so scanner errors cannot collapse into success.
- Declare and enforce Python `>=3.10` (prefer a tested 3.12 release floor), Bash 3.2 compatibility where claimed, and absolute/digest-bound `ssh-keygen` discovery.
- Either hand the consumer an immutable verified snapshot, protect installed roots from the invoking identity, or label same-UID post-check mutation as an advisory residual. Do not claim an atomic loader boundary that is not present.
- Replace the DeepAPI example's bearer-token-in-`curl -H` argv transport with protected stdin or a mode-0600 curl configuration. Explicitly disable tracing and clean the carrier immediately.
- Default wizard secrets to password/secret-manager storage. Plaintext `.env` persistence becomes explicit opt-in and fails if the path is tracked, unignored, inside a build/publication context, or has unsafe ancestors.
- Replace the wizard's shell hostname extraction with a standards-compliant URL parser. Validate the exact parsed scheme, hostname, port, credentials, control characters, IDN form, and loopback exception before opening the same normalized URL.

### Gate

Conflicting payloads, chmod-only drift, unsafe write modes, broken pipes, runtime mismatch, trusted-tool path substitution, token-in-argv transport, unsafe plaintext-secret persistence, and query/fragment/userinfo URL confusion all fail. Tests run on real macOS/Bash 3.2 and Windows/NTFS/OpenSSH seats, not only emulation.

## G5 — Fortify all 50 islands without flattening them

### Changes

- Preserve the archipelago rule: one concern per island, common law in `CONTEXT.md`, no duplicated authority semantics.
- Vendor the Archipelago protocol helpers at a reviewed pinned commit or remove runnable claims that depend on absent files.
- Disclose the 2,067-line self-contained-ship scanner fixture suite as shipped test material and document how it is maintained.
- Complete provenance and third-party notices for fused source material, packages, and adapted patterns. Record upstream commit, license, local modifications, and review status.
- Preserve 50/50 byte-and-mode installation parity across Codex, Claude, Pi, and Hermes. Either produce a sanitized Claude.ai export profile or make the 13 current export warnings explicitly advisory and non-blocking.
- Run deterministic supply-chain candidate scans, but require human intent review; keyword matches alone are not vulnerability verdicts.
- Make the intake scanner enumerate symlinks and special files, use NUL-safe paths, and visibly encode untrusted filenames/snippets so candidate bytes cannot hide or counterfeit evidence.
- Remove the `handoff` hierarchy inversion: system and current user instructions always outrank skill prose, including any preferred temporary-file workflow.
- Assemble `console.lock` from exact `HEAD` blobs rather than a filesystem glob, and reject ignored blocks plus `skip-worktree`/`assume-unchanged` index flags before stamping provenance.

### Gate

Registry count, filesystem count, manifest count, and all four installed-root inventories equal 50. Byte, size, mode, provenance, and loader semantics match the release statement. No unresolved executable dependency points outside the signed or pinned closure.

## G6 — Exact-head review and release ceremony

### Full-assurance sequence — deferred after scoped 2.0.4

1. Establish the production 2-of-3 root under separate custody and publish its exact digest through two independently administered channels. Candidate-repository bytes may not supply this initial authority.
2. Produce red-before-green discriminators for every blocker, assign a new full-assurance version identity, and make every controlled source, test, document, state record, and generated report byte-final.
3. Run the 271-test repository suite, 395-case guard matrix, 619-case egress matrix, 82-test release-chain suite, 54-test runtime matrix, sealed-browser gate, Forge-50 closure, and the 31-record G0 evidence validator and replay.
4. Generate the v3 content manifest, then obtain the owner-held biometric content signature as the last candidate-byte mutation. Commit those exact bytes and create an unpublished annotated tag for the new full-assurance version at that commit.
5. Reproduce the commit and annotated tag from an ordinary clean clone and require content integrity 5/5. Any byte, commit, tree, or tag-target move returns to step 2.
6. Build the deterministic exact-tree archive, manifest-derived pre-install inventory, signed-history release index, and threshold release statement in that order. Sign the index in its distinct namespace and obtain the required release-role signatures without placing private material in Git or evidence.
7. Run the externally pinned threshold and freshness verifiers. Capture real macOS and Windows platform evidence, install through the accepted freshness launcher, and preserve four-root parity inside signed or independently witnessed external evidence.
8. Generate a complete evidence packet: commands, environment, exact inputs, exit codes, stdout/stderr, hashes, limitations, all eleven K3-204 lanes, and all 31 K3-203 reconciliations.
9. Request two signed disjoint non-OpenAI exact-head reviews, including a blind Kimi K3 rerun, then require protected-branch CI and two-party review. A controlled-byte or tag-target move voids the affected receipts.
10. Merge only through a protected path that preserves the accepted commit. Then publish the already accepted annotated tag and threshold-bound assets on GitHub, link them from the company endpoint, and re-observe the unchanged root digest through both pre-established trust channels.
11. Verify the signed publication-observer record and a fresh public consumer reaching `readyToRun=true` before describing a later immutable release as full-G0–G6 or production-assurance accepted. Each mutation or acceptance step remains explicit and separately auditable; no passing gate authorizes the next action by itself.

### Release stop conditions

- Any blocker lacks red-before-green proof.
- The candidate head changes after review.
- Initial trust depends on data first obtained from the candidate repository.
- A waiver is controlled by artifact content.
- Runtime/browser or real-platform proof is absent where claimed.
- Evidence paths, lines, hashes, or outputs cannot be recomputed.
- CI is green but a semantic gate reports partial, advisory, or unverified.

## Definition of world-class full assurance

“World-class” is earned when a new consumer can verify the release without trusting the release to define its own root; a poisoned repository, command string, artifact, or skill cannot silently grant itself authority; platform and installed-root behavior matches the signed model; and an independent reviewer can reconstruct every release claim from immutable evidence. A polished green indicator is presentation. These gates are the product.

For the scoped 2.0.4 publication, “world-class” applies only to the public
content-authenticated profile and its explicit evidence. The stronger paragraph
above remains the completion bar for the still-active full G0-G6 mission and a
later release identity.
