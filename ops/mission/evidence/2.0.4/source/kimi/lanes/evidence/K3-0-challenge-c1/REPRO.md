# K3-0 coordinator challenge of K3-8-C1 (independent re-execution, 2026-08-22)

Independent material: throwaway key SHA256:IeoLifAmljyDfIlF89N90kI3EvVINntgpumwq8pnt58
(K3-8 used SHA256:6bCR7/...), forged commit 986a240944f90202dfe50959ac4a45616f12fb92
(K3-8 used 0c6bb06...), payload skill = wizard (K3-8 used diagnose).

Chain executed from custody-verified pristine 2.0.3 tree (tag bbdbafeb / commit 26b9285 /
tree 0ca0997, anchors verified in CUSTODY.md):
1. sed-replaced fingerprint constant in all 10 in-band locations (bootstrap/idc_verify_fresh.py,
   scripts/skill_integrity.py, scripts/setup-signing-wizard.sh, integrity/{README.md,policy.json,
   manifest.json}, ops/mission/{brief.md,journal.md,evidence/signed-gate-2.0.2.json},
   IDC-Skills-2.0.2-Gap-Analysis...html). Top-level README.md carries NO fingerprint (minor
   correction to K3-8's file list; claim unaffected).
2. Swapped keys/{allowed_signers,idc-skills-signing.pub} to attacker key (principal idc-skills).
3. Inert payload appended to skills/wizard/SKILL.md.
4. `skill_integrity.py manifest` (forged verifier) -> MANIFEST OK profile=release skills=50;
   `sign` via throwaway ssh-agent -> SIGNED identity=idc-skills namespace=file.
   In-tree verify: contentReady=true score=5/5 (forged-intree-verify.json).
5. Forged trust-index: releases.json indexSequence=2, validUntil=+30d, entry pins forged
   commit/manifest/verifier/launcher digests; ssh-keygen -Y sign -n idc-skills-release-index-v1.
6. External deployment per integrity/README schema: launcher copy outside repo, canonical
   config (file source, bootstrapIndexSHA256=forged index sha, digest-pinned git/python3/
   ssh-keygen, checkpointPath, consumerHome). One fail-closed config nit hit and fixed
   (consumerPath /usr/bin+/bin duplicate-after-realpath -> single dir).
RESULT A (forged-launcher.json): pass=true readyToRun=true score="5/5+freshness"
   release=2.0.3 authority=external-signed-index rc=0.
RESULT B (genuine-vs-forged.json): PRISTINE launcher (compiled-in LBkF4... constant)
   vs the same forged tree+config -> rc=2, pass=false, error="public-key fingerprint
   mismatch: expected SHA256:LBkF4..., got SHA256:IeoLif...". Boundary proven both directions.
RESULT C (forged-install.json + payload-landing.txt): launcher-driven
   `install -- --target agents --skill wizard` rc=0, integrity-score=5/5, attacker payload
   bytes installed into consumer home (.agents/skills/wizard/SKILL.md line 52).

ADJUDICATION: CONFIRMED. Severity Critical per task §9 floor: forged release authority and
attacker-byte execution across the signed+freshness boundary without the private key, using
only released code and the documented bootstrap procedure. Scope gate: victim = consumer whose
first contact is the repository itself (the only onboarding path shipped); consumers with a
genuinely out-of-band-anchored launcher are immune (proven). Docs say "out-of-band" but the
release publishes the fingerprint only in-band; the skill_integrity.py docstring's "trusted,
out-of-band fingerprint documented below" is self-referential. Fix direction (not applied):
publish fingerprint via a channel that does not roll back with the repo (signed tag message +
independent second channel); mark in-repo fingerprint informational-only.
