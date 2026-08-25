from __future__ import annotations

import copy
import datetime as dt
import gzip
import io
import json
import shutil
import subprocess
import tempfile
import time
import tarfile
import unittest
from pathlib import Path

from scripts import trust_root as trust


SSH_KEYGEN = Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen")
GIT = Path(shutil.which("git") or "/usr/bin/git")
BUILD_TRUST = Path(__file__).resolve().parents[1] / "scripts" / "build_trust_metadata.py"
VERIFY_EXTERNAL = Path(__file__).resolve().parents[1] / "scripts" / "verify_external_root.py"
NOW = dt.datetime(2026, 8, 22, 12, 0, tzinfo=dt.timezone.utc)


def canonical_release_index(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def deterministic_release_archive(
    release: str, files: dict[str, tuple[bytes, int]]
) -> bytes:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for relative in sorted(files):
            data, mode = files[relative]
            info = tarfile.TarInfo(f"idc-skills-{release}/{relative}")
            info.size = len(data)
            info.mode = mode
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            archive.addfile(info, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="", fileobj=compressed, mode="wb", compresslevel=9, mtime=0
    ) as stream:
        stream.write(tar_buffer.getvalue())
    return compressed.getvalue()


def fixture_registry(names: list[str]) -> dict[str, object]:
    return {
        "anchor": "fixture evidence law",
        "buildOrder": names,
        "bundleName": "idc-skills-forge",
        "dualHarness": "fixture dual harness boundary",
        "harnessContract": "docs/harness-support.json",
        "manifestSequence": 2,
        "name": "idc-skills-forge",
        "promotesTo": "Island-Dev-Crew",
        "release": "2.0.4",
        "skills": [
            {
                "invocation": "model",
                "name": name,
                "path": name,
                "provenance": "fixture provenance",
                "summary": "fixture summary",
                "triggers": ["fixture trigger"],
            }
            for name in names
        ],
        "staging": "Navigata1/idc-skills-forge",
        "version": 1,
    }


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
        checkpoint = trust.canonical_json(
            trust.root_checkpoint(
                final_envelope,
                final_root,
                release_sequence=1,
                signed_statement_digest="sha256:" + "1" * 64,
            )
        )
        with self.assertRaisesRegex(trust.TrustError, "rollback against external checkpoint"):
            trust.validate_root_checkpoint(
                checkpoint,
                initial,
                root,
                release_sequence=1,
                signed_statement_digest="sha256:" + "1" * 64,
            )

    def test_external_checkpoint_rejects_release_sequence_rollback(self) -> None:
        initial, root = self.load_initial()
        checkpoint = trust.canonical_json(
            trust.root_checkpoint(
                initial,
                root,
                release_sequence=3,
                signed_statement_digest="sha256:" + "3" * 64,
            )
        )
        with self.assertRaisesRegex(trust.TrustError, "release-sequence rollback"):
            trust.validate_root_checkpoint(
                checkpoint,
                initial,
                root,
                release_sequence=2,
                signed_statement_digest="sha256:" + "2" * 64,
            )

    def test_external_checkpoint_rejects_same_sequence_statement_equivocation(self) -> None:
        initial, root = self.load_initial()
        checkpoint = trust.canonical_json(
            trust.root_checkpoint(
                initial,
                root,
                release_sequence=2,
                signed_statement_digest="sha256:" + "1" * 64,
            )
        )
        with self.assertRaisesRegex(trust.TrustError, "release equivocation"):
            trust.validate_root_checkpoint(
                checkpoint,
                initial,
                root,
                release_sequence=2,
                signed_statement_digest="sha256:" + "2" * 64,
            )

    def test_trust_clis_import_under_python_isolated_mode(self) -> None:
        for script in (BUILD_TRUST, VERIFY_EXTERNAL):
            completed = subprocess.run(
                ["python3", "-I", "-B", str(script), "--help"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, f"{script}: {completed.stderr}")

    def test_root_checkpoint_updates_are_serialized_across_processes(self) -> None:
        helper = "\n".join(
            (
                "import sys, time",
                "from pathlib import Path",
                "from scripts.verify_external_root import _checkpoint_lock",
                "with _checkpoint_lock(Path(sys.argv[1])):",
                "    print('locked', flush=True)",
                "    time.sleep(float(sys.argv[2]))",
            )
        )
        checkpoint = self.external / "serialized-checkpoint.json"
        environment = {"PYTHONPATH": str(Path(__file__).resolve().parents[1])}
        first = subprocess.Popen(
            ["python3", "-B", "-c", helper, str(checkpoint), "0.6"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        first_line = first.stdout.readline().strip()
        if first_line != "locked":
            _, first_stderr = first.communicate(timeout=3)
            self.fail(f"first lock process did not acquire the lock: {first_stderr}")
        started = time.monotonic()
        second = subprocess.run(
            ["python3", "-B", "-c", helper, str(checkpoint), "0"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        elapsed = time.monotonic() - started
        first_stdout, first_stderr = first.communicate(timeout=3)
        self.assertEqual(first.returncode, 0, first_stderr)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(second.stdout.strip(), "locked")
        self.assertGreaterEqual(elapsed, 0.45)

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

    def prepare_release(
        self,
        *,
        tree_override: str | None = None,
        tag_kind: str = "annotated",
        inventory_release_override: str | None = None,
        index_release_override: str | None = None,
        index_launcher_override: str | None = None,
    ) -> dict[str, object]:
        subprocess.run(["git", "-C", str(self.repo), "init", "-q"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "IDC Test"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        artifacts = {}
        for name in ("archive", "freshnessIndex", "installInventory", "manifest", "registry"):
            path = self.external / f"{name}.bin"
            path.write_bytes((name + " exact bytes\n").encode())
            artifacts[name] = path
        content_public_key = self.external / "content-signing.pub"
        content_public_key.write_text(self.keys["new1"][2] + "\n", encoding="utf-8")
        content_allowed_signers = self.external / "content-allowed-signers"
        content_allowed_signers.write_text(
            f"idc-skills {self.keys['new1'][2]}\n", encoding="utf-8"
        )
        tracked_data = b"candidate\n"
        launcher_data = b"fixture launcher\n"
        verifier_data = b"fixture verifier\n"
        skill_names = [f"skill-{index:02d}" for index in range(50)]
        launcher_digest = trust.sha256_bytes(launcher_data)
        verifier_digest = trust.sha256_bytes(verifier_data)
        registry_data = trust.canonical_registry(fixture_registry(skill_names))
        artifacts["registry"].write_bytes(registry_data)
        manifest_value = {
            "manifestSequence": 2,
            "profile": "release",
            "release": "2.0.4",
            "repositoryFiles": {
                "bootstrap/idc_verify_fresh.py": {
                    "posixMode": 0o644,
                    "sha256": launcher_digest,
                    "size": len(launcher_data),
                },
                "keys/allowed_signers": {
                    "posixMode": 0o644,
                    "sha256": trust.sha256_bytes(content_allowed_signers.read_bytes()),
                    "size": content_allowed_signers.stat().st_size,
                },
                "keys/idc-skills-signing.pub": {
                    "posixMode": 0o644,
                    "sha256": trust.sha256_bytes(content_public_key.read_bytes()),
                    "size": content_public_key.stat().st_size,
                },
                "scripts/skill_integrity.py": {
                    "posixMode": 0o755,
                    "sha256": verifier_digest,
                    "size": len(verifier_data),
                },
                "skills/registry.json": {
                    "posixMode": 0o644,
                    "sha256": trust.sha256_bytes(registry_data),
                    "size": len(registry_data),
                },
                "tracked.txt": {
                    "posixMode": 0o644,
                    "sha256": trust.sha256_bytes(tracked_data),
                    "size": len(tracked_data),
                }
            },
            "schema": trust.MANIFEST_SCHEMA,
            "skillCount": 50,
            "skillNames": skill_names,
        }
        manifest_data = trust.canonical_manifest(manifest_value)
        artifacts["manifest"].write_bytes(manifest_data)
        repository_files = {
            "bootstrap/idc_verify_fresh.py": launcher_data,
            "integrity/manifest.json": manifest_data,
            "integrity/manifest.json.sig": b"fixture manifest signature\n",
            "keys/allowed_signers": content_allowed_signers.read_bytes(),
            "keys/idc-skills-signing.pub": content_public_key.read_bytes(),
            "scripts/skill_integrity.py": verifier_data,
            "skills/registry.json": registry_data,
            "tracked.txt": tracked_data,
        }
        for relative, data in repository_files.items():
            destination = self.repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(data)
        (self.repo / "scripts/skill_integrity.py").chmod(0o755)
        subprocess.run(["git", "-C", str(self.repo), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "candidate"], check=True)
        if tag_kind == "annotated":
            subprocess.run(
                ["git", "-C", str(self.repo), "tag", "-a", "-m", "release", "2.0.4"],
                check=True,
            )
        elif tag_kind == "lightweight":
            subprocess.run(["git", "-C", str(self.repo), "tag", "2.0.4"], check=True)
        elif tag_kind != "absent":
            self.fail(f"unknown test tag kind: {tag_kind}")
        commit = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD"], text=True).strip()
        tree = subprocess.check_output(["git", "-C", str(self.repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
        archive_files = {
            relative: (
                data,
                0o755 if relative == "scripts/skill_integrity.py" else 0o644,
            )
            for relative, data in repository_files.items()
        }
        artifacts["archive"].write_bytes(
            deterministic_release_archive("2.0.4", archive_files)
        )
        artifacts["freshnessIndex"].write_bytes(
            canonical_release_index(
                {
                    "generatedAt": "2026-08-22T11:00:00Z",
                    "indexSequence": 2,
                    "releases": [
                        {
                            "gitCommit": commit,
                            "launcherSHA256": index_launcher_override
                            or launcher_digest,
                            "manifestSHA256": trust.sha256_bytes(manifest_data),
                            "manifestSequence": 2,
                            "release": index_release_override or "2.0.4",
                            "verifierSHA256": verifier_digest,
                        }
                    ],
                    "schema": "idc-skills-release-index/v1",
                    "validUntil": "2026-09-01T11:00:00Z",
                }
            )
        )
        inventory_value = trust.build_install_inventory(manifest_data)
        if inventory_release_override is not None:
            inventory_value["release"] = inventory_release_override
        artifacts["installInventory"].write_bytes(trust.canonical_json(inventory_value))
        signed = {
            "_type": "release",
            "artifacts": {
                name: {"sha256": trust.sha256_file(path), "size": path.stat().st_size}
                for name, path in artifacts.items()
            },
            "contentSigning": trust.content_signing_record(
                content_public_key, content_allowed_signers
            ),
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

    def test_release_statement_requires_content_signing_identity(self) -> None:
        prepared = self.prepare_release()
        missing = copy.deepcopy(prepared["signed"])
        del missing["contentSigning"]
        envelope = trust.ParsedEnvelope(
            value={}, signed=missing, signed_bytes=trust.canonical_json(missing), digest=""
        )
        with self.assertRaisesRegex(trust.TrustError, "keys differ"):
            trust.parse_release(envelope)

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
        self.assertEqual(result["contentSigning"], prepared["signed"]["contentSigning"])

    def test_release_statement_rejects_lightweight_tag(self) -> None:
        prepared = self.prepare_release(tag_kind="lightweight")
        with self.assertRaisesRegex(trust.TrustError, "annotated tag"):
            self.verify_prepared_release(prepared)

    def test_release_statement_rejects_semantically_mismatched_install_inventory(self) -> None:
        prepared = self.prepare_release(inventory_release_override="9.9.9")
        with self.assertRaisesRegex(trust.TrustError, "signed manifest expectation"):
            self.verify_prepared_release(prepared)

    def test_release_statement_rejects_semantically_mismatched_freshness_index(self) -> None:
        prepared = self.prepare_release(index_release_override="9.9.9")
        with self.assertRaisesRegex(trust.TrustError, "release index newest release"):
            self.verify_prepared_release(prepared)

    def test_release_statement_rejects_index_launcher_not_bound_by_manifest(self) -> None:
        prepared = self.prepare_release(
            index_launcher_override="sha256:" + "d" * 64
        )
        with self.assertRaisesRegex(trust.TrustError, "launcher digest"):
            self.verify_prepared_release(prepared)

    def test_checkpoint_identity_ignores_equivalent_signature_order(self) -> None:
        prepared = self.prepare_release()
        update = self.make_valid_rotation()
        first = trust.verify_external_release(
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
        envelope = json.loads(prepared["statement"].read_text(encoding="utf-8"))
        envelope["signatures"].reverse()
        prepared["statement"].write_bytes(trust.canonical_json(envelope))

        second = trust.verify_external_release(
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
            root_checkpoint_data=trust.canonical_json(first["rootCheckpoint"]),
            now=NOW,
        )
        self.assertEqual(first["rootCheckpoint"], second["rootCheckpoint"])

    def test_checkpoint_binds_intermediate_root_across_forward_rotation(self) -> None:
        root2a = self.make_root(
            self.external / "2a.root.json",
            version=2,
            root_family="new",
            release_family="new",
            signers=["old1", "old2", "new1", "new2"],
        )
        root3a = self.make_root(
            self.external / "3a.root.json",
            version=3,
            root_family="new",
            release_family="new",
            signers=["new1", "new2"],
        )
        root2b = self.make_root(
            self.external / "2b.root.json",
            version=2,
            root_family="attacker",
            release_family="attacker",
            signers=["old1", "old2", "attacker1", "attacker2"],
        )
        root3b = self.make_root(
            self.external / "3b.root.json",
            version=3,
            root_family="attacker",
            release_family="attacker",
            signers=["attacker1", "attacker2"],
        )
        initial_envelope, initial_root = self.load_initial()
        checkpoint_envelope, checkpoint_root = trust.update_root_chain(
            initial_envelope,
            initial_root,
            [root2a],
            ssh_keygen=SSH_KEYGEN,
            now=NOW,
        )
        checkpoint = trust.canonical_json(
            trust.root_checkpoint(
                checkpoint_envelope,
                checkpoint_root,
                release_sequence=2,
                signed_statement_digest="sha256:" + "2" * 64,
            )
        )

        prepared = self.prepare_release()
        prepared["signed"]["releaseSequence"] = 3
        prepared["signed"]["rootVersion"] = 3
        prepared["statement"].write_bytes(
            trust.canonical_json(
                self.signed_envelope(
                    prepared["signed"], ["new1", "new2"], trust.RELEASE_NAMESPACE
                )
            )
        )
        legitimate = trust.verify_external_release(
            repo=self.repo,
            trusted_root_path=self.root1,
            trusted_root_digest=trust.sha256_file(self.root1),
            root_updates=[root2a, root3a],
            statement_path=prepared["statement"],
            artifacts=prepared["artifacts"],
            ssh_keygen=SSH_KEYGEN,
            ssh_keygen_digest=trust.sha256_file(SSH_KEYGEN.resolve()),
            git=GIT,
            git_digest=trust.sha256_file(GIT.resolve()),
            root_checkpoint_data=checkpoint,
            now=NOW,
        )
        signed_statement_digest = trust.sha256_bytes(
            trust.load_envelope(prepared["statement"], "release statement").signed_bytes
        )
        self.assertEqual(legitimate["rootCheckpoint"]["version"], 3)
        self.assertEqual(
            legitimate["rootCheckpoint"]["signedStatementSHA256"],
            signed_statement_digest,
        )

        attacker_statement = self.external / "attacker-release-statement.json"
        attacker_statement.write_bytes(
            trust.canonical_json(
                self.signed_envelope(
                    prepared["signed"], ["attacker1", "attacker2"], trust.RELEASE_NAMESPACE
                )
            )
        )
        with self.assertRaisesRegex(
            trust.TrustError, "root equivocation against external checkpoint at version 2"
        ):
            trust.verify_external_release(
                repo=self.repo,
                trusted_root_path=self.root1,
                trusted_root_digest=trust.sha256_file(self.root1),
                root_updates=[root2b, root3b],
                statement_path=attacker_statement,
                artifacts=prepared["artifacts"],
                ssh_keygen=SSH_KEYGEN,
                ssh_keygen_digest=trust.sha256_file(SSH_KEYGEN.resolve()),
                git=GIT,
                git_digest=trust.sha256_file(GIT.resolve()),
                root_checkpoint_data=checkpoint,
                now=NOW,
            )

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

    def test_threshold_signed_archive_with_extra_member_is_rejected(self) -> None:
        prepared = self.prepare_release()
        manifest_data = prepared["artifacts"]["manifest"].read_bytes()
        identity = trust.parse_manifest_identity(manifest_data)
        files = {
            relative: (
                (self.repo / relative).read_bytes(),
                record["posixMode"],
            )
            for relative, record in identity["repositoryFiles"].items()
        }
        files["integrity/manifest.json"] = (manifest_data, 0o644)
        files["integrity/manifest.json.sig"] = (
            (self.repo / "integrity/manifest.json.sig").read_bytes(),
            0o644,
        )
        files["unexpected.txt"] = (b"not in the signed tree\n", 0o644)
        archive = prepared["artifacts"]["archive"]
        archive.write_bytes(deterministic_release_archive("2.0.4", files))
        prepared["signed"]["artifacts"]["archive"] = {
            "sha256": trust.sha256_file(archive),
            "size": archive.stat().st_size,
        }
        prepared["statement"].write_bytes(
            trust.canonical_json(
                self.signed_envelope(
                    prepared["signed"], ["new1", "new2"], trust.RELEASE_NAMESPACE
                )
            )
        )
        with self.assertRaisesRegex(trust.TrustError, "inventory count differs|extra member"):
            self.verify_prepared_release(prepared)

    def test_tag_tree_mismatch_is_rejected(self) -> None:
        prepared = self.prepare_release(tree_override="0" * 40)
        with self.assertRaisesRegex(trust.TrustError, "tag tree differs"):
            self.verify_prepared_release(prepared)


if __name__ == "__main__":
    unittest.main()
