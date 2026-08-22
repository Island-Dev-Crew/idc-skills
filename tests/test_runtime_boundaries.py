from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts import verify_runtime_requirements as runtime
from scripts import skill_integrity
from scripts import verify_platform_evidence as platform_evidence


REPO = Path(__file__).resolve().parents[1]


class RuntimeBoundaryTests(unittest.TestCase):
    def test_pinned_ssh_keygen_requires_absolute_exact_digest(self) -> None:
        tool = Path(shutil.which("ssh-keygen") or "").resolve(strict=True)
        digest = skill_integrity.sha256_bytes(tool.read_bytes())
        self.assertEqual(
            skill_integrity._validate_pinned_ssh_keygen(tool, digest, REPO), tool
        )
        with self.assertRaisesRegex(skill_integrity.IntegrityError, "digest differs"):
            skill_integrity._validate_pinned_ssh_keygen(
                tool, "sha256:" + "0" * 64, REPO
            )

    def test_platform_evidence_binds_both_real_platform_records_and_head(self) -> None:
        head = "a" * 40
        record = {
            "status": "passed",
            "runner": "real-host",
            "osVersion": "fixture",
            "filesystem": "APFS",
            "python": "3.12",
            "bash": "3.2",
            "sshKeygen": "OpenSSH fixture",
            "command": "python -B -m unittest",
            "outputSHA256": "sha256:" + "b" * 64,
        }
        value = {
            "schema": "idc-platform-evidence/v1",
            "candidateHead": head,
            "records": [
                {"platform": "macos", **record},
                {"platform": "windows", **record, "filesystem": "NTFS", "bash": "n/a"},
            ],
        }
        platform_evidence.validate(value, head)
        with self.assertRaisesRegex(
            platform_evidence.PlatformEvidenceError, "exact candidate head"
        ):
            platform_evidence.validate(value, "c" * 40)
        value["records"][1]["filesystem"] = "simulated"
        with self.assertRaisesRegex(platform_evidence.PlatformEvidenceError, "NTFS"):
            platform_evidence.validate(value, head)

    def test_runtime_contract_accepts_supported_and_rejects_old_python(self) -> None:
        data = (REPO / "runtime-requirements.json").read_bytes()
        contract = runtime.validate_contract(data, (3, 10, 0))
        self.assertEqual(contract["python"]["minimum"], "3.10")
        with self.assertRaisesRegex(runtime.RuntimeRequirementError, "below the signed minimum"):
            runtime.validate_contract(data, (3, 9, 19))

    def test_runtime_contract_rejects_floor_downgrade_and_unknown_keys(self) -> None:
        value = json.loads((REPO / "runtime-requirements.json").read_text(encoding="utf-8"))
        value["python"]["minimum"] = "3.9"
        with self.assertRaisesRegex(runtime.RuntimeRequirementError, "may not be below"):
            runtime.validate_contract(json.dumps(value).encode("utf-8"), (3, 14, 0))
        value["python"]["minimum"] = "3.10"
        value["unknown"] = True
        with self.assertRaisesRegex(runtime.RuntimeRequirementError, "keys differ"):
            runtime.validate_contract(json.dumps(value).encode("utf-8"), (3, 14, 0))

    @unittest.skipIf(os.name == "nt", "POSIX broken-pipe fixture")
    def test_integrity_hook_block_exit_survives_closed_stderr_pipe(self) -> None:
        script = REPO / "scripts/pretooluse-skill-integrity.py"
        read_fd, write_fd = os.pipe()
        bootstrap = (
            "import runpy,sys;from pathlib import Path;"
            "print('READY',flush=True);"
            "sys.stdin.buffer.read(1);"
            "sys.argv=[sys.argv[1],*sys.argv[2:]];"
            "sys.path.insert(0,str(Path(sys.argv[0]).parent));"
            "runpy.run_path(sys.argv[0],run_name='__main__')"
        )
        process = subprocess.Popen(
            [
                sys.executable,
                "-I",
                "-B",
                "-c",
                bootstrap,
                str(script),
                "--repo-root",
                str(REPO),
                "--installed-skills",
                str(REPO / "skills"),
                "--skill",
                "short",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=write_fd,
            text=True,
        )
        try:
            self.assertEqual(process.stdout.readline(), "READY\n")
            os.close(read_fd)
            process.stdin.write("x")
            process.stdin.close()
            process.wait(timeout=10)
        finally:
            if process.stdout is not None:
                process.stdout.close()
            os.close(write_fd)
        self.assertEqual(process.returncode, 2)


if __name__ == "__main__":
    unittest.main()
