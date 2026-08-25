from __future__ import annotations

import copy
import hashlib
import io
import json
import os
import subprocess
import tarfile
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
        self.source_bundle = self.root / "source-bundle.tar.gz"
        with tarfile.open(self.source_bundle, "w:gz") as archive:
            archive.add(self.output, arcname="ground-truth/output.txt")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def payload(self) -> dict[str, object]:
        fixture_digest = digest(self.fixture)
        return {
            "schema": "idc.security-evidence/v2",
            "releaseRevision": RELEASE,
            "sourceBundle": {
                "path": "source-bundle.tar.gz",
                "sha256": digest(self.source_bundle),
            },
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
                    "fixture": {
                        "anchor": "candidate-preserved",
                        "path": "fixture.txt",
                        "sha256": fixture_digest,
                    },
                    "capture": {
                        "kind": "preserved-observation",
                        "source": {"type": "local", "path": "output.txt"},
                        "sha256": digest(self.output),
                        "fixtureSha256": fixture_digest,
                    },
                    "semanticBinding": {
                        "description": "The preserved output records the expected block exit.",
                        "assertions": [
                            {"target": "capture", "contains": "observed=2"}
                        ],
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
        return self.run_package(package)

    def run_package(self, package: Path) -> subprocess.CompletedProcess[str]:
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

    def test_repository_ledger_is_deterministic_v2_with_authoritative_captures(self) -> None:
        ledger_path = REPO / "ops/mission/evidence/2.0.4/evidence.json"
        before = ledger_path.read_bytes()
        process = subprocess.run(
            ["python3", "-B", str(REPO / "scripts/build_kimi_evidence.py")],
            cwd=REPO,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertEqual(ledger_path.read_bytes(), before)
        ledger = json.loads(before)
        self.assertEqual(ledger["schema"], "idc.security-evidence/v2")
        self.assertEqual(
            ledger["sourceBundle"]["sha256"],
            "6b471d41a3d7adec021690ceb007e949140ec05061a165674709d6511628e81d",
        )
        records = {record["id"]: record for record in ledger["findings"]}
        self.assertEqual(len(records), 31)
        for record in records.values():
            self.assertNotIn("execution", record)
            self.assertTrue(record["semanticBinding"]["assertions"])
        for finding_id in ("K3-203-012", "K3-203-020", "K3-203-023", "K3-203-029"):
            source = records[finding_id]["capture"]["source"]
            self.assertEqual(source["type"], "bundle-member")
            self.assertTrue(source["member"].endswith(f"/{finding_id}/stdout.txt"))

    def test_tracked_schema_aid_describes_v2_capture_model(self) -> None:
        self.assertFalse(
            (REPO / "ops/mission/evidence/evidence-schema-v1.json").exists()
        )
        schema = json.loads(
            (REPO / "ops/mission/evidence/evidence-schema-v2.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            schema["properties"]["schema"]["const"], "idc.security-evidence/v2"
        )
        finding = schema["$defs"]["finding"]
        self.assertIn("capture", finding["required"])
        self.assertNotIn("execution", finding["properties"])

    def test_duplicate_json_keys_fail_closed(self) -> None:
        package = self.root / "evidence.json"
        encoded = json.dumps(self.payload())
        package.write_text(
            encoded.replace(
                '"schema": "idc.security-evidence/v2"',
                '"schema": "idc.security-evidence/v2", "schema": "idc.security-evidence/v2"',
                1,
            ),
            encoding="utf-8",
        )
        process = self.run_package(package)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("duplicate JSON key", process.stderr)

    def test_oversized_package_fails_before_parsing(self) -> None:
        package = self.root / "evidence.json"
        package.write_bytes(b'{"padding":"' + b"x" * (9 * 1024 * 1024) + b'"}')
        process = self.run_package(package)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("size limit", process.stderr)

    def test_finding_ids_are_exact_ascii(self) -> None:
        payload = self.payload()
        confusable = "K3-203-٠٠١"
        self.roster.write_text(f"| {confusable} | confusable |\n", encoding="utf-8")
        payload["sourceRoster"]["sha256"] = digest(self.roster)
        payload["expectedFindingIds"] = [confusable]
        payload["findings"][0]["id"] = confusable
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("ASCII", process.stderr)

    @unittest.skipIf(os.name == "nt", "symlink fixture requires POSIX semantics")
    def test_intermediate_symlink_in_evidence_path_is_rejected(self) -> None:
        payload = self.payload()
        real = self.root / "real"
        real.mkdir()
        nested = real / "fixture.txt"
        nested.write_text("malicious input fixture\n", encoding="utf-8")
        (self.root / "alias").symlink_to(real, target_is_directory=True)
        payload["findings"][0]["fixture"]["path"] = "alias/fixture.txt"
        payload["findings"][0]["fixture"]["sha256"] = digest(nested)
        payload["findings"][0]["capture"]["fixtureSha256"] = digest(nested)
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("symlink ancestor", process.stderr)

    def test_source_bundle_digest_is_verified(self) -> None:
        payload = self.payload()
        payload["sourceBundle"]["sha256"] = "0" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("sourceBundle.sha256 mismatch", process.stderr)

    def test_unsafe_source_bundle_member_is_rejected(self) -> None:
        with tarfile.open(self.source_bundle, "w:gz") as archive:
            info = tarfile.TarInfo("../escape.txt")
            body = b"escape\n"
            info.size = len(body)
            archive.addfile(info, io.BytesIO(body))
        payload = self.payload()
        payload["sourceBundle"]["sha256"] = digest(self.source_bundle)
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("unsafe source bundle member", process.stderr)

    def test_bundle_member_capture_passes(self) -> None:
        payload = self.payload()
        payload["findings"][0]["capture"]["source"] = {
            "type": "bundle-member",
            "member": "ground-truth/output.txt",
        }
        process = self.run_gate(payload)
        self.assertEqual(process.returncode, 0, process.stderr)

    def test_fixture_and_capture_schemas_are_exact(self) -> None:
        for field in ("fixture", "capture"):
            with self.subTest(field=field):
                payload = self.payload()
                payload["findings"][0][field]["unexpected"] = True
                process = self.run_gate(payload)
                self.assertNotEqual(process.returncode, 0)
                self.assertIn(f"{field} has unexpected keys", process.stderr)

    def test_execution_claims_are_not_part_of_preserved_capture_schema(self) -> None:
        payload = self.payload()
        payload["findings"][0]["execution"] = {
            "command": "true",
            "observedExit": 0,
        }
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("unexpected keys", process.stderr)

    def test_semantic_target_must_be_utf8(self) -> None:
        payload = self.payload()
        self.output.write_bytes(b"observed=2\xff")
        payload["findings"][0]["capture"]["sha256"] = digest(self.output)
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("UTF-8", process.stderr)

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
        payload["findings"][0]["capture"]["sha256"] = "f" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("outputSha256 mismatch", process.stderr)

    def test_output_must_bind_same_fixture_digest(self) -> None:
        payload = self.payload()
        payload["findings"][0]["capture"]["fixtureSha256"] = "a" * 64
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("does not bind", process.stderr)

    def test_source_revision_must_equal_the_historical_release(self) -> None:
        payload = self.payload()
        payload["findings"][0]["sourceLocations"][0]["revision"] = "0" * 40
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("must equal releaseRevision", process.stderr)

    def test_semantically_irrelevant_capture_fails(self) -> None:
        payload = self.payload()
        payload["findings"][0]["semanticBinding"]["assertions"][0]["contains"] = (
            "not present in the capture"
        )
        process = self.run_gate(payload)
        self.assertNotEqual(process.returncode, 0)
        self.assertIn("semantic assertion", process.stderr)

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
