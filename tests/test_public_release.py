from __future__ import annotations

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import verify_public_release as publication


GIT = Path(shutil.which("git") or "").resolve()
GIT_SHA256 = "sha256:" + hashlib.sha256(GIT.read_bytes()).hexdigest()


class PublicReleaseTests(unittest.TestCase):
    def fixture(self, root: Path):
        repo = root / "repo"
        external = root / "external"
        repo.mkdir()
        external.mkdir()
        subprocess.run([str(GIT), "-C", str(repo), "init", "-q"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "config", "user.name", "Fixture"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "config", "user.email", "fixture@example.invalid"], check=True)
        (repo / "tracked.txt").write_text("release\n", encoding="utf-8")
        subprocess.run([str(GIT), "-C", str(repo), "add", "tracked.txt"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "commit", "-qm", "release"], check=True)
        subprocess.run([str(GIT), "-C", str(repo), "tag", "-a", "-m", "release", "2.0.4"], check=True)
        commit = subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
        candidate = {"commit": commit, "tag": "2.0.4", "tree": tree}
        assets = {
            name: {"sha256": "sha256:" + hashlib.sha256(name.encode()).hexdigest(), "size": len(name)}
            for name in ("archive", "freshnessIndex", "installInventory", "manifest", "registry")
        }
        root_digest = "sha256:" + "a" * 64
        signed = {
            "_type": "release",
            "artifacts": assets,
            "expires": "2027-01-01T00:00:00Z",
            "git": candidate,
            "release": "2.0.4",
            "releaseSequence": 2,
            "rootVersion": 1,
            "schema": "idc-skills-release-statement/v1",
        }
        statement = external / "release-statement.json"
        statement.write_text(json.dumps({"signatures": [], "signed": signed}), encoding="utf-8")

        def make_receipt(name: str, content: str):
            path = external / name
            path.write_text(content, encoding="utf-8")
            data = path.read_bytes()
            return {"path": str(path), "sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)}

        def make_json_receipt(name: str, value: dict):
            return make_receipt(name, json.dumps(value))

        statement_record = make_receipt("statement-copy.json", statement.read_text(encoding="utf-8"))
        record = {
            "schema": publication.SCHEMA,
            "candidate": candidate,
            "root": {"sha256": root_digest, "version": 1},
            "threshold": {
                "releaseStatement": statement_record,
                "verificationReceipt": make_json_receipt(
                    "threshold.json",
                    {
                        "schema": "idc-threshold-verification-receipt/v1",
                        "candidate": candidate,
                        "externalTrustVerified": True,
                        "root": {"sha256": root_digest, "version": 1},
                        "statementSHA256": statement_record["sha256"],
                        "verifiedAt": "2026-08-23T00:00:00Z",
                    },
                ),
            },
            "github": {
                "assets": [{"name": name, **value} for name, value in assets.items()],
                "releaseURL": "https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.4",
                "repository": "Island-Dev-Crew/idc-skills",
                "releaseReceipt": make_json_receipt(
                    "github.json",
                    {
                        "schema": "idc-github-release-receipt/v1",
                        "assets": [{"name": name, **value} for name, value in assets.items()],
                        "candidate": candidate,
                        "observedAt": "2026-08-23T00:00:00Z",
                        "releaseURL": "https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.4",
                        "repository": "Island-Dev-Crew/idc-skills",
                    },
                ),
                "tagVerificationReceipt": make_json_receipt(
                    "tag.json",
                    {
                        "schema": "idc-tag-verification-receipt/v1",
                        "candidate": candidate,
                        "observedAt": "2026-08-23T00:00:00Z",
                        "tagObject": subprocess.check_output([str(GIT), "-C", str(repo), "rev-parse", "2.0.4"], text=True).strip(),
                        "verified": True,
                    },
                ),
            },
            "site": {
                "administrationReceipt": make_json_receipt(
                    "site-admin.json",
                    {
                        "schema": "idc-site-administration-receipt/v1",
                        "attestedAt": "2026-08-23T00:00:00Z",
                        "githubAdministration": "release-team",
                        "independent": True,
                        "siteAdministration": "web-trust-team",
                    },
                ),
                "landingReceipt": make_receipt(
                    "site-landing.html",
                    "\n".join(("2.0.4", commit, tree, root_digest, "https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.4")),
                ),
                "landingURL": "https://islanddevcrew.com/skills/forge",
                "rootDigestReceipt": make_receipt("site-root.txt", root_digest + "\n"),
                "rootDigestURL": "https://islanddevcrew.com/.well-known/idc-skills-root.txt",
                "rootSHA256": root_digest,
            },
            "secondChannel": {
                "kind": "dnssec",
                "locator": "_idc-skills-root.islanddevcrew.com TXT",
                "receipt": make_json_receipt(
                    "dnssec.json",
                    {
                        "schema": "idc-second-channel-receipt/v1",
                        "kind": "dnssec",
                        "locator": "_idc-skills-root.islanddevcrew.com TXT",
                        "observedAt": "2026-08-23T00:00:00Z",
                        "rootSHA256": root_digest,
                        "verified": True,
                    },
                ),
                "rootSHA256": root_digest,
            },
        }
        path = external / "publication.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return repo, record, path

    def test_matching_publication_channels_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path = self.fixture(Path(temporary))
            report = publication.verify(path, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")
            self.assertTrue(report["pass"])
            self.assertEqual(report["assets"], 5)

    def test_channel_or_asset_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path = self.fixture(Path(temporary))
            mismatch = copy.deepcopy(record)
            mismatch["secondChannel"]["rootSHA256"] = "sha256:" + "b" * 64
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "second trust channel differs"):
                publication.verify(path, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")

            mismatch = copy.deepcopy(record)
            mismatch["github"]["assets"][0]["size"] += 1
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "assets differ"):
                publication.verify(path, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")

    def test_publication_record_inside_candidate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path = self.fixture(Path(temporary))
            inside = repo / "publication.json"
            inside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "outside"):
                publication.verify(inside, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")

    def test_irrelevant_receipt_and_dirty_checkout_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path = self.fixture(Path(temporary))
            root_receipt = Path(record["site"]["rootDigestReceipt"]["path"])
            root_receipt.write_text("sha256:" + "b" * 64 + "\n", encoding="utf-8")
            data = root_receipt.read_bytes()
            record["site"]["rootDigestReceipt"].update(
                {"sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)}
            )
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "site root digest receipt differs"):
                publication.verify(path, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")

        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path = self.fixture(Path(temporary))
            (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "dirty"):
                publication.verify(path, repo, GIT, GIT_SHA256, "Island-Dev-Crew/idc-skills", "islanddevcrew.com")


if __name__ == "__main__":
    unittest.main()
