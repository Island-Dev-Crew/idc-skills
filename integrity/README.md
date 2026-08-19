# Forge 50 signed integrity gate

Release 2.0.2 uses one dependency-free repository gate, not fifty self-checkers. The detached OpenSSH signature binds the canonical manifest to the stable 1Password-held Ed25519 key; the manifest binds all registered skill bytes, the registry, shared instructions, installer, verifier, hook adapter, policy, tests, and CI control files.

The trusted signing fingerprint is:

```text
SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA
```

## The five checks

`python3 scripts/skill_integrity.py verify` reports ready-to-run only when all five independently fail-capable checks pass:

1. **Signature:** the out-of-band fingerprint, `idc-skills` principal, `file` namespace, detached signature, manifest schema, and canonical JSON all agree. The verifier captures the manifest, signature, public key, and signer list once, verifies those bytes, and parses that same authenticated manifest snapshot; installer and hook consumers do not reopen the manifest path.
2. **Local bytes:** every file in all 50 registered skills plus every security-control file matches the signed SHA-256/size record; symlinks, inventory drift, case collisions, and Unicode-normalization collisions are denied. The complete local manifest is recomputed immediately before authorization, and installed skill directories are captured twice, so bytes that move during a check force red.
3. **External-reference set:** every HTTP(S) reference and every detected network-command occurrence is signed; a new or reclassified reference is drift.
4. **Remote content pins:** content classified `runtime-instruction` is fetched at verification time and must match its signed content hash and final redirect URL. Informational citations and fixed API endpoints are explicit allow-list entries, not silently treated as pinned instructions.
5. **Fetch/execute policy:** fetch-and-execute, process-substitution execution, download-to-file, and network package execution are denied unless the exact signed line hash is a reviewed non-executed example or an explicitly approved setup operation.

A fixture key may make all five test checks pass, but fixture mode never emits `readyToRun=true` and cannot authorize installation or execution.

## Trusted bootstrap (irreducible)

Repository code cannot prove its own trust anchor. Before running the verifier from a newly obtained copy, compare both public artifacts to the fingerprint received through a trusted channel:

```bash
ssh-keygen -lf keys/idc-skills-signing.pub
awk '{print $2, $3}' keys/allowed_signers | ssh-keygen -lf -
```

Both outputs must contain the exact fingerprint above. Then verify the manifest directly with the system OpenSSH client:

```bash
ssh-keygen -Y verify \
  -f keys/allowed_signers \
  -I idc-skills \
  -n file \
  -s integrity/manifest.json.sig \
  < integrity/manifest.json
```

Only after that succeeds is the verifier digest inside the signed manifest trustworthy. Compare it before execution:

```bash
expected="$(jq -r '.controlFiles["scripts/skill_integrity.py"].sha256' integrity/manifest.json)"
actual="sha256:$(shasum -a 256 scripts/skill_integrity.py | awk '{print $1}')"
test "$actual" = "$expected"
python3 scripts/skill_integrity.py verify
```

If the public key, `allowed_signers`, manifest, signature, or verifier came only from the same untrusted channel and the fingerprint was not independently checked, a green result is not a trustworthy bootstrap.

## Generate and sign

The manifest command fails before writing when policy, inventory, external references, denied patterns, symlinks, or required control files are invalid:

```bash
python3 scripts/skill_integrity.py manifest
python3 scripts/skill_integrity.py sign
python3 scripts/skill_integrity.py verify
```

`sign` uses the already-established agent-served public key and exactly this protocol:

```text
ssh-keygen -Y sign -f keys/idc-skills-signing.pub -U -n file integrity/manifest.json
```

The private key never enters the repository or local disk. `scripts/setup-signing-wizard.sh` verifies the existing stable fingerprint; it does not create or rotate the key. Rotation requires a separately reviewed out-of-band trust ceremony.

## Installation and pre-execution

The portable installer verifies the signed release before any destination preflight or write, then checks both staged and installed bytes against the signed per-skill file map:

```bash
python3 scripts/install.py install --verify-integrity --target agents
./scripts/install.sh
```

The shell wrapper is intentionally not a bypass; it always selects `--verify-integrity`.

For a harness with a `PreToolUse` event on its Skill tool, configure the reviewed adapter with absolute paths:

```text
python3 /trusted/idc-skills/scripts/pretooluse-skill-integrity.py \
  --repo-root /trusted/idc-skills \
  --installed-skills /absolute/harness/skills
```

`--installed-skills` is mandatory: the adapter refuses to attest only the canonical source while a harness may execute a different copied tree. It returns exit 2 on a missing installed root, invalid payload, non-green release, unknown skill, or installed-byte drift. A hook is enforced only after the receiving harness is actually configured to call it and a blocking smoke probe has been observed; the shipped adapter alone is merely available enforcement.

## External-reference classifications

- `runtime-instruction`: content an agent may retrieve and follow as instructions. HTTPS, a raw-content SHA-256 pin, and a final-URL pin are mandatory; verification re-fetches it.
- `api-endpoint`: a fixed service endpoint used as data transport. It is allow-listed and signed, but its changing response is not presented as pinned or safe. Credential, spend, response-injection, and authorization controls remain separate.
- `informational`: attribution, standards namespaces, examples, placeholders, and source citations that are not execution instructions. They are signed and allow-listed but are not fetched by the gate.

An unclassified or stale policy entry fails manifest generation. A mutable documentation page that tells the agent what to do must never be disguised as `informational`; it belongs in `runtime-instruction` or must be removed.

## Honest scope

This gate defends point-in-time local tamper, skill/control inventory drift, added external references, reviewed-policy drift, several fetch/execute forms, and mutable remote-instruction content drift. It materially raises the cost of poisoning because a repository editor cannot update the trusted signature without the agent-held private key and operator approval.

It does **not** prove that signed content is benevolent, protect a stolen/unlocked signing key, make an API response safe, understand all obfuscation or shell semantics, prevent a same-user attacker from changing files after the check, revoke credentials, constrain the agent's OS/network authority, or attest the agent's complete behavior from instantiation through completion. “Ready 5/5” is a signed preflight result at the bytes and remote observations checked; it is not a full execution trace or a Garnet-style claim about events the gate did not observe. Use least privilege, sandboxing, scoped identities, network controls, replayable audit records, and emergency credential/network shutdown for those layers.

No authority without evidence. A signature authenticates reviewed bytes; it does not turn bytes into truth.
