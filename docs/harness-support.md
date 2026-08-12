# IDC Skills Forge harness support contract

Contract schema: `idc.harness-support/v1.1`

Contract version: `1.1.0`

Evidence date: `2026-08-11`

Forge release inspected: `2.0.0` (50 skill islands)

The machine-readable source of this document is [`harness-support.json`](harness-support.json). This contract deliberately does **not** claim that one byte-identical `SKILL.md` works in every named product. A harness is positive only when a primary source identifies a loader surface and this contract gives a reproducible probe. An unrun probe is not presented as a passing observation.

## Classification law

| Classification | Meaning |
|---|---|
| `verified-native` | Primary documentation explicitly supports the Forge's raw loader location and the invocation controls the Forge relies on. No transform is required. A probe is supplied. |
| `format-validated` | The raw skill is documented as discoverable or was enumerated by the harness, but an invocation-policy field is absent, removed, or not proven. Discovery is not policy equivalence. |
| `documented-adapter` | Primary documentation provides a real target surface, but a path or format transform is required. The adapter is described, not silently assumed to exist. |
| `unsupported/unknown` | No primary evidence establishes a reliable filesystem import contract for Forge skills. Product adjacency, Markdown support, or a conversational “save skill” feature is not enough. |

“Native” is a format/loader statement, not an assurance that a model will follow instructions. “Invocation policy preserved” means a user-only island remains unavailable to autonomous model selection; descriptions saying “never auto-invoke” are advisory and do not satisfy that property.

Probe evidence uses four non-binary states: `unrun` means no step of the stated probe ran; `partial` means some evidence exists but the full pass criteria were not exercised or satisfied; `passed` means every criterion ran and passed; `failed` means the stated probe ran and at least one criterion failed. Inventory-only evidence is never a behavioral pass.

## Canonical pack facts and portability boundary

The Forge currently contains 50 `skills/<name>/SKILL.md` islands and 50 `skills/<name>/agents/openai.yaml` sidecars. Every island has `name` and `description`. Thirteen use the Claude-family extension `disable-model-invocation`; five of those also use `argument-hint`:

- `disable-model-invocation`: `batch-sample-curate`, `connected-fix-prompt`, `delegated-authority-prompt`, `gauntlet-loop`, `handoff`, `prose-craft`, `short`, `skill-duel`, `teach`, `to-questionnaire`, `wait-what`, `wayfinder`, `worktree-fleet`.
- `argument-hint`: `batch-sample-curate`, `connected-fix-prompt`, `gauntlet-loop`, `skill-duel`, `teach`.

