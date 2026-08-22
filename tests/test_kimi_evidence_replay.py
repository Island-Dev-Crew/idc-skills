from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
REPLAY = REPO / "scripts/replay_kimi_evidence.py"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class KimiEvidenceReplayTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="idc-kimi-replay-")
        self.root = Path(self.temporary.name)
        self.fixture = self.root / "fixture.txt"
        self.output = self.root / "output.txt"
        self.fixture.write_text("preserved adversarial fixture\n", encoding="utf-8")
        self.output.write_text("preserved observed output\n", encoding="utf-8")
        fixture_sha = digest(self.fixture)
        self.package = {
            "findings": [
                {
                    "id": "K3-203-TEST",
                    "fixture": {"path": "fixture.txt", "sha256": fixture_sha},
                    "execution": {
                        "fixtureSha256": fixture_sha,
                        "outputPath": "output.txt",
                        "outputSha256": digest(self.output),
                        "observedExit": 0,
                    },
                }
            ]
        }

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_replay(self) -> subprocess.CompletedProcess[bytes]:
        evidence = self.root / "evidence.json"
        evidence.write_text(json.dumps(self.package), encoding="utf-8")
        return subprocess.run(
            ["python3", "-B", str(REPLAY), "--id", "K3-203-TEST", "--evidence", str(evidence)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_exact_preserved_bytes_replay(self) -> None:
        process = self.run_replay()
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        self.assertEqual(process.stdout, self.output.read_bytes())

    def test_fixture_tamper_is_rejected(self) -> None:
        self.fixture.write_text("changed fixture\n", encoding="utf-8")
        process = self.run_replay()
        self.assertEqual(process.returncode, 2)
        self.assertIn(b"fixture digest differs", process.stderr)

    def test_output_tamper_is_rejected(self) -> None:
        self.output.write_text("changed output\n", encoding="utf-8")
        process = self.run_replay()
        self.assertEqual(process.returncode, 2)
        self.assertIn(b"captured-output digest differs", process.stderr)

    def test_path_escape_is_rejected(self) -> None:
        self.package["findings"][0]["fixture"]["path"] = "../fixture.txt"
        process = self.run_replay()
        self.assertEqual(process.returncode, 2)
        self.assertIn(b"unsafe evidence path", process.stderr)


if __name__ == "__main__":
    unittest.main()
