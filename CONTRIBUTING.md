# Contributing to Forge 50

Forge 50 is a fixed-seat, evidence-gated skill system. Contributions are welcome, but a persuasive description is not acceptance evidence.

## Before changing anything

1. Read [`AGENTS.md`](AGENTS.md) and [`CONTEXT.md`](CONTEXT.md).
2. For any skill edit, read [`skills/idc-skill-authoring/SKILL.md`](skills/idc-skill-authoring/SKILL.md) in full.
3. Open an issue describing the job, affected skill or public surface, intended evidence, and compatibility boundary.
4. Preserve upstream attribution and notices. Do not rewrite provenance to make a fusion look original.

## Skill changes

- Keep one concern per island and progressive disclosure one level deep.
- Preserve exact invocation semantics and the matching `agents/openai.yaml` policy.
- Add or update red-capable fixtures before accepting a green result.
- State enforced and advisory controls separately.
- Update registry, provenance, validation records, generated views, and manifest inputs together when required.
- A proposed 51st skill must win the repository’s displacement process; the fixed fifty does not expand by assertion.

## Public-surface changes

- Keep claims tied to repository or external evidence.
- Do not call a compatibility matrix universal support.
- Do not collapse `contentReady` into `readyToRun`.
- Keep generated catalog bytes reproducible with `python3 -B scripts/render_catalog.py --check`.
- Use local, provenance-recorded assets with meaningful alt text.

## Minimum local checks

```bash
python3 -B scripts/render_catalog.py --check
python3 -B scripts/validate_skills.py --json
python3 -B scripts/verify_forge_50.py --json
python3 -B scripts/verify_harness_support.py
python3 -B -m unittest discover -s tests -p 'test_*.py'
git diff --check
```

Run the additional guard, egress, integrity, shell, platform, or sealed-browser matrix for the files you touch. A zero exit is not enough when semantic output reports partial, deferred, or unverified evidence.

## Pull requests

Describe:

- the exact problem and scope;
- the base and final commit/tree;
- every public claim added or changed;
- commands run and red-before-green evidence;
- platform and harness limits;
- generated files and their source; and
- any deferred gate.

The author does not grant independent acceptance to their own diff. Release, merge, signature, and publication authority remain separate decisions.
