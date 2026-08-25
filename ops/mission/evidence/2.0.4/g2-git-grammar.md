# G2 Git grammar — red-before-green record

## Scope

- Baseline release: `2.0.3` at `26b9285c1fe11a3ef875a34ff30faa0275eddf24`.
- Candidate branch: `codex/v2.0.4-hardening`.
- Host: macOS arm64, `/bin/bash` `3.2.57(1)-release`.
- Control remains a bounded command-string classifier. Normal mode is advisory; `IDC_GUARD_STRICT=1` is the fail-closed release mode.

## RED — released classifier plus new immutable cases

Command:

```bash
bash skills/agent-guardrails/scripts/test-block-dangerous-git.sh
```

Observed before implementation: `RESULT pass=301 fail=18`, non-zero exit. The eighteen failures were ten attached/mid-command redirection forms, three invoked bang-alias plus call-site-argument forms, `clean.requireForce=false`, `update-ref` move, `update-ref -d`, `tag -f`, and Bash brace expansion. The safe bang-alias-plus-`status` control passed.

## GREEN — candidate classifier

The same command now reports `RESULT pass=325 fail=0` under native macOS Bash 3.2. The added six cases exercise strict-mode variable dispatch, command assembly, `eval`, nested shell, function definition, and a proved-safe `git status` control.

Additional differential gate:

```bash
python3 -B -m unittest -v tests.test_git_guard_grammar
```

Observed: seven tests pass. Semantically equivalent push and hard-reset forms receive the same exit `2`; safe status/diff/single-file restore remain exit `0`; missing payload is exit `2` in strict mode and an announced exit `0` in ordinary advisory mode.

Static gate:

```bash
shellcheck -s bash skills/agent-guardrails/scripts/block-dangerous-git.sh skills/agent-guardrails/scripts/test-block-dangerous-git.sh
```

Observed after literal-fixture annotations: zero findings.

## Enforced versus advisory

- `IDC_GUARD_STRICT=1`: unsupported dynamic grammar, a missing command, and a missing classifier dependency block with exit `2`.
- ordinary mode: preserves the documented compatibility fail-open for a malformed payload or missing interpreter.
- neither mode is a shell sandbox; renamed binaries, unrecognized wrappers, repository/global aliases, and PowerShell remain outside the declared model and require repository/OS controls.

## 2026-08-23 construction re-run after K3-204 reconciliation

The original RED record above is preserved as chronology. On the repaired,
uncommitted construction tree based on `28edb946a84b7da85f8a38807b9a2def2f5aae31`,
the expanded matrix reports `RESULT pass=395 fail=0`. It adds the K3-204
editor/helper execution surfaces, destructive plumbing commands, named-file
descriptor redirections, `coproc`, parameter-spliced command dispatch, and
resource ceilings. `tests.test_git_guard_grammar` remains 7/7.

`skills/agent-guardrails/scripts/block-dangerous-git-strict.sh` is now the
durable installed strict entrypoint; it exports `IDC_GUARD_STRICT=1` and
delegates to the classifier in the same installed directory. Bash syntax and
ShellCheck are green for the classifier, strict wrapper, and fixture matrix.
This is construction evidence, not an exact signed-head platform acceptance
record.

## 2026-08-24 VERIFY-1 availability regression

Claude's conditional review identified an availability bypass in the strict
entrypoint: an attacker-controlled command string could make the classifier
spend unbounded time in shell-grammar analysis. The retained RED fixture feeds
a 96 KiB payload and requires strict mode to reject it before parsing in under
five seconds. The bounded control fixture feeds 48 KiB and proves ordinary
strict classification remains available below the ceiling.

The GREEN implementation enforces a 64 KiB maximum command-string size before
grammar analysis. The native Bash matrix remains `RESULT pass=395 fail=0`, and
`python3 -B -m unittest -v tests.test_git_guard_grammar` reports 9/9. The bound
is an enforced availability limit for the command-string classifier; it is not
a general shell sandbox or a promise to classify arbitrarily large scripts.
