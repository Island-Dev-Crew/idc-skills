# K3-0 Round 3 — dedup, severity calibration, regression coverage (2.0.3)

Target of record: tag `bbdbafebde00f411dfa55584f4943c88e5a0393a` → commit
`26b9285c1fe11a3ef875a34ff30faa0275eddf24` → tree `0ca09971998a058ca80c05fbfde4ca4d1178fdf8`.
Calibration scale per task §9 floor: P0 forge release authority / execute attacker bytes across
signed+freshness boundary w/o key · P1 practical sig/index/checkpoint bypass or privileged
install write/exec · P2 real cross-boundary weakness under constraints / material fail-open on
supported platform · P3 narrow/availability/precision · Ignore no-boundary/self-only/documented.

## A. Deduplication decisions

| Keep | Absorbs | Reason |
|------|---------|--------|
| K3-8-C2 (hook first-match-wins) | K3-3-C2 | Same mechanism, independently discovered by two seats (convergent). K3-3 evidence (E9) + K3-8 evidence (hook/) both retained. |
| K3-2-C3 (staged snapshot swap window) | K3-1-C8 (TOCTOU race battery) | Same surface; K3-1's 30-run race + double-build stability check is the bounding counterevidence. Single finding, Info/Theoretical. |
| K3-7-C1 (guard fail-open on missing python3/jq) | K3-4 documented-exclusion line | Same behavior; K3-4 noted it as documented exclusion, K3-7 flagged for adjudication. Calibrated Low (documented, advisory, platform can't run main system w/o python3 anyway). |
| K3-5 overlap note (skill_integrity URL_RE weaker than scan-egress) | K3-6-C6 (recall parity HELD) | K3-6 proved parity on the live tree; URL_RE weakness is latent (no live instance). One Info note. |
| K3-3-C1 (hook posixMode) | 2.0.2-era D-1 regression check | Partially fixed in 2.0.3 (repositoryFiles carry posixMode; skill records + hook still bytes+size). Residual Low. |

## B. Final severity roster (coordinator-calibrated)

### Critical — 1
| Final ID | Source | Title | Status |
|----------|--------|-------|--------|
| K3-203-001 | K3-8-C1 + K3-0 challenge | In-band trust anchors: first-contact bootstrap forgeable end-to-end (forged release authority without key) | CONFIRMED (two independent end-to-end repros: K3-8 key 6bCR7…/commit 0c6bb06…; K3-0 key IeoLif…/commit 986a2409…) |

Scope gate: victim = fresh consumer whose only anchor channel is the repo (the sole onboarding
path shipped). Existing out-of-band-anchored installs REJECT the forged tree (proven both
directions, rc=2 fingerprint mismatch). Kept Critical because the primary threat question grants
the repo-bytes attacker and the released artifacts contain no out-of-band channel.

### Medium — 8
| Final ID | Source | Title | Status |
|----------|--------|-------|--------|
| K3-203-002 | K3-4-C1 | Redirection glued to decisive token defeats every guarded git subcommand | CONFIRMED (real-git proofs) |
| K3-203-003 | K3-4-C3 | Bang alias `!git` composes with call-site args (`-c alias.p='!git' p push`) | CONFIRMED (real-git proofs) |
| K3-203-004 | K3-5-C1 | srcset/imagesrcset/ping/setAttribute: leading data:/blob: candidate suppresses later external candidates | CONFIRMED (Chromium runtime) |
| K3-203-005 | K3-5-C2 | Meta refresh without `url=` (bare `;`-form) missed for netpath targets | CONFIRMED (Chromium runtime) |
| K3-203-006 | K3-5-C3 | Binary path launders browser-active markup (UTF-16/32 BOM, control byte) under --allow-binary | CONFIRMED (Chromium runtime) |
| K3-203-007 | K3-5-C4 | Markup-injection sinks unmodeled (innerHTML/outerHTML/insertAdjacentHTML/document.write) | CONFIRMED (Chromium runtime) |
| K3-203-008 | K3-5-C7 | Self-service unsigned waiver can silence UNCERT fail-closed tripwire; one marker waives whole line | CONFIRMED (scanner) |
| K3-203-009 | K3-3-C2 + K3-8-C2 | PreToolUse hook first-match-wins skill-field extraction; disagreeing payload fields not cross-checked | THEORETICAL (mechanics CONFIRMED both seats; no triggering harness observed) |

Severity rationale for guard/egress Mediums: each defeats an explicit claimed control boundary
inside its claimed grammar on a supported platform (Linux, real git 2.39.5 / Chromium 151),
runtime-proven; none touches the signature/freshness authority (which is why not High per §9).
K3-203-009: hook IS a readyToRun-side boundary; impact warrants Medium, but trigger requires a
harness payload shape not observed in the shipped harness (Claude Code) → THEORETICAL.

### Low — 16
| Final ID | Source | Title | Status |
|----------|--------|-------|--------|
| K3-203-010 | K3-3-C1 | Hook binds sha256+size only; posixMode/xattrs of installed skill bytes invisible | CONFIRMED |
| K3-203-011 | K3-3-C3 | Broken stderr pipe collapses intended BLOCK (exit 2) into exit 120 | CONFIRMED (behavior) |
| K3-203-012 | K3-3-C4 | Direct (non-launcher) hook routing honors PYTHONPATH shadowing; launcher immune | THEORETICAL |
| K3-203-013 | K3-2-C2 | http.client.IncompleteRead escapes fetch error handling (fail-closed traceback) | CONFIRMED (fail-closed nit) |
| K3-203-014 | K3-2-C5 | Non-FreshnessError consumer exceptions escape main() catch list (fail-closed) | CONFIRMED (fail-closed nit) |
| K3-203-015 | K3-4-C2 | `-c clean.requireForce=false clean -d` deletes untracked files, no force flag | CONFIRMED |
| K3-203-016 | K3-4-C5 | `update-ref`/`tag -f` unguarded plumbing ref rewrites vs ambiguous claim wording | CONFIRMED |
| K3-203-017 | K3-4-C4 | `git {push,}` brace expansion executes (Bash grammar outside lexical claim) | CONFIRMED |
| K3-203-018 | K3-5-C5 | CSS `-webkit-image-set()` string candidates never scanned | CONFIRMED (runtime) |
| K3-203-019 | K3-5-C6 | `<?xml-stylesheet href>` PI invisible in xml/svg/xhtml | CONFIRMED (runtime) |
| K3-203-020 | K3-6-C2 | archipelago: runnable protocol scripts referenced, not vendored; prose-only pin | CONFIRMED (self-disclosed) |
| K3-203-021 | K3-6-C3 | self-contained-ship: 2,067-line executable fixture suite undisclosed by SKILL.md | CONFIRMED (hygiene) |
| K3-203-022 | K3-7-C1 | Dangerous-git guard fails open on missing python3/jq (documented, advisory) | CONFIRMED (documented) |
| K3-203-023 | K3-7-C2 | In-tree verifier resolves ssh-keygen via inherited PATH (asymmetric w/ launcher) | CONFIRMED |
| K3-203-024 | K3-7-C3 | Minimum-Python floor undocumented; 3.9 fails closed via incidental TypeError | CONFIRMED |
| K3-203-025 | K3-6-C5 | Provenance traceability gap vs provenance.json / THIRD-PARTY-NOTICES | CONFIRMED (hygiene) |

### Informational — 6
| Final ID | Source | Title | Status |
|----------|--------|-------|--------|
| K3-203-026 | K3-2-C3 | Staged consumer snapshot not re-hashed between content verify and consumer exec (same-UID residual) | THEORETICAL (documented boundary) |
| K3-203-027 | K3-1-C9/C6-sub | Forgeable handoff marker unlocks routing only; NaN accepted in never-compared fields | FALSE-POSITIVE (documented non-boundary) |
| K3-203-028 | K3-6-C1 | research skill: live paid-API call + op credential read — exemplary gating, residual by design | FALSE-POSITIVE for malice |
| K3-203-029 | K3-6-C4 | video-analysis downloads arbitrary user-supplied media URLs (user-invoked tool) | CONFIRMED (by-design tool behavior) |
| K3-203-030 | K3-7-C4/C5/C6 | Publication hygiene: CHANGELOG cites 3 absent commits; CI run/PR refs 404; "candidate" heading in shipped tag | CONFIRMED (cosmetic) |
| K3-203-031 | K3-7-C7/C8 | Windows mode/ownership checks design-limited; os.defpath ssh-keygen likely unsatisfiable on stock Windows | UNVERIFIED on Windows (deps named) |

### HELD / FALSE-POSITIVE batteries (no finding IDs — recorded in ATTEMPTS.md)
K3-1 C1–C8 (all crypto/content attacks HELD: manifest edit, anchor substitution incl. append
variant — the 2.0.2 A-2 class now rejected by exactly-one-signer rule, namespace/principal
matrix, replay, canonical-JSON, closure, TOCTOU) · K3-2 C1/C4/C6/C7/C8 · K3-3 C5/C6 ·
K3-4 C6 boundary inventory + F1 (no undocumented FPs) · K3-5 C8 FP cluster · K3-6 C6 parity ·
K3-8 C3–C8.

## C. 2.0.2-era regression coverage (known-hole re-checks)

| 2.0.2 finding | 2.0.3 status | Evidence seat |
|---|---|---|
| A-1 anchor swap → green | CLOSED at pinned-launcher layer (hardcoded fingerprint + exactly-one-signer); RESIDUAL at first-contact bootstrap = K3-203-001 | K3-1-C2, K3-8-C1, K3-0 |
| A-2 append second principal | CLOSED — 12-case allowed_signers battery: verifier enforces exactly-one-signer (raw ssh-keygen still accepts; the released verifier does not) | K3-1-C3 |
| A-3 no freshness / rollback | CLOSED — v3 schema gate + sequence floors + checkpoint + 30-day expiry; 2.0.2 whole-tree replay rejected | K3-2 (70 checks), K3-8-C4 |
| A-4 validator sneak-past | MOOT as boundary — manifest/signature is the gate; regenerated manifest canonically identical; 50-skill intake clean | K3-6 |
| B-team 14 guard bypasses (IFS, quote/backslash splice, alias injection, pathspec magic, etc.) | ALL CLOSED (re-tested each class); NEW classes found = K3-203-002/003/015/016/017 | K3-4 |
| C-0 scan-egress dir mode extension gap | CLOSED — dir mode opens every regular file by content | K3-5 attempts |
| C-1/C-2 egress form/channel gaps | PARTIALLY CLOSED — old forms blocked; NEW runtime-proven forms = K3-203-004..008/018/019 | K3-5 |
| D-1 content-only hashing (mode flips) | PARTIALLY CLOSED — repositoryFiles carry posixMode; hook layer residual = K3-203-010 | K3-3-C1 |
| D-2 empty dirs / dir modes | CLOSED by construction — closure bound to git tree blobs; git never versions empty dirs | K3-1-C7 |
| D-3 --verify-only self-referential | CLOSED except via K3-203-001 — sync/verify binds to signed manifest, not just canonical tree | K3-3 (blind #8) |
| A-6 wizard anchor auto-select | NARROWED — wizard still in-band (fingerprint carried in wizard script, patched in my forge), but launch-time anchor no longer depends on wizard output; subsumed by K3-203-001 fix direction | K3-0 observation |

## D. Disposition inputs for VERDICT.md

- Seats occupied: K3-1, K3-2, K3-3, K3-4, K3-5, K3-6, K3-7, K3-8 (8/8 + K3-0 coordinator).
- Primary question answer: YES for first-contact bootstrap (K3-203-001); NO for every consumer
  with a genuine out-of-band anchor (all direct crypto/freshness/content attacks HELD).
- Disposition per task rules: changes-requested (1 Critical w/ narrow-but-normal precondition;
  8 Medium; no evidence gaps blocking judgment; Windows/macOS items UNVERIFIED with deps named).
- Top-3 fixes for 2.0.4: (1) ship the fingerprint out-of-band (signed tag message + independent
  second channel; mark in-repo copies informational-only); (2) guard: treat < > >& <& >| as
  token boundaries everywhere + classify bang-alias body+args + clean.requireForce policy;
  (3) scan-egress: multi-candidate split before data:/blob: short-circuit + meta-refresh bare
  form + UTF-16/32 re-decode before binary waiver + markup-sink grammar + waiver binding.
