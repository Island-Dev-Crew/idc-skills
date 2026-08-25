from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import verify_release_reviews as reviews


GIT = Path(shutil.which("git") or "").resolve()
GIT_SHA256 = "sha256:" + hashlib.sha256(GIT.read_bytes()).hexdigest()
SSH_KEYGEN = Path(shutil.which("ssh-keygen") or "").resolve()
SSH_KEYGEN_SHA256 = "sha256:" + hashlib.sha256(SSH_KEYGEN.read_bytes()).hexdigest()


class ReleaseReviewTests(unittest.TestCase):
    @staticmethod
    def verify_fixture(path: Path, repo: Path, authority_args: dict[str, object]):
        return reviews.verify(
            path,
            repo,
            GIT,
            GIT_SHA256,
            authorities_path=authority_args["path"],
            authorities_sha256=authority_args["sha256"],
            ssh_keygen=SSH_KEYGEN,
            ssh_keygen_sha256=SSH_KEYGEN_SHA256,
        )

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
        packet_artifacts: dict[str, bytes] = {}
        for lane in reviews.REQUIRED_LANES:
            packet_artifacts[f"lanes/{lane}.json"] = (
                json.dumps({"lane": lane, "status": "complete"}, sort_keys=True) + "\n"
            ).encode("utf-8")
        for finding in reviews.REQUIRED_RECONCILIATIONS:
            packet_artifacts[f"reconciliations/{finding}.json"] = (
                json.dumps(
                    {"disposition": "fixed", "finding": finding}, sort_keys=True
                )
                + "\n"
            ).encode("utf-8")
        packet_index = {
            "schema": "idc-review-evidence-packet/v2",
            "candidate": candidate,
            "generatedAt": "2026-08-23T00:00:00Z",
            "coverage": {
                "lanes": list(reviews.REQUIRED_LANES),
                "reconciliations": list(reviews.REQUIRED_RECONCILIATIONS),
            },
            "artifacts": [
                {
                    "path": name,
                    "sha256": "sha256:" + hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                }
                for name, content in sorted(packet_artifacts.items())
            ],
        }
        with zipfile.ZipFile(packet_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in sorted(packet_artifacts.items()):
                archive.writestr(name, content)
            archive.writestr("evidence-index.json", json.dumps(packet_index, sort_keys=True))
        packet_data = packet_path.read_bytes()
        packet = {
            "path": str(packet_path),
            "sha256": "sha256:" + hashlib.sha256(packet_data).hexdigest(),
            "size": len(packet_data),
        }
        items = []
        authorities: dict[str, object] = {}
        for kind, family, model in (
            ("cross-family", "anthropic", "Claude Fable 5"),
            ("kimi-k3", "moonshot", "Kimi K3 swarm"),
        ):
            reviewer = {"family": family, "model": model, "name": model}
            findings = {"blockers": 0, "critical": 0, "high": 0, "low": 1, "medium": 0}
            reviewed_at = "2026-08-23T00:00:00Z"
            coverage = {
                "lanes": [
                    {
                        "evidence": [f"lanes/{lane}.json"],
                        "id": lane,
                        "status": "complete",
                    }
                    for lane in reviews.REQUIRED_LANES
                ],
                "reconciliations": [
                    {
                        "disposition": "fixed",
                        "evidence": [f"reconciliations/{finding}.json"],
                        "id": finding,
                        "rationale": "fixture replay and exact-head review closed this finding",
                    }
                    for finding in reviews.REQUIRED_RECONCILIATIONS
                ],
            }
            receipt_path = external / f"{kind}.json"
            receipt_path.write_text(
                json.dumps(
                    {
                        "schema": reviews.RECEIPT_SCHEMA,
                        "candidate": candidate,
                        "coverage": coverage,
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
            private_key = external / f"{kind}.authority"
            subprocess.run(
                [str(SSH_KEYGEN), "-q", "-t", "ed25519", "-N", "", "-f", str(private_key)],
                check=True,
            )
            public = " ".join(
                Path(str(private_key) + ".pub").read_text(encoding="utf-8").split()[:2]
            )
            principal = f"idc-review-{kind}"
            allowed = external / f"{kind}.allowed-signers"
            allowed.write_text(f"{principal} {public}\n", encoding="utf-8")
            subprocess.run(
                [
                    str(SSH_KEYGEN),
                    "-Y",
                    "sign",
                    "-f",
                    str(private_key),
                    "-n",
                    reviews.RECEIPT_NAMESPACE,
                    str(receipt_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            data = receipt_path.read_bytes()
            signature_path = Path(str(receipt_path) + ".sig")
            signature_data = signature_path.read_bytes()
            allowed_data = allowed.read_bytes()
            authorities[kind] = {
                "allowedSigners": {
                    "path": str(allowed),
                    "sha256": "sha256:" + hashlib.sha256(allowed_data).hexdigest(),
                    "size": len(allowed_data),
                },
                "family": family,
                "principal": principal,
            }
            items.append(
                {
                    "candidate": candidate,
                    "coverage": coverage,
                    "findings": findings,
                    "kind": kind,
                    "receipt": {
                        "path": str(receipt_path),
                        "sha256": "sha256:" + hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                        "signature": {
                            "path": str(signature_path),
                            "sha256": "sha256:" + hashlib.sha256(signature_data).hexdigest(),
                            "size": len(signature_data),
                        },
                    },
                    "reviewedAt": reviewed_at,
                    "reviewer": reviewer,
                    "verdict": "approve",
                    "voidOnMove": True,
                }
            )
        record = {"schema": reviews.SCHEMA, "candidate": candidate, "evidencePacket": packet, "reviews": items}
        authorities_path = external / "review-authorities.json"
        authorities_data = json.dumps(
            {"schema": "idc-review-authorities/v1", "authorities": authorities},
            sort_keys=True,
        ).encode("utf-8")
        authorities_path.write_bytes(authorities_data)
        path = external / "reviews.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return repo, external, record, path, {
            "path": authorities_path,
            "sha256": "sha256:" + hashlib.sha256(authorities_data).hexdigest(),
        }

    def test_two_external_exact_head_reviews_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, _, path, authority_args = self.fixture(Path(temporary))
            report = self.verify_fixture(path, repo, authority_args)
            self.assertTrue(report["pass"])
            self.assertEqual(report["reviews"], ["cross-family", "kimi-k3"])
            self.assertEqual(report["lanes"], 11)
            self.assertEqual(report["reconciliations"], 31)

    def test_same_family_and_receipt_tamper_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path, authority_args = self.fixture(Path(temporary))
            same_family = copy.deepcopy(record)
            same_family["reviews"][0]["reviewer"]["family"] = "openai"
            path.write_text(json.dumps(same_family), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "not cross-family"):
                self.verify_fixture(path, repo, authority_args)

            path.write_text(json.dumps(record), encoding="utf-8")
            (external / "kimi-k3.json").write_text("changed\n", encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "receipt bytes differ"):
                self.verify_fixture(path, repo, authority_args)

    def test_irrelevant_receipt_and_shared_family_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path, authority_args = self.fixture(Path(temporary))
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
            with self.assertRaisesRegex(reviews.ReviewError, "authority signature is invalid"):
                self.verify_fixture(path, repo, authority_args)

            second_root = Path(temporary) / "second"
            second_root.mkdir()
            repo, _, record, path, authority_args = self.fixture(second_root)
            record["reviews"][1]["reviewer"]["family"] = "anthropic"
            path.write_text(json.dumps(record), encoding="utf-8")
            authorities_path = authority_args["path"]
            authorities = json.loads(authorities_path.read_text(encoding="utf-8"))
            authorities["authorities"]["kimi-k3"]["family"] = "anthropic"
            authorities_data = json.dumps(authorities, sort_keys=True).encode("utf-8")
            authorities_path.write_bytes(authorities_data)
            authority_args["sha256"] = "sha256:" + hashlib.sha256(authorities_data).hexdigest()
            with self.assertRaisesRegex(reviews.ReviewError, "families must be distinct"):
                self.verify_fixture(path, repo, authority_args)

    def test_record_inside_candidate_and_moved_head_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, record, path, authority_args = self.fixture(Path(temporary))
            inside = repo / "reviews.json"
            inside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "outside"):
                self.verify_fixture(inside, repo, authority_args)

            (repo / "later.txt").write_text("later\n", encoding="utf-8")
            subprocess.run([str(GIT), "-C", str(repo), "add", "later.txt"], check=True)
            subprocess.run([str(GIT), "-C", str(repo), "commit", "-qm", "later"], check=True)
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "moved"):
                self.verify_fixture(path, repo, authority_args)

    def test_evidence_packet_is_parsed_and_ignored_payloads_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path, authority_args = self.fixture(Path(temporary))
            packet_path = Path(record["evidencePacket"]["path"])
            packet_path.write_bytes(b"not a zip, but freshly rehashed\n")
            packet_data = packet_path.read_bytes()
            record["evidencePacket"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(packet_data).hexdigest(),
                    "size": len(packet_data),
                }
            )
            for review in record["reviews"]:
                review["receipt"]["sha256"] = review["receipt"]["sha256"]
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "evidence packet ZIP"):
                self.verify_fixture(path, repo, authority_args)

        with tempfile.TemporaryDirectory() as temporary:
            repo, _, _, path, authority_args = self.fixture(Path(temporary))
            (repo / ".git" / "info" / "exclude").write_text("hidden.bin\n", encoding="utf-8")
            (repo / "hidden.bin").write_bytes(b"ignored evidence-hiding payload\n")
            with self.assertRaisesRegex(reviews.ReviewError, "ignored payload"):
                self.verify_fixture(path, repo, authority_args)

    def test_incomplete_lane_or_reconciliation_coverage_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, record, path, authority_args = self.fixture(Path(temporary))
            incomplete = copy.deepcopy(record)
            incomplete["reviews"][0]["coverage"]["lanes"].pop()
            path.write_text(json.dumps(incomplete), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "all 11 K3-204 lanes"):
                self.verify_fixture(path, repo, authority_args)

            unindexed = copy.deepcopy(record)
            unindexed["reviews"][0]["coverage"]["reconciliations"][0][
                "evidence"
            ] = ["reconciliations/not-indexed.json"]
            path.write_text(json.dumps(unindexed), encoding="utf-8")
            with self.assertRaisesRegex(reviews.ReviewError, "evidence is not indexed"):
                self.verify_fixture(path, repo, authority_args)

    def test_rehashed_review_receipt_without_authority_signature_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path, authority_args = self.fixture(Path(temporary))
            receipt_path = external / "cross-family.json"
            payload = json.loads(receipt_path.read_text(encoding="utf-8"))
            payload["limitations"] = ["forged after the reviewer signed"]
            receipt_path.write_text(json.dumps(payload), encoding="utf-8")
            receipt_data = receipt_path.read_bytes()
            record["reviews"][0]["receipt"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(receipt_data).hexdigest(),
                    "size": len(receipt_data),
                }
            )
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(reviews.ReviewError, "authority signature is invalid"):
                self.verify_fixture(path, repo, authority_args)

    def test_review_authorities_must_not_share_a_signing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, external, record, path, authority_args = self.fixture(Path(temporary))
            shared_private = external / "cross-family.authority"
            shared_allowed = external / "cross-family.allowed-signers"
            kimi_allowed = external / "kimi-k3.allowed-signers"
            shared_public = " ".join(
                Path(str(shared_private) + ".pub").read_text(encoding="utf-8").split()[:2]
            )
            kimi_allowed.write_text(
                f"idc-review-kimi-k3 {shared_public}\n", encoding="utf-8"
            )
            kimi_receipt = external / "kimi-k3.json"
            kimi_signature = Path(str(kimi_receipt) + ".sig")
            kimi_signature.unlink()
            subprocess.run(
                [
                    str(SSH_KEYGEN),
                    "-Y",
                    "sign",
                    "-f",
                    str(shared_private),
                    "-n",
                    reviews.RECEIPT_NAMESPACE,
                    str(kimi_receipt),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            signature_data = kimi_signature.read_bytes()
            record["reviews"][1]["receipt"]["signature"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(signature_data).hexdigest(),
                    "size": len(signature_data),
                }
            )
            path.write_text(json.dumps(record), encoding="utf-8")
            authorities = json.loads(authority_args["path"].read_text(encoding="utf-8"))
            allowed_data = kimi_allowed.read_bytes()
            authorities["authorities"]["kimi-k3"]["allowedSigners"].update(
                {
                    "path": str(kimi_allowed),
                    "sha256": "sha256:" + hashlib.sha256(allowed_data).hexdigest(),
                    "size": len(allowed_data),
                }
            )
            authorities_data = json.dumps(authorities, sort_keys=True).encode("utf-8")
            authority_args["path"].write_bytes(authorities_data)
            authority_args["sha256"] = "sha256:" + hashlib.sha256(authorities_data).hexdigest()

            with self.assertRaisesRegex(reviews.ReviewError, "signing keys must be disjoint"):
                self.verify_fixture(path, repo, authority_args)

    def test_candidate_local_git_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, _, path, authority_args = self.fixture(Path(temporary))
            candidate_git = repo / ".git" / "candidate-git"
            shutil.copyfile(GIT, candidate_git)
            candidate_git.chmod(0o755)
            candidate_digest = "sha256:" + hashlib.sha256(candidate_git.read_bytes()).hexdigest()

            with self.assertRaisesRegex(reviews.ReviewError, "Git must remain outside"):
                reviews.verify(
                    path,
                    repo,
                    candidate_git,
                    candidate_digest,
                    authorities_path=authority_args["path"],
                    authorities_sha256=authority_args["sha256"],
                    ssh_keygen=SSH_KEYGEN,
                    ssh_keygen_sha256=SSH_KEYGEN_SHA256,
                )


if __name__ == "__main__":
    unittest.main()
