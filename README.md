<div align="center">

<sub>IDC SKILLS · THE FORGE</sub>

# Forge 50

**Velocity, welded to proof.**

Fifty fused agent skills for building, researching, operating, verifying, and shipping—designed to increase velocity without loosening quality, control, or security boundaries.

[**Find my route**](#choose-your-outcome) · [Inspect the proof](#inspect-the-proof) · [Install safely](docs/getting-started.md)

</div>

![Five shape-coded island clusters linked to a luminous central forge, representing Forge 50's connected outcome routes.](assets/forge-50/hero-welded-constellation.webp)

<div align="center">

| REGISTERED SKILLS | OPENAI SIDECARS | RELEASE LINE | CONTENT INTEGRITY | FULL FRESHNESS |
|:---:|:---:|:---:|:---:|:---:|
| **50** | **50** | **2.0.5** | **signed · 5/5** | **deferred** |

<sub>The immutable tag and versioned external witnesses bind the exact release identity. “Signed · 5/5” means <code>contentReady</code>, not <code>readyToRun=true</code>.</sub>

</div>

Forge 50 is a navigable system of independent agent skills. Use one island for a focused job or connect several into an inspectable loop. The shared law is simple: **no authority without evidence**. A claim is not complete until a red-capable check produces something another person can inspect.

The canonical source and immutable releases live in this repository. The company site and DNSSEC record are external identity witnesses; neither is a second copy of the skill tree.

## Choose your outcome

**Choose the outcome. Bring the right discipline.** These five routes are editorial starting points—not popularity rankings or blanket certifications. Every listed skill is independently addressable; successful execution remains task-, dependency-, platform-, and harness-specific. Each loop is a recommended composition.

### Build

Turn an idea into a scoped, testable implementation without confusing motion with progress.

**Start here:** [`job-to-be-done`](skills/job-to-be-done/SKILL.md) · [`idc-skill-authoring`](skills/idc-skill-authoring/SKILL.md) · [`prototype`](skills/prototype/SKILL.md) · [`spec-pipeline`](skills/spec-pipeline/SKILL.md) · [`gauntlet-loop`](skills/gauntlet-loop/SKILL.md)

**Power-user loop:** `job-to-be-done → prototype → spec-pipeline → gauntlet-loop`

### Research

Replace plausible answers with sourced findings and context that survives the session.

**Start here:** [`grill`](skills/grill/SKILL.md) · [`research`](skills/research/SKILL.md) · [`video-analysis`](skills/video-analysis/SKILL.md) · [`data-source-map`](skills/data-source-map/SKILL.md) · [`productionize-opinion`](skills/productionize-opinion/SKILL.md)

**Power-user loop:** `grill → research/video-analysis → data-source-map → productionize-opinion`

### Operate

Coordinate agents and recurring work without losing ownership or control-plane history.

**Start here:** [`console-as-code`](skills/console-as-code/SKILL.md) · [`lane-claim`](skills/lane-claim/SKILL.md) · [`worktree-fleet`](skills/worktree-fleet/SKILL.md) · [`model-routing`](skills/model-routing/SKILL.md) · [`agent-schedule`](skills/agent-schedule/SKILL.md)

**Power-user loop:** `console-as-code → lane-claim → worktree-fleet/model-routing → agent-schedule`

### Verify & Ship

Turn “it works” into recomputable evidence, independent review, and exact-revision transport proof.

**Start here:** [`computer-use-smoke`](skills/computer-use-smoke/SKILL.md) · [`evidence-packet`](skills/evidence-packet/SKILL.md) · [`cross-family-review`](skills/cross-family-review/SKILL.md) · [`self-contained-ship`](skills/self-contained-ship/SKILL.md) · [`transport-complete`](skills/transport-complete/SKILL.md)

**Power-user loop:** `computer-use-smoke → evidence-packet → cross-family-review → self-contained-ship → transport-complete`

### Architect

Shape repository, domain, and module boundaries so agents navigate an explicit system.

**Start here:** [`arch-survey`](skills/arch-survey/SKILL.md) · [`deep-modules`](skills/deep-modules/SKILL.md) · [`folder-workspace`](skills/folder-workspace/SKILL.md) · [`workspace-scaffold`](skills/workspace-scaffold/SKILL.md) · [`archipelago`](skills/archipelago/SKILL.md)

**Power-user loop:** `arch-survey → deep-modules → folder-workspace/workspace-scaffold → archipelago`

[Browse the complete 50-skill catalog →](docs/catalog.md)

## Three loops worth learning first

### Idea to implementation

`job-to-be-done → prototype → spec-pipeline → gauntlet-loop`

Use this when the request sounds buildable but the value, design answer, or acceptance bar is still fuzzy. The chain narrows the bet, tests one uncertainty, defines implementation seams, and iterates against a falsifiable rubric. It does **not** prove production fitness or authorize release.

### Runtime proof to live revision

`computer-use-smoke → evidence-packet → cross-family-review → transport-complete`

Use this when a working change needs observable UI evidence, a recomputable packet, a different-family review, and proof that the accepted SHA reached its destination. A successful transport check does **not** expand the scope of the reviewer’s verdict.

### Hot spot to governed architecture

`arch-survey → deep-modules → folder-workspace → archipelago`

Use this when churn points to a structural problem rather than an isolated bug. The chain finds the seam, deepens its interface, makes the repository map explicit, and governs the build. It does **not** make architecture quality automatic; the chosen seam and evidence still need judgment.

## Install safely

The safe path begins outside the checkout: compare the tag, commit, tree, manifest digest, and signing fingerprint with the immutable release and both external witnesses. Do not execute repository code until that identity comparison agrees.

After the identity comparison, run the repository's structural checks:

```bash
python3 -I -B scripts/validate_skills.py --json
python3 -I -B scripts/verify_forge_50.py --json
```

Those commands execute repository-controlled Python. They establish registry/frontmatter and Forge-50 record closure for the identified checkout; they are not a sandbox and do not independently authenticate the checkout, prove loader behavior, or authorize installation.

The current public profile supports independently anchored signed-content verification. Authoritative mutating installation is deliberately routed through an independently installed freshness launcher and protected configuration; a clone cannot appoint itself as its own freshness authority. Start with the [safe evaluation and installation guide](docs/getting-started.md), then use the [harness support contract](docs/harness-support.md) for the exact target surface.

Keep these evidence layers separate:

1. byte distribution;
2. loader discovery;
3. explicit invocation;
4. implicit-invocation policy;
5. successful execution.

A green result at one layer is not evidence that the next layer passed.

## Inspect the proof

Forge 50 2.0.5 is a **limited-trust, public content-authenticated** release. Its front door is new; its assurance boundary remains deliberately narrower than full freshness authority.

| Bound value | 2.0.5 authority |
|---|---|
| Immutable release | [`2.0.5`](https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.5) |
| Manifest sequence | `3` |
| Forge key fingerprint | `SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA` |
| Company witness | [`/.well-known/idc-skills/2.0.5.json`](https://islanddevcrew.com/.well-known/idc-skills/2.0.5.json) |
| DNSSEC witness | `_idc-skills-2-0-5.islanddevcrew.com` |
| Commit, tree, manifest, and fingerprint | Compare the immutable release with both external witnesses |
| Manifest signature SHA-256 | Compare the release asset with the company JSON witness |

The tracked README does not appoint its own commit or tree. The immutable GitHub release and both out-of-repository witnesses carry the tag, commit, tree, manifest digest, and fingerprint so a changed tree cannot inherit an earlier identity. The DNS record does not carry the detached-signature digest; compare that value between the release asset and company JSON witness. Read the [verification guide](docs/verification.md) and the exact [2.0.5 claim boundary](docs/2.0.5-release-scope.md) before using stronger language.

What this profile does **not** claim:

- production 2-of-3 root or release-role custody;
- completed eleven-lane Kimi acceptance;
- independent Windows/NTFS acceptance;
- freshness-authorized four-root fleet parity;
- a disjoint publication-observer attestation; or
- full `readyToRun=true` authority.

## The full archipelago

The catalog is ordered deliberately: authoring and review foundations come first, the ICM workspace cluster occupies 22–28, and shipping/governance skills close the chain. The complete index exposes all 50 skills with their exact job, invocation mode, and recorded lineage.

- [Complete catalog](docs/catalog.md)
- [Shared composition law](CONTEXT.md)
- [Validation snapshot with named residuals · historical evidence epochs](docs/report.html)
- [Harness support contract](docs/harness-support.md)
- [Public documentation map](docs/README.md)

## Why Forge 50 exists

Forge 50 fuses public work from David Ondrej, Matt Pocock, and Jake Van Clief with IDC-authored islands and field discipline. IDC’s contribution is not a claim to other people’s work; it is the weld: a shared evidence law, exact-head review ceremony, cross-machine coordination, recomputable packets, and a fifty-seat system that composes without turning every skill into one giant prompt.

The repository’s [`provenance.json`](provenance.json) records source archives, exact commits where available, per-island lineage, and the unresolved historical ICM commit rather than inventing a pin. Required upstream notices remain in [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

## Trust boundary

The signed manifest binds tracked bytes, declared control files, POSIX-mode intent, external-reference observations, and reviewed fetch/execute exceptions. It does not certify benevolent intent, sandbox an agent, prevent same-user post-check mutation, or turn a repository-controlled verifier into an external freshness root.

For the deeper model:

- [`integrity/README.md`](integrity/README.md) — content integrity and external freshness boundary;
- [`trust/README.md`](trust/README.md) — deferred threshold-root ceremony;
- [`docs/release-acceptance-evidence.md`](docs/release-acceptance-evidence.md) — full-profile evidence format;
- [`SECURITY.md`](SECURITY.md) — vulnerability reporting and disclosure boundaries.

## Contributing

Start with [`CONTRIBUTING.md`](CONTRIBUTING.md). Skill changes must follow [`skills/idc-skill-authoring/SKILL.md`](skills/idc-skill-authoring/SKILL.md), preserve provenance, and bring red-capable evidence. A new skill does not expand the fixed fifty by assertion; it must displace an incumbent under the repository’s governance.

## License

MIT — see [`LICENSE`](LICENSE) and [`THIRD-PARTY-NOTICES.md`](THIRD-PARTY-NOTICES.md).

---

<div align="center">

**Island Development Crew** · Huntsville, Alabama
*No authority without evidence.*

</div>
