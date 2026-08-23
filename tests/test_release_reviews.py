from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import verify_release_reviews as reviews


GIT = Path(shutil.which("git") or "").resolve()
GIT_SHA256 = "sha256:" + hashlib.sha256(GIT.read_bytes()).hexdigest()


class ReleaseReviewTests(unittest.TestCase):
    def fixture(self, root: Path):
        repo = root / "repo"
        external = root / "external"
        repo.mkdir()
        external.mkdir()
        subprocess.run([str(GIT), "-C", str(repo), "init", "-q"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "config", "core.autocrlf", "false"], check=True)
        (repo / "subject.txt").write_text("base\n", encoding="utf-8")
        subprocess.run([str(GIT), "-C", str(repo), "add", "subject.txt"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "commit", "-qm", "base"], check=True)
        base = subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        (repo / "subject.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run([str(GIT), "-C", str(repo), "commit", "-qam", "candidate"], check=True)
        head = subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
        candidate = {"base": base, "commit": head, "tree": tree}
        packet_path = external / "evidence-packet.zip"
        packet_path.write_bytes(b"exact-head evidence packet\n")
        packet_data = packet_path.read_bytes()
        packet = {
            "path": str(packet_path),
            "sha256": "sha256:" + hashlib.sha256(packet_data).hexdigest(),
            "size": len(packet_data),
        }
        items = []
        for kind, family, model in (
            ("cross-family", "anthropic", "Claude Fable 5"),
            ("kimi-k3", "moonshot", "Kimi K3 swarm"),
        ):
            reviewer = {"family": family, "model": model, "name": model}
            findings = {"blockers": 0, "critical": 0, "high": 0, "low": 1, "medium": 0}
            reviewed_at = "2026-08-23T00:00:00Z"
            receipt_path = external / f"{kind}.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "schema": reviews.RECEIPT_SCHEMA,
                        "candidate": candidate,
                        "evidencePacketSHA256": packet["sha256"],
                        "findings": findings,
                        "kind": kind,
                        "limitations": ["fixture review"],
                        "reviewedAt": reviewed_at,
                        "reviewer": reviewer,
                        "verdict": "approve",
                        "voidOnMove": True,
                    }
                ),
                encoding="utf-8",
            )
            data = receipt_path.read_bytes()
            items.append(
                {
                    "candidate": candidate,
                    "findings": findings,
                    "kind": kind,
                    "receipt": {"path": str(receipt_path), "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)},
                    "reviewedAt": reviewed_at,
                    "reviewer": reviewer,
                    "verdict": "approve",
                    "voidOnMove": True,
                }
            )
        record = {"schema": reviews.SCHEMA, "candidate": candidate, "evidencePacket": packet, "reviews": items}
        path = external / "reviews.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return repo, external, record, path

    def test_two_external_exact_head_reviews_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, _, path = self.fixture(Path(temporary))
            report = reviews.verify(path, repo, GIT, GIT_SHA256)
            self.assertTrue(report["pass"])
            self.assertEqual(report["reviews"], ["cross-family", "kimi-k3"])

    def test_same_family_and_receipt_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path = self.fixture(Path(temporary))
            same_family = copy.deepcopy(record)
            same_family["reviews"][0]["reviewer"]["family"] = "openai"
            path.write_text(json.dumps(same_family), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "not cross-family"):
                reviews.verify(path, repo, GIT, GIT_SHA256)

            path.write_text(json.dumps(record), encoding="utf-8")
            (external / "kimi-k3.json").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "receipt bytes differ"):
                reviews.verify(path, repo, GIT, GIT_SHA256)

    def test_irrelevant_receipt_and_shared_family_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path = self.fixture(Path(temporary))
            forged = copy.deepcopy(record)
            receipt_path = external / "cross-family.json"
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            payload["candidate"]["tree"] = "0" * 40
            receipt_path.write_text(json.dumps(payload), encoding="utf-8")
            data = receipt_path.read_bytes()
            forged["reviews"][0]["receipt"].update(
                {"sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)}
            )
            path.write_text(json.dumps(forged), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "receipt candidate differs"):
                reviews.verify(path, repo, GIT, GIT_SHA256)

            second_root = Path(temporary) / "second"
            second_root.mkdir()
            repo, _, record, path = self.fixture(second_root)
            record["reviews"][1]["reviewer"]["family"] = "anthropic"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "families must be distinct"):
                reviews.verify(path, repo, GIT, GIT_SHA256)

    def test_record_inside_candidate_and_moved_head_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, record, path = self.fixture(Path(temporary))
            inside = repo / "reviews.json"
            inside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "outside"):
                reviews.verify(inside, repo, GIT, GIT_SHA256)

            (repo / "later.txt").write_text("later\n", encoding="utf-8")
            subprocess.run([str(GIT), "-C", str(repo), "add", "later.txt"], check=True)
            subprocess.run([str(GIT), "-C", str(repo), "commit", "-qm", "later"], check=True)
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "moved"):
                reviews.verify(path, repo, GIT, GIT_SHA256)


if __name__ == "__main__":
    unittest.main()
