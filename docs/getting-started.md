# Evaluate and install Forge 50 safely

Forge 50 separates four decisions that ordinary install guides often collapse:

1. which exact release you acquired;
2. whether its content signature and external identity witnesses agree;
3. whether the target harness preserves the skill’s loader and invocation contract; and
4. whether you require external freshness authority before any mutating install.

The 2.0.5 release line is a **limited-trust, public content-authenticated** profile. It can establish `contentReady=true`; it does not claim `readyToRun=true`.

## 1. Acquire one immutable release

Use the canonical repository and detach at the exact tag named by both external witnesses:

```bash
git clone https://github.com/Island-Dev-Crew/idc-skills.git
cd idc-skills
git checkout --detach 2.0.5
git rev-parse HEAD
git rev-parse HEAD^{tree}
```

Do not take the expected commit and tree from the tracked README or from the checkout you are trying to authenticate. Read them from the immutable `2.0.5` GitHub release and both external witnesses, then require all sources and the commands above to agree byte-for-byte. Stop on any mismatch. Do not substitute a branch, fork, mirror, archive repost, or similarly named tag.

## 2. Compare the out-of-repository identity

Compare the release values against both channels before trusting repository-contained keys or instructions:

- HTTPS witness: [`https://islanddevcrew.com/.well-known/idc-skills/2.0.5.json`](https://islanddevcrew.com/.well-known/idc-skills/2.0.5.json)
- DNSSEC TXT owner name: `_idc-skills-2-0-5.islanddevcrew.com`

The tag, commit, tree, manifest digest, and full signing fingerprint must agree exactly. DNSSEC validation requires an authenticated validating resolver or tool such as `delv`; seeing a TXT string with plain DNS lookup is not cryptographic validation.

## 3. Run non-authoritative structural checks after identity comparison

Only after steps 1–2 agree, these checks require no third-party Python package:

```bash
python3 -I -B scripts/validate_skills.py --json
python3 -I -B scripts/verify_forge_50.py --json
python3 -I -B scripts/verify_harness_support.py
python3 -I -B scripts/verify_runtime_requirements.py \
  --contract runtime-requirements.json
```

These commands execute repository-controlled Python. They prove their named repository facts for the identified checkout; they are not a sandbox, do not independently authenticate the checkout, and do not prove successful invocation in a live harness.

## 4. Authenticate the signed content

Select the OpenSSH executable independently of the untrusted checkout, compute its SHA-256 outside candidate-controlled configuration, and pass both values explicitly:

```bash
python3 -I -B scripts/skill_integrity.py verify \
  --ssh-keygen /independently/selected/ssh-keygen \
  --ssh-keygen-sha256 sha256:<independently-computed-executable-digest> \
  --json
```

Proceed only if the report says `contentReady: true`, `score: 5/5`, and shows the independently anchored fingerprint:

```text
SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA
```

This gate authenticates the scoped signed bytes and policies. It is not freshness authority, a sandbox, or proof that every signed instruction is safe for every environment.

## 5. Choose an installation authority

### Full-authority path

Every mutating repository-provided installer route is designed to run behind an independently installed freshness launcher, protected configuration, protected checkpoint, and digest-pinned runtime tools. The supported command shape is:

```bash
/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  verify

/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  install -- --target agents --verify-only --json

/trusted/runtime/python3 -I -B /trusted/bin/idc-verify-fresh \
  --repo-root /absolute/idc-skills \
  --config /trusted/etc/idc-skills-freshness.json \
  install -- --target agents --json
```

These paths are deployment templates, not values to copy literally. The production threshold/freshness ceremony is not activated for 2.0.5, so 2.0.5 cannot honestly complete this route as `readyToRun=true`. Read [`../integrity/README.md`](../integrity/README.md) before provisioning it.

### Limited-trust local policy

An operator may adopt content after a valid `contentReady` result under an explicit local policy that accepts the missing external freshness guarantee. That choice is outside the 2.0.5 release authority. The repository intentionally provides no flag that relabels it `readyToRun=true` and no direct-install bypass for the launcher.

If you need a turnkey freshness-authorized installation, wait for a release whose immutable evidence explicitly closes that profile. Do not manufacture the claim by setting internal handoff variables or copying an in-tree launcher into a trusted label.

## 6. Verify the target harness separately

Read [`harness-support.md`](harness-support.md). Its 15-surface matrix is a dated contract with mixed evidence states, not a universal support promise. In particular, preserve the distinction between copied bytes, discovery, explicit invocation, implicit-invocation policy, and actual execution.
