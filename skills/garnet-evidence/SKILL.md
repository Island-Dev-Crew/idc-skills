---
name: garnet-evidence
description: Assemble a Garnet evidence packet for a change - garnet check on every changed source, garnet diff-caps base-vs-head read as no-widening, a deterministic build manifest, an in-toto seal, and the project verification ladder, each captured with its exit code and rolled into packet.sha256 so a reviewer recomputes instead of trusting. Use when an Omarchy-hosted or fleet agent must prove a Garnet change before merge, or the user says "evidence packet", "prove this change", "garnet evidence", "diff-caps packet". Differentiator - evidence-packet is the generic Contributor-Road artifact; this island binds its rungs to Garnet 0.8.1's real CLI and the Garnet repo ladder, and records an absent tool as unverified rather than green.
---

# Garnet Evidence: the packet a Garnet change carries to the gate

Derived from [`evidence-packet`](../evidence-packet/SKILL.md), the Contributor-Road artifact, and bound to Garnet's real CLI. The thesis is unchanged: **no authority without evidence** ([`CONTEXT.md`](../../CONTEXT.md)); *acceptance is a decision made on evidence the author cannot fake.* A Garnet change that widens declared capability, fails the static capability check, or drifts from a deterministic build has to show that in a packet a reviewer recomputes from a fresh clone, before any human reads a sentence about it. A weak author and a frontier author are exactly as mergeable when both can run the ladder.

Two leading words: **no widening** (the diff-caps reading a reviewer applies) and **captured** (a rung's exit code lives in the packet, not in the author's memory).

## What a packet contains

The layout is evidence-packet's, unchanged, so the same reviewer and the same gate read it:

```
evidence/<change-slug>/
  head.txt         # the exact SHA the packet attests
  diff.patch       # git diff <base> HEAD, after the redaction rule
  ladder.md        # every rung: command, out file, exit, status, what it proves
  out/             # captured stdout+stderr, then EXIT= and STATUS=, for every rung
  packet.sha256    # sha256 roll-up of everything above - the packet's own seal
```

A claim in `ladder.md` with no file in `out/` is a sentence, not evidence.

## The Garnet rungs

Garnet 0.8.1 (`garnet` from the `garnet-cli` crate) exposes exactly these; nothing below is aspirational.

| rung | command | reading |
|---|---|---|
| `garnet-check` | `garnet check --format json <file>` on every `.garnet` source added or modified between base and HEAD, at HEAD and again at base | Exits 1 with diagnostic `check.caps_coverage` when a function transitively calls a capability-bearing primitive it does not declare; exits 1 on a parse error. The JSON carries `summary.ok`. Green means the static capability check accepts the source **as declared**. The base copy is the discriminator pair: red at base, green at HEAD is the change proving itself. |
| `garnet-diff-caps` | `garnet diff-caps --machine <base-file> <head-file>` | Exits 1 with verdict `authority-expanded` and `aggregate_gained` listing each cap when declared authority widened; exits 0 with `no-authority-expansion` otherwise; exits 2 when a file is missing. **The no-widening reading:** red is not automatically a defect. It is a widening the reviewer accepts on purpose, cap by cap, or the author narrows. A file absent at base diffs against an empty file, so every declared cap shows as gained. The tool's own scope note stands: declared-surface-only, it does not prove absence of undeclared authority - that is what `garnet-check` is for. |
| `garnet-build` | `garnet build --deterministic <file>` | Writes `<file>.manifest.json` with `source_hash` and `ast_hash`; the manifest is copied into `out/`. Two builds of the same source produce identical manifests, so the reviewer's recompute produces the same bytes or a finding. `--sign <keyfile>` exists for Ed25519-signed manifests; the packet does not require it. |
| `garnet-seal` | `garnet seal <file> --out <scratch>/<slug>.seal.json`, copied to `out/garnet-seal.<slug>.json` | Emits an in-toto Statement (predicateType `garnet-lang.org/attestation/seal/v1`) carrying the build manifest and the capability manifest. Without cosign on PATH it is emitted **UNSIGNED** and says so on stderr; that line is captured with the rung. Garnet does not sign supply chain itself. |
| `garnet-version` | `garnet version` | The exact toolchain that produced the rungs above, in the packet. |

