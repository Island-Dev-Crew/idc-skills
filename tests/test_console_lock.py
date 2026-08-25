from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ASSEMBLER = REPO / "console/assemble.sh"
GIT = str(Path(shutil.which("git") or "").resolve())
SHA256 = str(Path(shutil.which("shasum") or "").resolve())
SHA256SUM = str(Path(shutil.which("sha256sum") or "").resolve())


class ConsoleLockTests(unittest.TestCase):
    def fixture(self, root: Path) -> None:
        (root / "console/blocks").mkdir(parents=True)
        shutil.copy2(ASSEMBLER, root / "console/assemble.sh")
        (root / "console/assemble.sh").chmod(0o755)
        (root / "console/blocks/10-second.md").write_bytes(b"second\n")
        (root / "console/blocks/00-first.md").write_bytes(b"first\n")
        subprocess.run([GIT, "-C", str(root), "init", "-q"], check=True)
        subprocess.run([GIT, "-C", str(root), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run([GIT, "-C", str(root), "config", "user.name", "Fixture"], check=True)
        subprocess.run([GIT, "-C", str(root), "config", "core.autocrlf", "false"], check=True)
        subprocess.run([GIT, "-C", str(root), "add", "."], check=True)
        subprocess.run([GIT, "-C", str(root), "commit", "-qm", "fixture"], check=True)

    def run_assembler(
        self,
        root: Path,
        *,
        sha256: str = SHA256,
        sha256_kind: str | None = "shasum",
    ) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["IDC_CONSOLE_GIT"] = GIT
        environment["IDC_CONSOLE_SHA256"] = sha256
        if sha256_kind is not None:
            environment["IDC_CONSOLE_SHA256_KIND"] = sha256_kind
        else:
            environment.pop("IDC_CONSOLE_SHA256_KIND", None)
        return subprocess.run(
            ["/bin/bash", str(root / "console/assemble.sh")],
            cwd=root,
            env=environment,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_lock_is_assembled_from_sorted_exact_head_blobs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            result = self.run_assembler(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            body = b"first\nsecond\n"
            blocks_tree = subprocess.run(
                [GIT, "-C", str(root), "rev-parse", "HEAD:console/blocks"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()
            expected = (
                f"<!-- console.lock - assembled from blocks-tree:{blocks_tree} - sha256:{hashlib.sha256(body).hexdigest()} -->\n\n".encode()
                + body
            )
            self.assertEqual((root / "console/console.lock").read_bytes(), expected)

    @unittest.skipUnless(shutil.which("sha256sum"), "GNU sha256sum is required")
    def test_gnu_sha256sum_contract_is_supported_explicitly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            result = self.run_assembler(
                root, sha256=SHA256SUM, sha256_kind="sha256sum"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(hashlib.sha256(b"first\nsecond\n").hexdigest(), result.stdout)

    @unittest.skipUnless(shutil.which("sha256sum"), "GNU sha256sum is required")
    def test_gnu_sha256sum_is_portable_without_basename_guessing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            result = self.run_assembler(root, sha256=SHA256SUM, sha256_kind=None)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(hashlib.sha256(b"first\nsecond\n").hexdigest(), result.stdout)

    def test_skill_delegates_to_hardened_assembler_and_names_actual_blocks(self) -> None:
        skill = (REPO / "skills/console-as-code/SKILL.md").read_text(encoding="utf-8")
        for block in (
            "00-boot.md",
            "10-covenants.md",
            "20-mission.md",
            "30-seats.md",
        ):
            self.assertIn(block, skill)
        self.assertNotIn("20-lanes.md", skill)
        self.assertIn("./console/assemble.sh", skill)
        self.assertIn("IDC_CONSOLE_SHA256_KIND", skill)
        self.assertNotIn("blocks=(console/blocks/*.md)", skill)

    def test_ignored_untracked_block_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.fixture(root)
            (root / ".gitignore").write_text("console/blocks/ignored.md\n", encoding="utf-8")
            subprocess.run([GIT, "-C", str(root), "add", ".gitignore"], check=True)
            subprocess.run([GIT, "-C", str(root), "commit", "-qm", "ignore"], check=True)
            (root / "console/blocks/ignored.md").write_text("counterfeit\n", encoding="utf-8")
            result = self.run_assembler(root)
            self.assertEqual(result.returncode, 2)
            self.assertIn("ignored console block", result.stderr)

    def test_skip_worktree_and_assume_unchanged_flags_are_rejected(self) -> None:
        for flag in ("--skip-worktree", "--assume-unchanged"):
            with self.subTest(flag=flag), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                self.fixture(root)
                subprocess.run(
                    [GIT, "-C", str(root), "update-index", flag, "console/blocks/00-first.md"],
                    check=True,
                )
                result = self.run_assembler(root)
                self.assertEqual(result.returncode, 2)
                self.assertIn("skip-worktree or assume-unchanged", result.stderr)


if __name__ == "__main__":
    unittest.main()
