# Security policy

Forge 50 treats a mismatched release identity, signature bypass, unsafe installer behavior, authority confusion, or skill supply-chain defect as a security issue.

## Reporting

Use GitHub’s private **Report a vulnerability** flow when it is available for this repository:

[`https://github.com/Island-Dev-Crew/idc-skills/security/advisories/new`](https://github.com/Island-Dev-Crew/idc-skills/security/advisories/new)

If GitHub does not show a private reporting form, do **not** place exploit details, credentials, private keys, or unredacted host evidence in a public issue. Open a minimal issue that says only that you need a private security channel and names the affected release; wait for a maintainer to establish that channel.

Include privately:

- exact release, tag, commit, and tree;
- expected and observed digests or fingerprints;
- minimal reproduction steps and red output;
- affected platform/harness and version;
- whether exploitation requires same-user, administrator, network, or signing access; and
- any public-disclosure deadline.

Never send secrets, private signing material, recovery codes, or biometric prompts. Redact tokens and personal filesystem paths unless they are essential to the finding.

## Supported security profile

The 2.0.5 release line is supported as a limited-trust, public content-authenticated profile. Its exact guarantees and deferred authorities are in [`docs/2.0.5-release-scope.md`](docs/2.0.5-release-scope.md).

Security fixes receive a new immutable version. Published tags, manifests, signatures, witnesses, and release assets are not silently rewritten or reused.

## Scope reminders

- A valid signature authenticates bytes, not benevolent intent.
- `contentReady=true` is not `readyToRun=true`.
- The in-tree verifier cannot establish whole-tree freshness by itself.
- Windows/NTFS acceptance and the production threshold ceremony remain separate evidence gates.
- Scanner findings require review; a scanner pass is not a system-wide safety certificate.

Public discussion may begin only after affected users have a correction path or the maintainers and reporter agree that immediate disclosure better protects users.
