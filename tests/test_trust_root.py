from __future__ import annotations

import copy
import datetime as dt
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import trust_root as trust


SSH_KEYGEN = Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
GIT = Path(shutil.which("git") or "/usr/bin/git")
BUILD_TRUST = Path(__file__).resolve().parents[1] / "scripts" / "build_trust_metadata.py"
VERIFY_EXTERNAL = Path(__file__).resolve().parents[1] / "scripts" / "verify_external_root.py"
NOW = dt.datetime(2026, 8, 22, 12, 0, tzinfo=dt.timezone.utc)


class TrustRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not SSH_KEYGEN.is_file():
            raise unittest.SkipTest("OpenSSH ssh-keygen is required")
        cls.key_space = tempfile.TemporaryDirectory(prefix="idc-root-keys-")
        cls.key_root = Path(cls.key_space.name)
        cls.keys: dict[str, tuple[Path, str, str]] = {}
        for family in ("old", "new", "attacker"):
            for index in range(1, 4):
                name = f"{family}{index}"
                private = cls.key_root / name
                completed = subprocess.run(
                    [str(SSH_KEYGEN), "-q", "-t", "ed25519", "-N", "", "-f", str(private)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if completed.returncode != 0:
                    raise RuntimeError(completed.stderr.decode())
                public = " ".join(private.with_suffix(".pub").read_text(encoding="utf-8").split()[:2])
                key = {
                    "keytype": "ed25519",
                    "keyval": {"public": public},
                    "scheme": "ssh-ed25519",
                }
                cls.keys[name] = (private, trust.keyid_for(key), public)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.key_space.cleanup()

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="idc-root-test-")
        self.root = Path(self.temporary.name)
        self.external = self.root / "external"
        self.repo = self.root / "repo"
        self.external.mkdir()
        self.repo.mkdir()
        self.root1 = self.make_root(
            self.external / "1.root.json",
            version=1,
            root_family="old",
            release_family="old",
            signers=["old1", "old2"],
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @classmethod
    def key_object(cls, name: str) -> tuple[str, dict[str, object]]:
        _, keyid, public = cls.keys[name]
        return keyid, {
            "keytype": "ed25519",
            "keyval": {"public": public},
            "scheme": "ssh-ed25519",
        }

    def signed_envelope(self, signed: dict[str, object], signers: list[str], namespace: str) -> dict[str, object]:
        payload = trust.canonical_json(signed)
        signatures = []
        for position, signer in enumerate(signers):
            private, keyid, _ = self.keys[signer]
            data_path = self.root / f"payload-{len(list(self.root.glob('payload-*')))}-{position}.json"
            data_path.write_bytes(payload)
            completed = subprocess.run(
                [str(SSH_KEYGEN), "-Y", "sign", "-f", str(private), "-n", namespace, str(data_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr.decode())
            signature_path = data_path.with_name(data_path.name + ".sig")
            signatures.append({"keyid": keyid, "sig": signature_path.read_text(encoding="utf-8")})
            data_path.unlink()
            signature_path.unlink()
        return {"signatures": signatures, "signed": signed}

    def make_root(
        self,
        path: Path,
        *,
        version: int,
        root_family: str,
        release_family: str,
        signers: list[str],
        expires: str = "2030-01-01T00:00:00Z",
    ) -> Path:
        root_names = [f"{root_family}{number}" for number in range(1, 4)]
        release_names = [f"{release_family}{number}" for number in range(1, 4)]
        key_records = dict(self.key_object(name) for name in sorted(set(root_names + release_names)))
        root_keyids = [self.keys[name][1] for name in root_names]
        release_keyids = [self.keys[name][1] for name in release_names]
        signed = {
            "_type": "root",
            "consistentSnapshot": True,
            "expires": expires,
            "keys": key_records,
            "roles": {
                "release": {"keyids": release_keyids, "threshold": 2},
                "root": {"keyids": root_keyids, "threshold": 2},
            },
            "schema": trust.ROOT_SCHEMA,
            "specVersion": "1.0",
            "version": version,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(trust.canonical_json(self.signed_envelope(signed, signers, trust.ROOT_NAMESPACE)))
        return path

    def load_initial(self) -> tuple[trust.ParsedEnvelope, dict[str, object]]:
        envelope, root = trust.load_trusted_root(
            self.root1,
            repo_root=self.repo,
            ssh_keygen=SSH_KEYGEN,
            pinned_digest=trust.sha256_file(self.root1),
        )
        return envelope, dict(root)

    def make_valid_rotation(self, name: str = "2.root.json") -> Path:
        return self.make_root(
            self.repo / name,
            version=2,
            root_family="new",
            release_family="new",
            signers=["old1", "old2", "new1", "new2"],
        )

    def test_valid_dual_threshold_rotation(self) -> None:
        initial, root = self.load_initial()
        update = self.make_valid_rotation()
        final_envelope, final_root = trust.update_root_chain(
            initial, root, [update], ssh_keygen=SSH_KEYGEN, now=NOW
        )
        self.assertEqual(final_root["version"], 2)
        self.assertEqual(final_envelope.digest, trust.sha256_file(update))

    def test_public_builder_emits_verifiable_root_without_private_key_access(self) -> None:
        payload = self.root / "builder-root.payload.json"
        envelope_path = self.root / "builder-root.json"
        command = [
            "python3", "-B", str(BUILD_TRUST), "root-payload",
            "--version", "1", "--expires", "2030-01-01T00:00:00Z",
        ]
        for name in ("old1", "old2", "old3"):
            command += ["--root-key", str(self.keys[name][0].with_suffix(".pub"))]
        command += ["--root-threshold", "2"]
        for name in ("old1", "old2", "old3"):
            command += ["--release-key", str(self.keys[name][0].with_suffix(".pub"))]
        command += ["--release-threshold", "2", "--output", str(payload)]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        signature_arguments = []
        for name in ("old1", "old2"):
            signer_payload = self.root / f"{name}.payload.json"
            signer_payload.write_bytes(payload.read_bytes())
            signed = subprocess.run(
                [str(SSH_KEYGEN), "-Y", "sign", "-f", str(self.keys[name][0]), "-n", trust.ROOT_NAMESPACE, str(signer_payload)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(signed.returncode, 0, signed.stderr)
            signature_arguments += [
                "--signature", f"{self.keys[name][1]}={signer_payload}.sig"
            ]
        assembled = subprocess.run(
            [
                "python3", "-B", str(BUILD_TRUST), "envelope",
                "--payload", str(payload), *signature_arguments, "--output", str(envelope_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(assembled.returncode, 0, assembled.stderr)
        parsed = trust.load_envelope(envelope_path, "builder root")
        root = trust.parse_root(parsed, "builder root")
        valid = trust.verify_role_threshold(
            parsed, root, "root", trust.ROOT_NAMESPACE, SSH_KEYGEN, "builder root"
        )
        self.assertEqual(len(valid), 2)

    def test_public_builder_refuses_output_overwrite(self) -> None:
        output = self.root / "existing.json"
        output.write_text("keep\n", encoding="utf-8")
        completed = subprocess.run(
            [
                "python3", "-B", str(BUILD_TRUST), "root-payload",
                "--version", "1", "--expires", "2030-01-01T00:00:00Z",
                "--root-key", str(self.keys["old1"][0].with_suffix(".pub")),
                "--root-threshold", "1",
                "--release-key", str(self.keys["old1"][0].with_suffix(".pub")),
                "--release-threshold", "1", "--output", str(output),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("refusing to overwrite", completed.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "keep\n")

    def test_forged_in_band_root_is_rejected_before_release_read(self) -> None:
        forged = self.make_root(
            self.repo / "2.root.json",
            version=2,
            root_family="attacker",
            release_family="attacker",
            signers=["attacker1", "attacker2"],
        )
        with self.assertRaisesRegex(trust.TrustError, "under old root"):
            trust.verify_external_release(
                repo=self.repo,
                trusted_root_path=self.root1,
                trusted_root_digest=trust.sha256_file(self.root1),
                root_updates=[forged],
                statement_path=self.repo / "does-not-exist.json",
                artifacts={},
                ssh_keygen=SSH_KEYGEN,
                ssh_keygen_digest=trust.sha256_file(SSH_KEYGEN.resolve()),
                git=GIT,
                git_digest=trust.sha256_file(GIT.resolve()),
                now=NOW,
            )

    def test_rollback_is_rejected(self) -> None:
        initial, root = self.load_initial()
        update = self.make_valid_rotation()
        with self.assertRaisesRegex(trust.TrustError, "rollback"):
            trust.update_root_chain(initial, root, [update, self.root1], ssh_keygen=SSH_KEYGEN, now=NOW)

    def test_same_version_equivocation_is_rejected(self) -> None:
        equivocation = self.make_root(
            self.repo / "equivocation.root.json",
            version=1,
            root_family="attacker",
            release_family="attacker",
            signers=["attacker1", "attacker2"],
        )
        initial, root = self.load_initial()
        with self.assertRaisesRegex(trust.TrustError, "equivocation"):
            trust.update_root_chain(initial, root, [equivocation], ssh_keygen=SSH_KEYGEN, now=NOW)

    def test_external_checkpoint_rejects_withheld_rotation(self) -> None:
        initial, root = self.load_initial()
        update = self.make_valid_rotation()
        final_envelope, final_root = trust.update_root_chain(
            initial, root, [update], ssh_keygen=SSH_KEYGEN, now=NOW
        )
        checkpoint = trust.canonical_json(trust.root_checkpoint(final_envelope, final_root))
        with self.assertRaisesRegex(trust.TrustError, "rollback against external checkpoint"):
            trust.validate_root_checkpoint(checkpoint, initial, root)

    def test_skipped_rotation_is_rejected(self) -> None:
        skipped = self.make_root(
            self.repo / "3.root.json",
            version=3,
            root_family="new",
            release_family="new",
            signers=["old1", "old2", "new1", "new2"],
        )
        initial, root = self.load_initial()
        with self.assertRaisesRegex(trust.TrustError, "skipped root rotation"):
            trust.update_root_chain(initial, root, [skipped], ssh_keygen=SSH_KEYGEN, now=NOW)

    def test_expired_final_root_is_rejected(self) -> None:
        expired = self.make_root(
            self.repo / "2.root.json",
            version=2,
            root_family="new",
            release_family="new",
            signers=["old1", "old2", "new1", "new2"],
            expires="2020-01-01T00:00:00Z",
        )
        initial, root = self.load_initial()
        with self.assertRaisesRegex(trust.TrustError, "expired"):
            trust.update_root_chain(initial, root, [expired], ssh_keygen=SSH_KEYGEN, now=NOW)

    def test_partial_old_threshold_is_rejected(self) -> None:
        partial = self.make_root(
            self.repo / "2.root.json",
            version=2,
            root_family="new",
            release_family="new",
            signers=["old1", "new1", "new2"],
        )
        initial, root = self.load_initial()
        with self.assertRaisesRegex(trust.TrustError, "under old root"):
            trust.update_root_chain(initial, root, [partial], ssh_keygen=SSH_KEYGEN, now=NOW)

    def test_in_tree_initial_root_and_wrong_digest_are_rejected(self) -> None:
        in_tree = self.repo / "1.root.json"
        shutil.copyfile(self.root1, in_tree)
        with self.assertRaisesRegex(trust.TrustError, "outside"):
            trust.load_trusted_root(in_tree, repo_root=self.repo, ssh_keygen=SSH_KEYGEN)
        with self.assertRaisesRegex(trust.TrustError, "differs"):
            trust.load_trusted_root(
                self.root1,
                repo_root=self.repo,
                ssh_keygen=SSH_KEYGEN,
                pinned_digest="sha256:" + "0" * 64,
            )

    def test_tool_digest_substitution_is_rejected_before_candidate_metadata(self) -> None:
        with self.assertRaisesRegex(trust.TrustError, "ssh-keygen bytes differ"):
            trust.verify_external_release(
                repo=self.repo,
                trusted_root_path=self.root1,
                trusted_root_digest=trust.sha256_file(self.root1),
                root_updates=[],
                statement_path=self.repo / "does-not-exist.json",
                artifacts={},
                ssh_keygen=SSH_KEYGEN,
                ssh_keygen_digest="sha256:" + "0" * 64,
                git=GIT,
                git_digest=trust.sha256_file(GIT.resolve()),
                now=NOW,
            )

    def prepare_release(self, *, tree_override: str | None = None) -> dict[str, object]:
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "IDC Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        (self.repo / "tracked.txt").write_text("candidate\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(self.repo), "add", "tracked.txt"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "candidate"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "tag", "2.0.4"], check=True)
        commit = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
        artifacts = {}
        for name in ("archive", "freshnessIndex", "installInventory", "manifest", "registry"):
            path = self.external / f"{name}.bin"
            path.write_bytes((name + " exact bytes\n").encode())
            artifacts[name] = path
        signed = {
            "_type": "release",
            "artifacts": {
                name: {"sha256": trust.sha256_file(path), "size": path.stat().st_size}
                for name, path in artifacts.items()
            },
            "expires": "2030-01-01T00:00:00Z",
            "git": {"commit": commit, "tag": "2.0.4", "tree": tree_override or tree},
            "release": "2.0.4",
            "releaseSequence": 2,
            "rootVersion": 2,
            "schema": trust.RELEASE_SCHEMA,
        }
        statement_path = self.external / "release-statement.json"
        statement_path.write_bytes(
            trust.canonical_json(self.signed_envelope(signed, ["new1", "new2"], trust.RELEASE_NAMESPACE))
        )
        return {"artifacts": artifacts, "statement": statement_path, "signed": signed}

    def verify_prepared_release(self, prepared: dict[str, object]) -> dict[str, object]:
        update = self.make_valid_rotation()
        return trust.verify_external_release(
            repo=self.repo,
            trusted_root_path=self.root1,
            trusted_root_digest=trust.sha256_file(self.root1),
            root_updates=[update],
            statement_path=prepared["statement"],
            artifacts=prepared["artifacts"],
            ssh_keygen=SSH_KEYGEN,
            ssh_keygen_digest=trust.sha256_file(SSH_KEYGEN.resolve()),
            git=GIT,
            git_digest=trust.sha256_file(GIT.resolve()),
            now=NOW,
        )

    def test_release_statement_binds_all_objects(self) -> None:
        prepared = self.prepare_release()
        result = self.verify_prepared_release(prepared)
        self.assertTrue(result["externalTrustVerified"])
        self.assertTrue(result["eligibleForContentVerification"])
        self.assertFalse(result["readyToInstall"])
        self.assertEqual(result["release"], "2.0.4")

    def test_cli_persists_checkpoint_and_rejects_withheld_root(self) -> None:
        prepared = self.prepare_release()
        update = self.make_valid_rotation()
        checkpoint = self.external / "state" / "root-checkpoint.json"
        checkpoint.parent.mkdir(mode=0o700)
        command = [
            "python3", "-B", str(VERIFY_EXTERNAL),
            "--repo", str(self.repo),
            "--trusted-root", str(self.root1),
            "--trusted-root-sha256", trust.sha256_file(self.root1),
            "--root-update", str(update),
            "--root-checkpoint", str(checkpoint),
            "--release-statement", str(prepared["statement"]),
            "--archive", str(prepared["artifacts"]["archive"]),
            "--freshness-index", str(prepared["artifacts"]["freshnessIndex"]),
            "--install-inventory", str(prepared["artifacts"]["installInventory"]),
            "--manifest", str(prepared["artifacts"]["manifest"]),
            "--registry", str(prepared["artifacts"]["registry"]),
            "--git", str(GIT), "--git-sha256", trust.sha256_file(GIT.resolve()),
            "--ssh-keygen", str(SSH_KEYGEN),
            "--ssh-keygen-sha256", trust.sha256_file(SSH_KEYGEN.resolve()),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertTrue(json.loads(completed.stdout)["externalTrustVerified"])
        self.assertEqual(json.loads(checkpoint.read_text())["version"], 2)
        without_rotation = command.copy()
        update_position = without_rotation.index("--root-update")
        del without_rotation[update_position : update_position + 2]
        refused = subprocess.run(without_rotation, text=True, capture_output=True, check=False)
        self.assertEqual(refused.returncode, 2)
        self.assertIn("rollback against external checkpoint", refused.stderr)

    def test_archive_substitution_is_rejected(self) -> None:
        prepared = self.prepare_release()
        prepared["artifacts"]["archive"].write_bytes(b"substituted archive\n")
        with self.assertRaisesRegex(trust.TrustError, "archive artifact differs"):
            self.verify_prepared_release(prepared)

    def test_tag_tree_mismatch_is_rejected(self) -> None:
        prepared = self.prepare_release(tree_override="0" * 40)
        with self.assertRaisesRegex(trust.TrustError, "tag tree differs"):
            self.verify_prepared_release(prepared)


if __name__ == "__main__":
    unittest.main()
