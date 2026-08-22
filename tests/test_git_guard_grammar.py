from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
GUARD = REPO / "skills/agent-guardrails/scripts/block-dangerous-git.sh"


class GitGuardGrammarTests(unittest.TestCase):
    def run_guard(self, command: str | None, *, strict: bool = False) -> subprocess.CompletedProcess[str]:
        payload = {} if command is None else {"tool_input": {"command": command}}
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": os.environ.get("HOME", "/tmp"),
            "TMPDIR": os.environ.get("TMPDIR", "/tmp"),
        }
        if strict:
            env["IDC_GUARD_STRICT"] = "1"
        return subprocess.run(
            ["bash", str(GUARD)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            env=env,
            check=False,
        )

    def test_push_redirection_forms_receive_same_block(self) -> None:
        commands = [
            "git push",
            "git push>/dev/null",
            "git push>>/dev/null",
            "git</dev/null push",
            "git push</dev/null origin main",
        ]
        self.assertEqual([self.run_guard(command).returncode for command in commands], [2] * 5)

    def test_reset_redirection_forms_receive_same_block(self) -> None:
        commands = [
            "git reset --hard",
            "git reset --hard>/dev/null",
            "git>/dev/null reset --hard",
        ]
        self.assertEqual([self.run_guard(command).returncode for command in commands], [2] * 3)

    def test_bang_alias_composes_with_call_site_arguments(self) -> None:
        blocked = [
            "git -c alias.p='!git' p push",
            "git -c alias.p='!git' p reset --hard",
            "git -c alias.p='!git' p clean -fd",
        ]
        self.assertEqual([self.run_guard(command).returncode for command in blocked], [2] * 3)
        self.assertEqual(self.run_guard("git -c alias.p='!git' p status").returncode, 0)

    def test_non_alias_config_and_plumbing_mutations_block(self) -> None:
        commands = [
            "git -c clean.requireForce=false clean -d",
            "git update-ref refs/heads/topic HEAD~1",
            "git update-ref -d refs/heads/topic",
            "git tag -f release HEAD~1",
        ]
        self.assertEqual([self.run_guard(command).returncode for command in commands], [2] * 4)

    def test_strict_mode_blocks_unsupported_dynamic_grammar(self) -> None:
        commands = [
            "C=git; $C push",
            "git $(printf pu)sh",
            'eval "git push"',
            'sh -c "git push"',
            "f(){ git push; }; f",
        ]
        self.assertEqual(
            [self.run_guard(command, strict=True).returncode for command in commands], [2] * 5
        )

    def test_strict_mode_blocks_missing_command_but_advisory_mode_announces_open(self) -> None:
        strict = self.run_guard(None, strict=True)
        advisory = self.run_guard(None, strict=False)
        self.assertEqual(strict.returncode, 2)
        self.assertIn("strict guard BLOCK", strict.stderr)
        self.assertEqual(advisory.returncode, 0)
        self.assertIn("advisory guard OPEN", advisory.stderr)

    def test_safe_commands_remain_available_in_strict_mode(self) -> None:
        for command in ("git status", "git diff", "git restore README.md"):
            with self.subTest(command=command):
                self.assertEqual(self.run_guard(command, strict=True).returncode, 0)


if __name__ == "__main__":
    unittest.main()