What does **not** exist: there is no `garnet build --evidence` flag. The packet's seal is `packet.sha256`. A Garnet *release* adds the GPG-signed `SHA256SUMS.asc` (verified per the Garnet repo's `docs/release-signing.md` against `docs/garnet-release-signing.pub.asc`) and a CycloneDX SBOM; those are release artifacts, not rungs this island runs.

## The project ladder

From the Garnet repo's `CLAUDE.md`, run from the repo root, captured the same way:

```
cargo fmt --all -- --check                                      # rung: fmt
git diff --check <base-sha> <head-sha>                          # rung: whitespace
cargo test --workspace --no-fail-fast                           # rung: test
python3 scripts/garnet_v0_8_1_release_readiness.py --gate       # rung: readiness
```

Outside a Garnet checkout the cargo and readiness rungs go red for lack of a manifest or a gate script. That red is noise, not evidence (a rung only counts when the command itself ran against the thing it measures): drop those rungs with `GE_RUNGS` before stamping.

## Run it

```bash
# from the repo root, on the branch that holds the change; <skill-dir> is wherever this SKILL.md lives
bash <skill-dir>/scripts/garnet-evidence-packet.sh <slug> <base-ref> [file.garnet ...]
#   default sources: every .garnet file added or modified between <base-ref> and HEAD
#   GE_RUNGS="worktree garnet-version garnet-check garnet-diff-caps garnet-build garnet-seal fmt whitespace test readiness"
#   GE_OUT=evidence          packet root; the packet lands at $GE_OUT/<slug>/ and is never overwritten
#   GE_STRICT=1              exit 1 unless every rung is green (use it as a gate, not as a default)
#   GE_REDACT_SED=path.sed   repo-relative extra redaction rules, applied after builtin-v1 and hashed into ladder.md
```

[`scripts/garnet-evidence-packet.sh`](scripts/garnet-evidence-packet.sh) is the only place the rules below are mechanical. It runs on Bash 3.2, needs `git` and `shasum` or `sha256sum`, and installs nothing.

## Capture discipline

- **Every rung runs through one capture path.** stdout and stderr go to `out/<rung>.txt`, followed by `EXIT=<code>` and `STATUS=<ran|tool-absent|not-applicable>`. The exit code is the verdict; the status says whether a verdict exists.
- **Red rungs are evidence.** The script never stops at a red rung and never omits one. A packet whose `garnet-diff-caps` is red is a packet telling the reviewer exactly which caps widened; that is the packet doing its job.
- **An absent tool is `unverified`, never green.** No `garnet` or no `cargo` on PATH is captured as `EXIT=127 STATUS=tool-absent`, and `ladder.md` marks the rung `unverified`. The packet cannot claim a rung that did not run; a later packet on a machine with the tool can.
- **Status vocabulary:** `green` (ran, exit 0), `red` (ran, non-zero), `unverified` (tool absent), `n/a` (no applicable input, e.g. no `.garnet` source changed). `verified` is not a status the script can emit. Verification is the reviewer's recompute, not the author's run.
- **Redaction rule `builtin-v1`**, applied to `diff.patch` and every `out/` file before it is written: repo root, scratch dir, and home directory become `<repo>`, `<work>`, `<home>`; Bearer tokens, `Authorization:` headers, AWS access key ids, GitHub tokens, and `PRIVATE KEY` block headers become typed placeholders. The rule name, and the sha256 of any `GE_REDACT_SED`, are recorded in `ladder.md` so the reviewer applies the same normalization. If a rung cannot be made safe without destroying its evidentiary value, drop it with `GE_RUNGS` and arrange a protected review; never keep a leak because the hash would reproduce.
- **The Garnet rungs run in a scratch directory** on copies taken from the attested commits (`git show <sha>:<path>`), never on the working tree, so `.garnet-cache/` and build manifests never land in the repository and the rungs measure HEAD, not uncommitted edits. The `worktree` rung records `git status --porcelain` (excluding the packet root) and goes red when the tree is dirty.

