# Verify Forge 50 without upgrading the claim

Verification is a ladder. Each rung establishes one authority and stops there.

| Check | Establishes | Does not establish |
|---|---|---|
| `validate_skills.py` | Registry/frontmatter structure and named compatibility diagnostics | Signed identity, security, installation, or runtime behavior |
| `verify_forge_50.py` | Registry, validation-record, provenance, and vendored protocol closure | That every skill succeeds on every real task |
| `skill_integrity.py verify` | Signed tracked-byte and policy closure under the independently anchored Forge key | Freshness, benevolent intent, sandboxing, or `readyToRun=true` |
| Harness probe | The exact loader/invocation behavior exercised on one named harness/version | Other harnesses, versions, or policies |
| External freshness launcher | Newest authorized release plus content integrity under protected external state | Protection from a compromised operating system or trusted runtime |
| Independent exact-head review | A reviewer’s verdict on one immutable commit/tree and stated matrix | Merge, tag, release, or broader authority |

## Current release identity

Forge 50 2.0.5 is a **limited-trust, public content-authenticated** release.

```text
repository  Island-Dev-Crew/idc-skills
tag         2.0.5
sequence    4
fingerprint SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA
```

The immutable release is [`2.0.5`](https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.5). Its release notes and assets provide the exact commit, tree, manifest digest, signature digest, and fingerprint. Compare the tag, commit, tree, manifest digest, and fingerprint with:

- the [company-site JSON witness](https://islanddevcrew.com/.well-known/idc-skills/2.0.5.json); and
- the DNSSEC TXT record at `_idc-skills-2-0-5.islanddevcrew.com`.

Those shared values must match byte-for-byte. Separately compare the detached manifest-signature digest between the GitHub release asset and company-site JSON witness; the DNS TXT schema does not carry that digest. The tracked repository deliberately does not embed its own resulting commit and tree as authority. Different URLs are not automatically independent authorities; the 2.0.5 claim is specifically the scoped profile documented in [`2.0.5-release-scope.md`](2.0.5-release-scope.md).

## Signed-content command

Choose and hash the OpenSSH executable independently, then run:

```bash
python3 -I -B scripts/skill_integrity.py verify \
  --ssh-keygen /independently/selected/ssh-keygen \
  --ssh-keygen-sha256 sha256:<independently-computed-executable-digest> \
  --json
```

The expected authority state is `contentReady=true` and `score=5/5`. The verifier deliberately never emits `readyToRun=true`.

## Explicitly deferred in 2.0.5

- production 2-of-3 root and release-role custody;
- completed eleven-lane Kimi K3 acceptance;
- independent Windows/NTFS/OpenSSH acceptance;
- freshness-authorized four-root fleet parity;
- a disjoint publication-observer receipt; and
- full-profile `readyToRun=true`.

The machinery for those gates ships as reviewed source, but implemented machinery is not production evidence. A later release must regenerate and independently bind its own manifest, signature, witnesses, receipts, and immutable identity.

## Report a mismatch

If the tag, commit, tree, manifest, signature, fingerprint, or witness differs, stop. Preserve the exact bytes and command output, then follow [`../SECURITY.md`](../SECURITY.md). Do not “repair” an immutable release or accept a close-looking fingerprint.
