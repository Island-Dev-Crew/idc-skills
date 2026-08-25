from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "ci_tool_pins.py"


class CiToolPinTests(unittest.TestCase):
    def test_provisioner_exports_the_resolved_ssh_keygen_path_and_exact_digest(self) -> None:
        ssh_keygen = Path(shutil.which("ssh-keygen") or "").resolve()
        expected_digest = "sha256:" + hashlib.sha256(ssh_keygen.read_bytes()).hexdigest()
        with tempfile.TemporaryDirectory() as temporary:
            github_env = Path(temporary) / "github.env"
            completed = subprocess.run(
                [
                    "python3",
                    "-B",
                    str(SCRIPT),
                    "--github-env",
                    str(github_env),
                    "--ssh-keygen",
                    str(ssh_keygen),
                    "--json",
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            report = json.loads(completed.stdout)
            self.assertEqual(report["path"], str(ssh_keygen))
            self.assertEqual(report["sha256"], expected_digest)
            self.assertEqual(
                github_env.read_text(encoding="utf-8").splitlines(),
                [
                    f"IDC_SKILLS_SSH_KEYGEN={ssh_keygen}",
                    f"IDC_SKILLS_SSH_KEYGEN_SHA256={expected_digest}",
                ],
            )

    def test_workflow_provisions_pins_before_content_reacceptance(self) -> None:
        workflow = (REPO / ".github" / "workflows" / "validate.yml").read_text(
            encoding="utf-8"
        )
        provision = workflow.index("python -B scripts/ci_tool_pins.py")
        reaccept = workflow.index("python -B scripts/reaccept.py")
        self.assertLess(provision, reaccept)


if __name__ == "__main__":
    unittest.main()
