# Guard and scanner final component evidence — 2026-08-20

This is pre-sign component evidence, not release authority.

## Dangerous-Git guard

- Approved component commit: `d0fac44e0c1fa7a0a2fb99703a487c8a8cf56967`
- Integration replay command: `/bin/bash skills/agent-guardrails/scripts/test-block-dangerous-git.sh`
- Native macOS Bash 3.2 result: `RESULT pass=300 fail=0`
- Exact Bash syntax, workflow ShellCheck, and `git diff --check`: green

## Static egress scanner

- Approved precommit diff: `e98cfac6997586ef1a4db272c855d2d4c1d74d84e2f65747860723e161cde469`
- Committed component: `04a5bd4`
- Integration replay command: `/bin/bash skills/self-contained-ship/scripts/test-scan-egress.sh`
- Native macOS Bash 3.2 result: `RESULT pass=589 fail=0`
- Exact three-file review scope, opening/closing diff hash, Bash syntax,
  workflow ShellCheck, and `git diff --check`: green

Both controls remain bounded defense-in-depth rungs. These results do not
replace signed content verification, external freshness, clean-clone replay,
required CI, or the public-source release proof.

## Integrated pre-sign replay

- Repository unit tests: 101/101
- Integrity + freshness matrix: 40/40
- Canonical validation: 50/50 skills, zero errors, 13 named advisories
- Harness contract: 15 surfaces / 50 skills
- Gauntlet records: 3 builders / 3 non-author critiques
- Validation records: 50 skills / 150 cases / deterministic report current
- Release shell syntax and exact workflow ShellCheck list: green
- Scratch v3 manifest: `MANIFEST OK`, 50 skills, 12 classified references,
  715 signed network-command occurrences
