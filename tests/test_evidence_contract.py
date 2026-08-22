from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
RELEASE = "26b9285c1fe11a3ef875a34ff30faa0275eddf24"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class EvidenceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="idc-evidence-test-")
        self.root = Path(self.temporary.name)
        self.roster = self.root / "roster.md"
        self.fixture = self.root / "fixture.txt"
        self.output = self.root / "output.txt"
        self.roster.write_text("| K3-203-001 | preserved finding |\n", encoding="utf-8")
        self.fixture.write_text("malicious input fixture\n", encoding="utf-8")
        self.output.write_text("BLOCK expected=2 observed=2\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self) -> dict[str, object]:
        fixture_digest = digest(self.fixture)
        return {
            "schema": "idc.security-evidence/v1",
            "releaseRevision": RELEASE,
            "sourceRoster": {"path": "roster.md", "sha256": digest(self.roster)},
            "expectedFindingIds": ["K3-203-001"],
            "findings": [
                {
                    "id": "K3-203-001",
                    "title": "Preserved test finding",
                    "sourceLocations": [
                        {
                            "revision": RELEASE,
                            "path": "README.md",
                            "startLine": 1,
                            "endLine": 1,
                        }
                    ],
                    "fixture": {"path": "fixture.txt", "sha256": fixture_digest},
                    "execution": {
                        "command": "python3 -B scripts/validate_evidence.py evidence.json",
                        "expectedExit": 2,
                        "observedExit": 2,
                        "outputPath": "output.txt",
                        "outputSha256": digest(self.output),
                        "fixtureSha256": fixture_digest,
                    },
                    "discriminator": {
                        "description": "The named input is blocked with the expected exit.",
                        "passed": True,
                    },
                    "disposition": {
                        "status": "confirmed",
                        "rationale": "The fixture and captured output reproduce the finding.",
                    },
                }
            ],
        }

    def run_gate(self, payload: dict[str, object]) -> subprocess.CompletedProcess[str]:
        package = self.root / "evidence.json"
        package.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [
                "python3",
                str(REPO / "scripts/validate_evidence.py"),
                str(package),
                "--repo",
                str(REPO),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_complete_bound_record_passes(self) -> None:
        process = self.run_gate(self.payload())
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("records=1 roster=1", process.stdout)

    def test_missing_source_path_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["sourceLocations"][0]["path"] = "missing/file.py"
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("cannot resolve", process.stderr)

    def test_out_of_range_source_line_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["sourceLocations"][0]["endLine"] = 1000000
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("exceeds", process.stderr)

    def test_fixture_digest_mismatch_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["fixture"]["sha256"] = "0" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("fixture.sha256 mismatch", process.stderr)

    def test_output_digest_mismatch_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["execution"]["outputSha256"] = "f" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("outputSha256 mismatch", process.stderr)

    def test_output_must_bind_same_fixture_digest(self) -> None:
        payload = self.payload()
        payload["findings"][0]["execution"]["fixtureSha256"] = "a" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("does not bind", process.stderr)

    def test_absent_command_script_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["execution"]["command"] = "python3 scripts/absent.py"
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("absent script", process.stderr)

    def test_confirmed_without_passing_discriminator_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["discriminator"]["passed"] = False
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("without a passing discriminator", process.stderr)

    def test_roster_ids_cannot_be_silently_omitted(self) -> None:
        payload = self.payload()
        self.roster.write_text(
            "| K3-203-001 | first |\n| K3-203-002 | second |\n", encoding="utf-8"
        )
        payload["sourceRoster"]["sha256"] = digest(self.roster)
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("does not equal", process.stderr)


if __name__ == "__main__":
    unittest.main()
