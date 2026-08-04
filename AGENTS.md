# AGENTS

This repo is an **archipelago of agent skills**. Each island under `skills/<name>/SKILL.md` is a self-contained skill; the vocabulary and discipline they share live in [CONTEXT.md](CONTEXT.md).

- **Authoring or editing any skill** — read [`skills/idc-skill-authoring/SKILL.md`](skills/idc-skill-authoring/SKILL.md) first. It is the canon every island was built under.
- **The shared law** — no authority without evidence. State enforced-vs-advisory explicitly; never launder `unverified` into `verified`. See [CONTEXT.md](CONTEXT.md).
- **The registry** — [`skills/registry.json`](skills/registry.json) lists every island, its provenance, summary, and trigger phrases.
- **Distribution** — `./scripts/install.sh` fans every island across the four fleet skill folders (Codex/Claude/Pi/Hermes) and validates frontmatter.

Skills compose at runtime — one concern per island, loops over menus. Don't bundle; don't duplicate meaning across islands; keep every reference one level deep.