## The recompute contract

The reviewer trusts none of it: fresh clone at `head.txt`, the same script with the same `GE_RUNGS` and base ref, then compare exit codes exactly and `out/` after the recorded redaction rule. The Garnet rungs are deterministic by construction (content hashes, machine JSON, no timestamps), so divergence there is a finding, not machine noise. Divergence in `cargo test` output after normalization is a finding too. Full contract, shallow-clone remedy, and the fresh-clone-never-worktree rule: [`evidence-packet`](../evidence-packet/SKILL.md).

## Enforced vs advisory

**Enforced** by the script's exit paths: a rung that did not run cannot be green; every requested rung has an `out/` file ending in `EXIT=` and `STATUS=`; an existing packet directory is never overwritten; the roll-up covers every file in the packet; `GE_STRICT=1` returns non-zero on any red or unverified rung. **Advisory:** which rungs belong in `GE_RUNGS`, whether `builtin-v1` redaction is sufficient for this change, and the no-widening judgment itself. Nothing here blocks a fabricated packet; the gate that voids one is [`cross-family-review`](../cross-family-review/SKILL.md) recomputing it from a fresh clone. Constructing a discriminating rung for a change no default rung discriminates on: [`diagnose`](../diagnose/SKILL.md).

## Install on Omarchy

Omarchy (Quattro source tree, version file `4.0.0.alpha`) fans one skill folder across four agent skill directories by symlink. Quoted verbatim from `migrations/1786098807.sh`:

```
mkdir -p ~/.agents/skills ~/.claude/skills ~/.codex/skills ~/.pi/agent/skills
ln -sfn "$OMARCHY_PATH/default/agents/skills/omarchy" ~/.agents/skills/omarchy
ln -sfn "$OMARCHY_PATH/default/agents/skills/omarchy" ~/.claude/skills/omarchy
ln -sfn "$OMARCHY_PATH/default/agents/skills/omarchy" ~/.codex/skills/omarchy
ln -sfn "$OMARCHY_PATH/default/agents/skills/omarchy" ~/.pi/agent/skills/omarchy
```

`migrations/1786539345.sh` loops the same four directories (`~/.agents/skills ~/.claude/skills ~/.codex/skills ~/.pi/agent/skills`) with `ln -sfn "$skills_source/<skill>" "$skills_dir/<skill>"`. Omarchy's own skills live under `$OMARCHY_PATH/default/agents/skills/<name>/SKILL.md`. A Gemini skills directory was **not** found in the source read; do not invent one.

Install this island the same way, from a checkout of the IDC skills repository:

```bash
for d in ~/.agents/skills ~/.claude/skills ~/.codex/skills ~/.pi/agent/skills; do mkdir -p "$d" && ln -sfn "$PWD/skills/garnet-evidence" "$d/garnet-evidence"; done
```

That is a symlink install for an Omarchy-hosted agent. It is not the Forge's signed fleet install (`scripts/install.py`), whose parity verifier fails closed on any symlinked entry under those roots; pick one install mode per machine and say which one a packet was produced under.

## Completion

**Done when** `head.txt` names the attested SHA; every rung in `GE_RUNGS` has an `out/` file ending in `EXIT=` and `STATUS=`; every changed `.garnet` source has its `garnet-check` pair and a `garnet-diff-caps` verdict, or `ladder.md` says `n/a` because none changed; every red or unverified rung is listed as such, with no red laundered into a sentence; and `packet.sha256` stamps the bundle. Hand the packet to [`cross-family-review`](../cross-family-review/SKILL.md); ship the exact SHA with [`transport-complete`](../transport-complete/SKILL.md).

Built by Island Development Crew.

**No authority without evidence. A rung that did not run is unverified, never green.**
