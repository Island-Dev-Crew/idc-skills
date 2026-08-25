from __future__ import annotations

import copy
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import verify_public_release as publication
from scripts import trust_root as trust


GIT = Path(shutil.which("git") or "").resolve()
GIT_SHA256 = "sha256:" + hashlib.sha256(GIT.read_bytes()).hexdigest()
SSH_KEYGEN = Path(shutil.which("ssh-keygen") or "").resolve()
SSH_KEYGEN_SHA256 = "sha256:" + hashlib.sha256(SSH_KEYGEN.read_bytes()).hexdigest()
NOW = dt.datetime(2026, 8, 23, 1, 0, tzinfo=dt.timezone.utc)


class PublicReleaseTests(unittest.TestCase):
    @staticmethod
    def generate_key(path: Path) -> tuple[Path, str, dict[str, object]]:
        subprocess.run(
            [str(SSH_KEYGEN), "-q", "-t", "ed25519", "-N", "", "-f", str(path)],
            check=True,
        )
        public = " ".join(path.with_suffix(".pub").read_text(encoding="utf-8").split()[:2])
        key = {
            "keytype": "ed25519",
            "keyval": {"public": public},
            "scheme": "ssh-ed25519",
        }
        return path, trust.keyid_for(key), key

    @staticmethod
    def sign_envelope(
        root: Path,
        signed: dict[str, object],
        private: Path,
        keyid: str,
        namespace: str,
        label: str,
    ) -> dict[str, object]:
        payload = root / f"{label}.payload.json"
        payload.write_bytes(trust.canonical_json(signed))
        subprocess.run(
            [str(SSH_KEYGEN), "-Y", "sign", "-f", str(private), "-n", namespace, str(payload)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        signature = Path(str(payload) + ".sig").read_text(encoding="utf-8")
        return {"signatures": [{"keyid": keyid, "sig": signature}], "signed": signed}

    @staticmethod
    def verify_fixture(path: Path, repo: Path, trust_args: dict[str, object]):
        return publication.verify(
            path,
            repo,
            GIT,
            GIT_SHA256,
            "Island-Dev-Crew/idc-skills",
            "islanddevcrew.com",
            trusted_root=trust_args["trusted_root"],
            trusted_root_sha256=trust_args["trusted_root_sha256"],
            ssh_keygen=SSH_KEYGEN,
            ssh_keygen_sha256=SSH_KEYGEN_SHA256,
            observer_authority=trust_args["observer_authority"],
            observer_authority_sha256=trust_args["observer_authority_sha256"],
            now=NOW,
        )

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
        root_private, root_keyid, root_key = self.generate_key(external / "root-key")
        release_private, release_keyid, release_key = self.generate_key(external / "release-key")
        _, _, content_key = self.generate_key(external / "content-key")
        root_signed = {
            "_type": "root",
            "consistentSnapshot": True,
            "expires": "2027-01-01T00:00:00Z",
            "keys": {root_keyid: root_key, release_keyid: release_key},
            "roles": {
                "release": {"keyids": [release_keyid], "threshold": 1},
                "root": {"keyids": [root_keyid], "threshold": 1},
            },
            "schema": trust.ROOT_SCHEMA,
            "specVersion": "1.0",
            "version": 1,
        }
        trusted_root = external / "1.root.json"
        trusted_root.write_bytes(
            trust.canonical_json(
                self.sign_envelope(
                    external, root_signed, root_private, root_keyid, trust.ROOT_NAMESPACE, "root"
                )
            )
        )
        root_digest = trust.sha256_file(trusted_root)
        content_public = external / "content.pub"
        content_public.write_text(
            content_key["keyval"]["public"] + "\n", encoding="utf-8"
        )
        content_allowed = external / "content.allowed"
        content_allowed.write_text(
            "idc-skills " + content_key["keyval"]["public"] + "\n", encoding="utf-8"
        )
        signed = {
            "_type": "release",
            "artifacts": assets,
            "contentSigning": trust.content_signing_record(content_public, content_allowed),
            "expires": "2027-01-01T00:00:00Z",
            "git": candidate,
            "release": "2.0.4",
            "releaseSequence": 2,
            "rootVersion": 1,
            "schema": "idc-skills-release-statement/v1",
        }
        statement = external / "release-statement.json"
        statement.write_bytes(
            trust.canonical_json(
                self.sign_envelope(
                    external,
                    signed,
                    release_private,
                    release_keyid,
                    trust.RELEASE_NAMESPACE,
                    "release",
                )
            )
        )

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
                "landingReceipt": make_json_receipt(
                    "site-landing.json",
                    {
                        "schema": "idc-site-landing-receipt/v2",
                        "candidate": candidate,
                        "landingURL": "https://islanddevcrew.com/skills/forge",
                        "observedAt": "2026-08-23T00:00:00Z",
                        "releaseURL": "https://github.com/Island-Dev-Crew/idc-skills/releases/tag/2.0.4",
                        "root": {"sha256": root_digest, "version": 1},
                    },
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
        observer_private, _, observer_key = self.generate_key(
            external / "publication-observer-key"
        )
        observer_principal = "idc-publication-observer"
        observer_allowed = external / "publication-observer.allowed-signers"
        observer_allowed.write_text(
            f"{observer_principal} {observer_key['keyval']['public']}\n",
            encoding="utf-8",
        )
        observer_allowed_data = observer_allowed.read_bytes()
        observer_authority = external / "publication-observer-authority.json"
        observer_authority.write_bytes(
            trust.canonical_json(
                {
                    "schema": publication.OBSERVER_AUTHORITY_SCHEMA,
                    "family": "independent-release-observer",
                    "independent": True,
                    "principal": observer_principal,
                    "allowedSigners": {
                        "path": str(observer_allowed),
                        "sha256": "sha256:"
                        + hashlib.sha256(observer_allowed_data).hexdigest(),
                        "size": len(observer_allowed_data),
                    },
                }
            )
        )
        attestation_path = external / "publication-observation.json"
        attestation_path.write_bytes(
            trust.canonical_json(publication.observation_payload(record))
        )
        subprocess.run(
            [
                str(SSH_KEYGEN),
                "-Y",
                "sign",
                "-f",
                str(observer_private),
                "-n",
                publication.OBSERVER_NAMESPACE,
                str(attestation_path),
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        attestation_data = attestation_path.read_bytes()
        attestation_signature = Path(str(attestation_path) + ".sig")
        attestation_signature_data = attestation_signature.read_bytes()
        record["observerAttestation"] = {
            "path": str(attestation_path),
            "sha256": "sha256:" + hashlib.sha256(attestation_data).hexdigest(),
            "size": len(attestation_data),
            "signature": {
                "path": str(attestation_signature),
                "sha256": "sha256:"
                + hashlib.sha256(attestation_signature_data).hexdigest(),
                "size": len(attestation_signature_data),
            },
        }
        path = external / "publication.json"
        path.write_text(json.dumps(record), encoding="utf-8")
        return repo, record, path, {
            "trusted_root": trusted_root,
            "trusted_root_sha256": root_digest,
            "observer_authority": observer_authority,
            "observer_authority_sha256": trust.sha256_file(observer_authority),
        }

    def test_matching_publication_channels_pass(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path, trust_args = self.fixture(Path(temporary))
            report = self.verify_fixture(path, repo, trust_args)
            self.assertTrue(report["pass"])
            self.assertEqual(report["assets"], 5)

    def test_channel_or_asset_mismatch_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            mismatch = copy.deepcopy(record)
            mismatch["secondChannel"]["rootSHA256"] = "sha256:" + "b" * 64
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "second trust channel differs"):
                self.verify_fixture(path, repo, trust_args)

            mismatch = copy.deepcopy(record)
            mismatch["github"]["assets"][0]["size"] += 1
            path.write_text(json.dumps(mismatch), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "assets differ"):
                self.verify_fixture(path, repo, trust_args)

    def test_publication_record_inside_candidate_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path, trust_args = self.fixture(Path(temporary))
            inside = repo / "publication.json"
            inside.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "outside"):
                self.verify_fixture(inside, repo, trust_args)

    def test_irrelevant_receipt_and_dirty_checkout_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            root_receipt = Path(record["site"]["rootDigestReceipt"]["path"])
            root_receipt.write_text("sha256:" + "b" * 64 + "\n", encoding="utf-8")
            data = root_receipt.read_bytes()
            record["site"]["rootDigestReceipt"].update(
                {"sha256": "sha256:" + hashlib.sha256(data).hexdigest(), "size": len(data)}
            )
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(
                publication.PublicationError,
                "publication observer attestation facts differ|site root digest receipt differs",
            ):
                self.verify_fixture(path, repo, trust_args)

        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path, trust_args = self.fixture(Path(temporary))
            (repo / "untracked.txt").write_text("dirty\n", encoding="utf-8")
            with self.assertRaisesRegex(publication.PublicationError, "dirty"):
                self.verify_fixture(path, repo, trust_args)

    def test_unsigned_release_statement_is_rejected_cryptographically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            statement_path = Path(record["threshold"]["releaseStatement"]["path"])
            envelope = json.loads(statement_path.read_text(encoding="utf-8"))
            envelope["signatures"] = []
            statement_path.write_bytes(trust.canonical_json(envelope))
            data = statement_path.read_bytes()
            record["threshold"]["releaseStatement"].update(
                {"sha256": trust.sha256_bytes(data), "size": len(data)}
            )
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(publication.PublicationError, "signatures|signature threshold"):
                self.verify_fixture(path, repo, trust_args)

    def test_ignored_checkout_payload_and_malformed_url_are_refused_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path, trust_args = self.fixture(Path(temporary))
            (repo / ".git" / "info" / "exclude").write_text("ignored.bin\n", encoding="utf-8")
            (repo / "ignored.bin").write_bytes(b"hidden payload\n")
            with self.assertRaisesRegex(publication.PublicationError, "ignored payload"):
                self.verify_fixture(path, repo, trust_args)

        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            record["site"]["landingURL"] = "https://islanddevcrew.com:broken/skills/forge"
            path.write_text(json.dumps(record), encoding="utf-8")
            with self.assertRaisesRegex(
                publication.PublicationError,
                "publication observer attestation facts differ|credential-free HTTPS",
            ):
                self.verify_fixture(path, repo, trust_args)

    def test_candidate_local_git_executable_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, _, path, trust_args = self.fixture(Path(temporary))
            candidate_git = repo / ".git" / "candidate-git"
            shutil.copyfile(GIT, candidate_git)
            candidate_git.chmod(0o755)
            candidate_digest = "sha256:" + hashlib.sha256(candidate_git.read_bytes()).hexdigest()

            with self.assertRaisesRegex(publication.PublicationError, "Git must remain outside"):
                publication.verify(
                    path,
                    repo,
                    candidate_git,
                    candidate_digest,
                    "Island-Dev-Crew/idc-skills",
                    "islanddevcrew.com",
                    trusted_root=trust_args["trusted_root"],
                    trusted_root_sha256=trust_args["trusted_root_sha256"],
                    ssh_keygen=SSH_KEYGEN,
                    ssh_keygen_sha256=SSH_KEYGEN_SHA256,
                    observer_authority=trust_args["observer_authority"],
                    observer_authority_sha256=trust_args["observer_authority_sha256"],
                    now=NOW,
                )

    def test_locally_rehashed_publication_receipt_without_observer_signature_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            landing_path = Path(record["site"]["landingReceipt"]["path"])
            landing = json.loads(landing_path.read_text(encoding="utf-8"))
            landing["observedAt"] = "2026-08-23T00:01:00Z"
            landing_path.write_text(json.dumps(landing), encoding="utf-8")
            landing_data = landing_path.read_bytes()
            record["site"]["landingReceipt"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(landing_data).hexdigest(),
                    "size": len(landing_data),
                }
            )
            attestation_path = Path(record["observerAttestation"]["path"])
            attestation_path.write_bytes(
                trust.canonical_json(publication.observation_payload(record))
            )
            attestation_data = attestation_path.read_bytes()
            record["observerAttestation"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(attestation_data).hexdigest(),
                    "size": len(attestation_data),
                }
            )
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(
                publication.PublicationError, "observer signature is invalid"
            ):
                self.verify_fixture(path, repo, trust_args)

    def test_publication_observer_key_must_be_disjoint_from_release_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            external = path.parent
            release_private = external / "release-key"
            release_public = " ".join(
                Path(str(release_private) + ".pub")
                .read_text(encoding="utf-8")
                .split()[:2]
            )
            allowed_path = external / "publication-observer.allowed-signers"
            allowed_path.write_text(
                f"idc-publication-observer {release_public}\n", encoding="utf-8"
            )
            allowed_data = allowed_path.read_bytes()
            authority_path = trust_args["observer_authority"]
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            authority["allowedSigners"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(allowed_data).hexdigest(),
                    "size": len(allowed_data),
                }
            )
            authority_path.write_bytes(trust.canonical_json(authority))
            trust_args["observer_authority_sha256"] = trust.sha256_file(authority_path)

            attestation_path = Path(record["observerAttestation"]["path"])
            signature_path = Path(record["observerAttestation"]["signature"]["path"])
            signature_path.unlink()
            subprocess.run(
                [
                    str(SSH_KEYGEN),
                    "-Y",
                    "sign",
                    "-f",
                    str(release_private),
                    "-n",
                    publication.OBSERVER_NAMESPACE,
                    str(attestation_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            signature_data = signature_path.read_bytes()
            record["observerAttestation"]["signature"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(signature_data).hexdigest(),
                    "size": len(signature_data),
                }
            )
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(
                publication.PublicationError,
                "observer signing key must be disjoint",
            ):
                self.verify_fixture(path, repo, trust_args)

    def test_publication_observer_key_must_be_disjoint_from_content_signing_key(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo, record, path, trust_args = self.fixture(Path(temporary))
            external = path.parent
            content_private = external / "content-key"
            content_public = " ".join(
                Path(str(content_private) + ".pub")
                .read_text(encoding="utf-8")
                .split()[:2]
            )
            allowed_path = external / "publication-observer.allowed-signers"
            allowed_path.write_text(
                f"idc-publication-observer {content_public}\n", encoding="utf-8"
            )
            allowed_data = allowed_path.read_bytes()
            authority_path = trust_args["observer_authority"]
            authority = json.loads(authority_path.read_text(encoding="utf-8"))
            authority["allowedSigners"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(allowed_data).hexdigest(),
                    "size": len(allowed_data),
                }
            )
            authority_path.write_bytes(trust.canonical_json(authority))
            trust_args["observer_authority_sha256"] = trust.sha256_file(authority_path)

            attestation_path = Path(record["observerAttestation"]["path"])
            signature_path = Path(record["observerAttestation"]["signature"]["path"])
            signature_path.unlink()
            subprocess.run(
                [
                    str(SSH_KEYGEN),
                    "-Y",
                    "sign",
                    "-f",
                    str(content_private),
                    "-n",
                    publication.OBSERVER_NAMESPACE,
                    str(attestation_path),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            signature_data = signature_path.read_bytes()
            record["observerAttestation"]["signature"].update(
                {
                    "sha256": "sha256:" + hashlib.sha256(signature_data).hexdigest(),
                    "size": len(signature_data),
                }
            )
            path.write_text(json.dumps(record), encoding="utf-8")

            with self.assertRaisesRegex(
                publication.PublicationError,
                "observer signing key must be disjoint",
            ):
                self.verify_fixture(path, repo, trust_args)


if __name__ == "__main__":
    unittest.main()