The [Agent Skills specification](https://agentskills.io/specification) defines only six top-level fields: `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`. Consequently, the 13 extended islands are not strict-spec byte-for-byte artifacts. `skills-ref validate <skill-dir>` is the normative format probe. Moving an extension into `metadata` preserves bytes as annotation but does **not** make a harness enforce its semantics.

claude.ai has a second, current mismatch: its Help Center caps `description` at 200 characters, while 48 of the Forge's 50 descriptions exceed 200 (YAML-parsed range: 106–749). That adapter must author reviewed short routing descriptions; blind truncation is not acceptable evidence that trigger intent survived.

The 13 user-only islands are therefore a hard policy boundary:

1. A harness that implements `disable-model-invocation` may receive the raw island.
2. Codex receives the equivalent `agents/openai.yaml` policy (`policy.allow_implicit_invocation: false`).
3. A harness without an enforced equivalent must omit the island by default. Including it requires an explicit policy waiver; rewriting the description is only advisory.

## Support matrix

| Harness/surface | Classification | Documented loader scope | Transform | Invocation-policy result |
|---|---|---|---|---|
| OpenAI Codex | `verified-native` | project `.agents/skills`; user `~/.agents/skills` | none; retain `agents/openai.yaml` | preserved by `policy.allow_implicit_invocation: false` |
| Claude Code | `verified-native` | project `.claude/skills`; user `~/.claude/skills` | none | raw `disable-model-invocation` is explicit-only |
| claude.ai custom-skill upload | `documented-adapter` | ZIP upload in Settings/Customize | six-key frontmatter, ≤200-character description, required root-folder ZIP; omit user-only islands by default | `disable-model-invocation` is rejected and has no documented equivalent |
| Cursor | `verified-native` | project/user `.agents/skills` plus Cursor locations | none | raw `disable-model-invocation` is explicit-only |
| GitHub Copilot in VS Code | `verified-native` | project `.github/skills`, `.claude/skills`, `.agents/skills`; personal equivalents | none | raw `disable-model-invocation` and `argument-hint` documented |
| Amp | `format-validated` | project/user `.agents/skills` plus Amp and Claude locations | none for discovery | Neo removed user-invokable skills; 13 user-only islands are not safely portable |
| Kimi Code CLI | `verified-native` | project/user `.agents/skills` plus Kimi locations | none | kebab-case alias of `disableModelInvocation` documented |
| Google Antigravity IDE | `documented-adapter` | project `.agents/skills`; global `~/.gemini/config/skills` | copy/link to documented scope | no documented explicit-only field; omit 13 by default |
| Google Antigravity CLI | `documented-adapter` | documented CLI global/project paths differ by release surface | copy/link to the path reported by current Antigravity docs/CLI | no documented explicit-only field; omit 13 by default |
| OpenClaw | `verified-native` | workspace/user `.agents/skills` plus OpenClaw locations | none | `disable-model-invocation` documented as manual-only |
| Grok Build CLI | `format-validated` | project/user `.grok/skills`; user `~/.agents/skills` | none for discovery | user-invocable slash commands documented; explicit-only field not documented |
| Grok Bot account skill | `unsupported/unknown` | account-managed skills/plugins only in current docs | no filesystem adapter established | unknown |
| Buzz | `unsupported/unknown` | Buzz delegates to selected ACP agents; no stable cross-backend skill loader contract found | backend-specific experiment required | unknown and backend-dependent |
| Pi | `verified-native` | project/user `.agents/skills` plus Pi locations | none | `disable-model-invocation` documented as hidden from model, manual `/skill:name` retained |
| Hermes Agent, native Windows | `documented-adapter` | `<HERMES_HOME>/skills` | resolve active `HERMES_HOME`; copy/link there | no documented explicit-only equivalent; omit 13 by default |

## Harness evidence and probes

### OpenAI Codex — `verified-native`

OpenAI documents project `.agents/skills` discovery from the working directory through the repository root, user `~/.agents/skills`, explicit invocation, implicit description matching, and the `agents/openai.yaml` `policy.allow_implicit_invocation` switch in [Agent Skills](https://developers.openai.com/codex/skills). The Forge's 50 sidecars are the semantic bridge for the 13 user-only islands; Codex does not need the Claude-only top-level key.

Probe (fresh Codex task, from outside this Forge repository): run `/skills`, confirm all 50 registry names are present, invoke `$short`, and ask a relevance-matching question without naming `short`; pass only if the explicit call loads it and the unnamed prompt does not. Also run:

```powershell
(Get-ChildItem "$HOME/.agents/skills" -Directory |
  Where-Object { Test-Path (Join-Path $_.FullName 'SKILL.md') }).Count
```

### Claude Code — `verified-native`

Anthropic documents `.claude/skills` scopes, slash invocation, automatic discovery, and `disable-model-invocation: true` as user-only in [Extend Claude with skills](https://code.claude.com/docs/en/skills). The current installer copies to `~/.claude/skills` when that target exists. This classification covers Claude Code CLI, not the coordinator behavior of claude.ai.

Probe: start a fresh `claude` session, run `/short`, then issue a prompt matching `short` without naming it. Pass only if `/short` works and the unnamed prompt does not load it. Confirm the copied tree against `skills/registry.json` by directory name.

### claude.ai upload — `documented-adapter`

Anthropic documents ZIP upload under Settings/Customize in [Use Skills in Claude](https://support.claude.com/en/articles/12512180-use-skills-in-claude). The current [Claude skills documentation](https://code.claude.com/docs/en/skills) states that claude.ai uploads accept exactly `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`; any other top-level field causes a hard upload error. It also says enabled personal Cowork and cloud skills use these same upload rules. Separately, the current [How to create custom skills](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) page caps descriptions at 200 characters and requires the ZIP's top-level entry to be the named skill folder containing `SKILL.md`—files directly at archive root or under another wrapper directory are invalid. That Help Center page also calls `dependencies` optional metadata, but the dedicated six-key validator contract excludes it as a top-level field. This adapter does not emit top-level `dependencies` until Anthropic reconciles that documentation tension.

The supplied earlier Claude-session report independently observed hard rejection of the 13 extended islands. That historical observation agrees with the current documented six-key rule, but it is not presented as a fresh live-account upload probe.

Required adapter:

1. Build a scratch ZIP; never rewrite canonical islands in place. Its single top-level entry is `<skill-name>/`, with `<skill-name>/SKILL.md` inside; do not place skill files directly at archive root or add another wrapper directory.
2. Retain only the six documented top-level fields: `name`, `description`, `license`, `compatibility`, `metadata`, and `allowed-tools`.
3. Generate and review a routing-equivalent description of at most 200 characters for each of the 48 over-limit islands; preserve the capability and “Use when” trigger.
4. Copy `argument-hint` and `disable-model-invocation` into namespaced `metadata` solely for provenance.
5. Omit all 13 user-only islands unless the operator explicitly waives loss of enforced explicit-only behavior.

Probe (`unrun`): upload one raw extended canary and one transformed root-folder ZIP through Customize in a disposable profile. The raw canary must reproduce the documented hard error; the transformed canary must upload and enable. Then separately test explicit and implicit behavior. `package_skill.py` may preflight structure but cannot substitute for the live claude.ai validator. Passing upload proves format only, not invocation equivalence.

### Cursor — `verified-native`

Cursor documents project and global `.agents/skills`, `.cursor/skills`, Claude/Codex compatibility locations, automatic discovery, slash invocation, and explicit-only `disable-model-invocation` in [Agent Skills](https://cursor.com/docs/context/skills).

Probe: open Cursor Settings → Rules/Skills, confirm registry membership, run `/short`, then issue the same relevance prompt without the slash. Pass only if the explicit command loads and the automatic route does not.

### GitHub Copilot in VS Code — `verified-native`

Microsoft's current [Use Agent Skills in VS Code](https://code.visualstudio.com/docs/agent-customization/agent-skills) documents project `.github/skills`, `.claude/skills`, `.agents/skills`; personal `~/.copilot/skills`, `~/.claude/skills`, `~/.agents/skills`; `argument-hint`; and `disable-model-invocation` as manual slash-only. This is the primary source for the VS Code surface, not an inference from Copilot CLI.

Probe: with GitHub Copilot Chat enabled, run `Chat: Open Customizations`, inspect Skills for all registry names and errors, execute `/short`, and repeat without naming it. Pass only if discovery is complete and automatic invocation is blocked.

### Amp — `format-validated`

The [Amp Owner's Manual](https://ampcode.com/manual) documents this precedence: `~/.config/agents/skills`, `~/.agents/skills`, `~/.config/amp/skills`, project/parent `.agents/skills`, project/parent `.claude/skills`, `~/.claude/skills`, `~/.claude/plugins/cache`, `amp.skills.path`, built-ins, then Amp-managed personal and workspace repositories. It documents `amp skills list --json` for shell inventory and `skills: list` in the `Ctrl+O` palette. However, [Amp, Rebuilt](https://ampcode.com/news/neo) states that Neo removed user-invokable skills while retaining Agent Skills. Therefore raw discovery is documented but the Forge's 13 explicit-only semantics are not portable to Neo.

Probe (`partial`): `amp skills list --json` returned valid JSON and enumerated all 50 Forge registry names among 65 installed skills on the local pre-Neo build. In a fresh Amp TUI, run `Ctrl+O` → `skills: list` and compare names with `skills/registry.json`. This inventory result does not pass the explicit-only policy gate or upgrade the classification. Until Amp documents an enforced equivalent, omit the 13 user-only islands.

### Kimi Code CLI — `verified-native`

Moonshot documents project/user `.agents/skills`, Kimi-specific locations, automatic and `/skill:name` invocation, and `disableModelInvocation` with `disable-model-invocation` as an accepted alias in [Agent Skills](https://www.kimi.com/code/docs/en/kimi-code-cli/customization/skills.html).

Probe: start a fresh Kimi Code CLI session, run `/skill:short`, then repeat the task without naming the skill. Pass only if the explicit call loads it and automatic invocation does not. Compare `/skill` inventory against registry names.

### Google Antigravity — `documented-adapter`

Google documents project `.agents/skills`, global `~/.gemini/config/skills`, automatic description-based loading, and the current `.agents` spelling in [Antigravity Skills](https://antigravity.google/docs/skills). Google's [skills codelab](https://codelabs.developers.google.com/getting-started-with-antigravity-skills) records surface-specific Antigravity CLI paths and warns that `~/.agents/skills` behavior differs between the IDE and CLI. The Forge installer currently installs globally to `~/.agents/skills`; it does not populate the documented global Google path.

Adapter: resolve whether the target is IDE or CLI, copy/link eligible islands into the path shown by that current product's docs, and omit the 13 user-only islands because only `name`/`description` invocation is documented. Do not treat `.agent/skills` and `.agents/skills` as interchangeable without checking the running release.

Probe: run `/skills` in the Antigravity CLI or ask the IDE “What skills are available?” and compare exact registry names. Test a unique canary island in a fresh workspace. This probe was not run on this machine because Antigravity is absent.

### OpenClaw — `verified-native`

OpenClaw documents workspace/user `.agents/skills`, OpenClaw-specific directories, source precedence, and manual-only handling of `disable-model-invocation` in [Skills](https://docs.openclaw.ai/tools/skills). On this machine, `openclaw skills list` enumerated sampled Forge islands (`batch-sample-curate`, `gauntlet-loop`, and `idc-skill-authoring`) from `agents-skills-personal`.

Probe:

```powershell
openclaw skills list
```

Compare all registry names and test `/short` versus an unnamed relevance prompt in a fresh session. Inventory evidence alone does not prove invocation policy; the policy result rests on primary documentation until the behavioral probe passes.

### Grok Build CLI — `format-validated`

xAI documents `.grok/skills`, configured extra paths, user `~/.agents/skills`, user-invocable slash commands, and `grok inspect --json` in [Skills, Plugins & Marketplaces](https://docs.x.ai/build/features/skills-plugins-marketplaces), [Modes and Commands](https://docs.x.ai/build/modes-and-commands), and the [CLI reference](https://docs.x.ai/build/cli/reference). On this machine, `grok inspect` enumerated sampled Forge islands as user skills. Current primary docs do not define `disable-model-invocation`, so “Claude Code compatible” is not treated as proof of that field's enforcement.

Probe:

```powershell
grok inspect --json
```

Compare exact registry names, invoke `/short`, and issue the same task unnamed. Until the unnamed route is documented and proven blocked, omit the 13 user-only islands from Grok deployment.

### Grok Bot account skills — `unsupported/unknown`

xAI's [Grok Bot skills, routines, and automations](https://docs.x.ai/grok-bot/skills-routines-and-automations) describes account-managed skills taught conversationally or installed as account plugins. It does not document a local `SKILL.md` discovery path or byte-preserving ZIP import. Grok Build filesystem support must not be projected onto Grok Bot.

Probe needed to upgrade: a primary xAI page naming the import format/path plus a fresh-account canary import that preserves bundled files and invocation controls. Until then, no automated Forge install target exists.

### Buzz — `unsupported/unknown`

Block's primary [Buzz repository](https://github.com/block/buzz) describes an ACP client that launches selected agents such as Claude Code, Codex, and Goose. Local read-only inspection found `~/.buzz/.agents/skills/buzz-cli/SKILL.md`, but neither fact establishes that Buzz merges arbitrary personal skills consistently across ACP backends. The active backend may apply its own paths and policy semantics.

Probe needed to upgrade: create a harmless canary in each documented backend-specific scope, launch fresh Buzz sessions for every supported ACP backend, and record which backend enumerates and invokes it. No cross-backend install claim is made before that matrix exists.

### Pi — `verified-native`

Pi documents project/user `.agents/skills`, Pi-specific directories, automatic discovery, manual `/skill:name`, lenient unknown-field handling, and `disable-model-invocation` behavior in [Agent Skills](https://pi.dev/docs/latest/skills).

Probe: start a fresh Pi session, run `/skill:short`, then test the same task unnamed. Pass only if explicit invocation works and the model does not see the user-only island. Compare the interactive skill inventory with registry names.

### Hermes Agent on native Windows — `documented-adapter`

Nous Research documents skills under `HERMES_HOME/skills` and `skill_view`/slash use in [Work with Skills](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/guides/work-with-skills.md). The official [Windows native guide](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/windows-native.md) places the default home under `%LOCALAPPDATA%\hermes`; the loader source uses `HERMES_HOME / "skills"` in [`skills_tool.py`](https://github.com/NousResearch/hermes-agent/blob/main/tools/skills_tool.py).

Local evidence exposed a real installer mismatch: `hermes config path` returned `C:\Users\IslandDevCrew\AppData\Local\hermes\config.yaml`, while the current shell installer targets `$HOME/.hermes/skills`. Sample Forge names were absent from `hermes skills list`.

Adapter: derive `HERMES_HOME` from the active Hermes profile/configuration and copy/link eligible islands to `<HERMES_HOME>/skills`. Omit the 13 user-only islands because no primary Hermes source found here documents an enforced explicit-only equivalent.

Probe:

```powershell
$hermesConfig = hermes config path
$hermesHome = Split-Path -Parent $hermesConfig
hermes skills list
Test-Path (Join-Path $hermesHome 'skills/idc-skill-authoring/SKILL.md')
```

Pass path/discovery only when the boolean is true and all eligible registry names appear. Invocation-policy support remains absent until separately documented and probed.

## Contract verification

Run the dependency-free structural and repository-fact verifier from the repository root:

```powershell
python scripts/verify_harness_support.py
```

It performs no network access. It verifies schema and tier vocabulary, requested-target coverage, source attribution structure, Markdown/JSON key-fact agreement, probe evidence-state semantics, exact pack counts, claude.ai constraints, Amp loader/command consistency, and URL structure. Live source reachability and behavioral probes remain separate release evidence.

## Release gate for any future “all harnesses” claim

A release may claim support only if its generated evidence packet records, per harness and version:

1. exact loader path and scope;
2. accepted/rejected frontmatter keys;
3. registry names discovered versus expected;
4. explicit invocation result;
5. implicit invocation result for a `disable-model-invocation` canary;
6. bundled script/reference accessibility;
7. adapter output hash and canonical input hash;
8. primary documentation URL and retrieval date.

The gate fails closed on missing evidence. `50/50 directory copies`, a successful YAML parse, or a model saying it “has the skill” is insufficient by itself.
