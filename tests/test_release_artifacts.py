from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import io
import json
import shutil
import subprocess
import tempfile
import tarfile
import unittest
from pathlib import Path

from bootstrap import idc_verify_fresh as fresh
from scripts import trust_root as trust


REPO = Path(__file__).resolve().parents[1]
BUILDER = REPO / "scripts/build_trust_metadata.py"
ROOT_LABELS = ("agents", "claude", "pi", "hermes")
GIT = Path(shutil.which("git") or "/usr/bin/git").resolve()
SSH_KEYGEN = Path(shutil.which("ssh-keygen") or "/usr/bin/ssh-keygen").resolve()


def canonical(value: object) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def index_canonical(value: object) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, allow_nan=False, sort_keys=True, indent=2)
        + "\n"
    ).encode("utf-8")


def fixture_registry(names: list[str], release: str, sequence: int) -> dict[str, object]:
    return {
        "anchor": "fixture evidence law",
        "buildOrder": names,
        "bundleName": "idc-skills-forge",
        "dualHarness": "fixture dual harness boundary",
        "harnessContract": "docs/harness-support.json",
        "manifestSequence": sequence,
        "name": "idc-skills-forge",
        "promotesTo": "Island-Dev-Crew",
        "release": release,
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


def release_archive_bytes(
    repo: Path,
    manifest_data: bytes,
    release: str,
    *,
    extra: tuple[str, bytes] | None = None,
) -> bytes:
    identity = trust.parse_manifest_identity(manifest_data)
    files = {
        relative: ((repo / relative).read_bytes(), record["posixMode"])
        for relative, record in identity["repositoryFiles"].items()
    }
    files["integrity/manifest.json"] = (manifest_data, 0o644)
    files["integrity/manifest.json.sig"] = (
        (repo / "integrity/manifest.json.sig").read_bytes(),
        0o644,
    )
    if extra is not None:
        files[extra[0]] = (extra[1], 0o644)
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
    output = io.BytesIO()
    with gzip.GzipFile(
        filename="", fileobj=output, mode="wb", compresslevel=9, mtime=0
    ) as stream:
        stream.write(tar_buffer.getvalue())
    return output.getvalue()


class ReleaseArtifactBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="idc-release-artifacts-")
        self.root = Path(self.temporary.name)
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        self.generated_at = (now - dt.timedelta(minutes=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.valid_until = (now + dt.timedelta(days=30)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.expired_at = (now - dt.timedelta(days=1)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        self.names = [f"skill-{index:02d}" for index in range(50)]
        self.manifest_value = {
            "manifestSequence": 2,
            "profile": "release",
            "release": "2.0.4",
            "repositoryFiles": {
                "tracked.txt": {
                    "posixMode": 0o644,
                    "sha256": "sha256:" + ("a" * 64),
                    "size": 1,
                }
            },
            "schema": "idc-skill-integrity/v3",
            "skillCount": 50,
            "skillNames": self.names,
        }
        self.manifest = self.root / "manifest.json"
        self.manifest.write_bytes(index_canonical(self.manifest_value))

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_builder(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["python3", "-I", "-B", str(BUILDER), *arguments],
            text=True,
            capture_output=True,
            check=False,
        )

    def prepare_signed_repository(
        self, *, release: str, manifest_sequence: int
    ) -> tuple[Path, Path, Path, Path, Path, str, str]:
        if not GIT.is_file() or not SSH_KEYGEN.is_file():
            self.skipTest("Git and OpenSSH ssh-keygen are required")
        repo = self.root / "repo"
        external = self.root / "external"
        repo.mkdir()
        external.mkdir()
        subprocess.run([str(GIT), "-C", str(repo), "init", "-q"], check=True)
        subprocess.run(
            [str(GIT), "-C", str(repo), "config", "user.name", "IDC Test"], check=True
        )
        subprocess.run(
            [str(GIT), "-C", str(repo), "config", "user.email", "test@example.invalid"],
            check=True,
        )
        verifier = repo / "scripts/skill_integrity.py"
        launcher = repo / "bootstrap/idc_verify_fresh.py"
        registry = repo / "skills/registry.json"
        verifier.parent.mkdir(parents=True)
        launcher.parent.mkdir(parents=True)
        registry.parent.mkdir(parents=True)
        verifier.write_bytes(b"fixture verifier\n")
        launcher.write_bytes(b"fixture launcher\n")
        registry.write_bytes(
            trust.canonical_registry(
                fixture_registry(self.names, release, manifest_sequence)
            )
        )
        key = external / "content-signing"
        generated = subprocess.run(
            [
                str(SSH_KEYGEN),
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(key),
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(generated.returncode, 0, generated.stderr.decode())
        public = key.with_suffix(".pub")
        fingerprint = subprocess.check_output(
            [str(SSH_KEYGEN), "-lf", str(public)], text=True
        ).split()[1]
        public_fields = public.read_text(encoding="utf-8").split()[:2]
        allowed = external / "content-allowed-signers"
        allowed.write_text(
            f"idc-skills {' '.join(public_fields)}\n", encoding="utf-8"
        )
        repository_public = repo / "keys/idc-skills-signing.pub"
        repository_allowed = repo / "keys/allowed_signers"
        repository_public.parent.mkdir(parents=True)
        repository_public.write_bytes(public.read_bytes())
        repository_allowed.write_bytes(allowed.read_bytes())
        manifest_value = {
            "manifestSequence": manifest_sequence,
            "profile": "release",
            "release": release,
            "repositoryFiles": {
                "bootstrap/idc_verify_fresh.py": {
                    "posixMode": 0o644,
                    "sha256": digest(launcher.read_bytes()),
                    "size": launcher.stat().st_size,
                },
                "scripts/skill_integrity.py": {
                    "posixMode": 0o644,
                    "sha256": digest(verifier.read_bytes()),
                    "size": verifier.stat().st_size,
                },
                "keys/allowed_signers": {
                    "posixMode": 0o644,
                    "sha256": digest(repository_allowed.read_bytes()),
                    "size": repository_allowed.stat().st_size,
                },
                "keys/idc-skills-signing.pub": {
                    "posixMode": 0o644,
                    "sha256": digest(repository_public.read_bytes()),
                    "size": repository_public.stat().st_size,
                },
                "skills/registry.json": {
                    "posixMode": 0o644,
                    "sha256": digest(registry.read_bytes()),
                    "size": registry.stat().st_size,
                },
            },
            "schema": "idc-skill-integrity/v3",
            "skillCount": 50,
            "skillNames": self.names,
        }
        manifest = repo / "integrity/manifest.json"
        manifest.parent.mkdir()
        manifest.write_bytes(index_canonical(manifest_value))
        signed = subprocess.run(
            [
                str(SSH_KEYGEN),
                "-Y",
                "sign",
                "-f",
                str(key),
                "-n",
                "file",
                str(manifest),
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(signed.returncode, 0, signed.stderr.decode())
        signature = Path(str(manifest) + ".sig")
        subprocess.run([str(GIT), "-C", str(repo), "add", "-A"], check=True)
        subprocess.run(
            [str(GIT), "-C", str(repo), "commit", "-qm", f"release {release}"],
            check=True,
        )
        subprocess.run(
            [str(GIT), "-C", str(repo), "tag", "-a", "-m", f"release {release}", release],
            check=True,
        )
        commit = subprocess.check_output(
            [str(GIT), "-C", str(repo), "rev-parse", "HEAD"], text=True
        ).strip()
        return repo, manifest, signature, allowed, key, commit, fingerprint

    def sign_path(self, path: Path, key: Path, namespace: str) -> Path:
        signed = subprocess.run(
            [
                str(SSH_KEYGEN),
                "-Y",
                "sign",
                "-f",
                str(key),
                "-n",
                namespace,
                str(path),
            ],
            capture_output=True,
            check=False,
        )
        self.assertEqual(signed.returncode, 0, signed.stderr.decode())
        return Path(str(path) + ".sig")

    def release_index_command(
        self,
        *,
        repo: Path,
        manifest: Path,
        signature: Path,
        allowed: Path,
        fingerprint: str,
        output: Path,
    ) -> list[str]:
        return [
            "release-index",
            "--repo",
            str(repo),
            "--manifest",
            str(manifest),
            "--manifest-signature",
            str(signature),
            "--content-public-key",
            str(self.root / "external/content-signing.pub"),
            "--content-allowed-signers",
            str(allowed),
            "--expected-content-fingerprint",
            fingerprint,
            "--generated-at",
            self.generated_at,
            "--valid-until",
            self.valid_until,
            "--git",
            str(GIT),
            "--git-sha256",
            digest(GIT.read_bytes()),
            "--ssh-keygen",
            str(SSH_KEYGEN),
            "--ssh-keygen-sha256",
            digest(SSH_KEYGEN.read_bytes()),
            "--output",
            str(output),
        ]

    def release_archive_command(
        self,
        *,
        repo: Path,
        manifest: Path,
        signature: Path,
        allowed: Path,
        fingerprint: str,
        output: Path,
    ) -> list[str]:
        return [
            "release-archive",
            "--repo",
            str(repo),
            "--manifest",
            str(manifest),
            "--manifest-signature",
            str(signature),
            "--content-public-key",
            str(self.root / "external/content-signing.pub"),
            "--content-allowed-signers",
            str(allowed),
            "--expected-content-fingerprint",
            fingerprint,
            "--git",
            str(GIT),
            "--git-sha256",
            digest(GIT.read_bytes()),
            "--ssh-keygen",
            str(SSH_KEYGEN),
            "--ssh-keygen-sha256",
            digest(SSH_KEYGEN.read_bytes()),
            "--output",
            str(output),
        ]

    def test_install_inventory_is_canonical_and_manifest_bound(self) -> None:
        output = self.root / "install-inventory.json"
        completed = self.run_builder(
            "install-inventory",
            "--manifest",
            str(self.manifest),
            "--output",
            str(output),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

        manifest_data = self.manifest.read_bytes()
        expected = {
            "authority": "pre-install-expectation-only",
            "manifest": {
                "manifestSequence": 2,
                "sha256": digest(manifest_data),
                "size": len(manifest_data),
            },
            "release": "2.0.4",
            "schema": "idc-skills-install-inventory/v1",
            "skills": {"count": 50, "names": self.names},
            "targets": [
                {
                    "label": label,
                    "releaseParity": "required",
                }
                for label in ROOT_LABELS
            ],
        }
        self.assertEqual(output.read_bytes(), canonical(expected))

    def test_trust_and_freshness_parsers_share_manifest_wire_contract(self) -> None:
        manifest_data = self.manifest.read_bytes()
        trust_identity = trust.parse_manifest_identity(manifest_data)
        fresh_manifest = fresh.parse_manifest(manifest_data)
        self.assertEqual(trust_identity["release"], fresh_manifest["release"])
        self.assertEqual(
            trust_identity["manifestSequence"], fresh_manifest["manifestSequence"]
        )
        compact = canonical(self.manifest_value)
        with self.assertRaises(trust.TrustError):
            trust.parse_manifest_identity(compact)
        with self.assertRaises(fresh.FreshnessError):
            fresh.parse_manifest(compact)

    def test_registry_parser_accepts_the_committed_producer_format(self) -> None:
        registry = trust.parse_registry((REPO / "skills/registry.json").read_bytes())
        self.assertEqual(registry["release"], "2.0.4")
        self.assertEqual(registry["manifestSequence"], 2)
        self.assertEqual(len(registry["skills"]), 50)

    def test_trust_and_freshness_parsers_share_release_index_contract(self) -> None:
        now = dt.datetime(2026, 8, 24, 0, 0, tzinfo=dt.timezone.utc)
        entry = {
            "gitCommit": "a" * 40,
            "launcherSHA256": "sha256:" + "b" * 64,
            "manifestSHA256": "sha256:" + "c" * 64,
            "manifestSequence": 1,
            "release": "2.0.3",
            "verifierSHA256": "sha256:" + "d" * 64,
        }
        base = {
            "generatedAt": "2026-08-23T12:00:00Z",
            "indexSequence": 1,
            "releases": [entry],
            "schema": "idc-skills-release-index/v1",
            "validUntil": "2026-09-22T12:00:00Z",
        }
        data = index_canonical(base)
        self.assertEqual(
            trust.parse_release_index(data, now=now)["releases"],
            fresh.parse_index(data, now=now)["releases"],
        )
        invalid_values = []
        for mutation in (
            {**base, "indexSequence": True},
            {**base, "unexpected": "field"},
            {**base, "validUntil": "2026-10-22T12:00:00Z"},
        ):
            invalid_values.append(index_canonical(mutation))
        bad_commit = json.loads(json.dumps(base))
        bad_commit["releases"][0]["gitCommit"] = "not-a-commit"
        invalid_values.append(index_canonical(bad_commit))
        for invalid in invalid_values:
            with self.subTest(invalid=invalid[:80]):
                with self.assertRaises(trust.TrustError):
                    trust.parse_release_index(invalid, now=now)
                with self.assertRaises(fresh.FreshnessError):
                    fresh.parse_index(invalid, now=now)

    def test_release_index_genesis_is_derived_and_canonical(self) -> None:
        repo, manifest, signature, allowed, _key, commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.3", manifest_sequence=1)
        )
        output = self.root / "external" / "releases.json"
        command = self.release_index_command(
            repo=repo,
            manifest=manifest,
            signature=signature,
            allowed=allowed,
            fingerprint=fingerprint,
            output=output,
        )
        completed = self.run_builder(
            *command,
            "--genesis",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        manifest_data = manifest.read_bytes()
        expected = {
            "generatedAt": self.generated_at,
            "indexSequence": 1,
            "releases": [
                {
                    "gitCommit": commit,
                    "launcherSHA256": digest(
                        (repo / "bootstrap/idc_verify_fresh.py").read_bytes()
                    ),
                    "manifestSHA256": digest(manifest_data),
                    "manifestSequence": 1,
                    "release": "2.0.3",
                    "verifierSHA256": digest(
                        (repo / "scripts/skill_integrity.py").read_bytes()
                    ),
                }
            ],
            "schema": "idc-skills-release-index/v1",
            "validUntil": self.valid_until,
        }
        self.assertEqual(output.read_bytes(), index_canonical(expected))

    def test_release_archive_builder_is_deterministic_and_exact(self) -> None:
        repo, manifest, signature, allowed, _key, _commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.4", manifest_sequence=2)
        )
        first = self.root / "external/idc-skills-2.0.4-a.tar.gz"
        second = self.root / "external/idc-skills-2.0.4-b.tar.gz"
        one = self.run_builder(
            *self.release_archive_command(
                repo=repo,
                manifest=manifest,
                signature=signature,
                allowed=allowed,
                fingerprint=fingerprint,
                output=first,
            )
        )
        two = self.run_builder(
            *self.release_archive_command(
                repo=repo,
                manifest=manifest,
                signature=signature,
                allowed=allowed,
                fingerprint=fingerprint,
                output=second,
            )
        )
        self.assertEqual(one.returncode, 0, one.stderr)
        self.assertEqual(two.returncode, 0, two.stderr)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        identity = trust.parse_manifest_identity(manifest.read_bytes())
        trust.validate_release_archive(
            first.read_bytes(),
            identity,
            manifest.read_bytes(),
            signature.read_bytes(),
            "2.0.4",
            git_tree=trust.git_tree_entries(GIT, repo),
        )

    def test_release_index_refuses_to_overwrite_output(self) -> None:
        repo, manifest, signature, allowed, _key, _commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.3", manifest_sequence=1)
        )
        output = self.root / "external/releases.json"
        output.write_bytes(b"existing authority bytes\n")
        command = self.release_index_command(
            repo=repo,
            manifest=manifest,
            signature=signature,
            allowed=allowed,
            fingerprint=fingerprint,
            output=output,
        )
        completed = self.run_builder(*command, "--genesis")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("refusing to overwrite", completed.stderr)
        self.assertEqual(output.read_bytes(), b"existing authority bytes\n")

    def test_release_index_refuses_validity_longer_than_31_days(self) -> None:
        repo, manifest, signature, allowed, _key, _commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.3", manifest_sequence=1)
        )
        output = self.root / "external/releases.json"
        command = self.release_index_command(
            repo=repo,
            manifest=manifest,
            signature=signature,
            allowed=allowed,
            fingerprint=fingerprint,
            output=output,
        )
        generated = dt.datetime.strptime(
            self.generated_at, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=dt.timezone.utc)
        command[command.index("--valid-until") + 1] = (
            generated + dt.timedelta(days=32)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
        completed = self.run_builder(*command, "--genesis")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("validity window exceeds 31 days", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_index_preserves_signed_checkpointed_history(self) -> None:
        repo, manifest, signature, allowed, key, commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.4", manifest_sequence=2)
        )
        previous_entry = {
            "gitCommit": "a" * 40,
            "launcherSHA256": "sha256:" + "b" * 64,
            "manifestSHA256": "sha256:" + "c" * 64,
            "manifestSequence": 1,
            "release": "2.0.3",
            "verifierSHA256": "sha256:" + "d" * 64,
        }
        previous_value = {
            "generatedAt": "2026-07-01T12:00:00Z",
            "indexSequence": 7,
            "releases": [previous_entry],
            "schema": "idc-skills-release-index/v1",
            "validUntil": "2026-07-31T12:00:00Z",
        }
        previous = self.root / "external/previous-releases.json"
        previous.write_bytes(index_canonical(previous_value))
        previous_signature = self.sign_path(
            previous, key, "idc-skills-release-index-v1"
        )
        checkpoint = self.root / "external/previous-checkpoint.json"
        checkpoint.write_bytes(
            index_canonical(
                {
                    "indexSHA256": digest(previous.read_bytes()),
                    "indexSequence": 7,
                    "releases": [previous_entry],
                    "schema": "idc-skills-freshness-checkpoint/v1",
                }
            )
        )
        output = self.root / "external/releases.json"
        command = self.release_index_command(
            repo=repo,
            manifest=manifest,
            signature=signature,
            allowed=allowed,
            fingerprint=fingerprint,
            output=output,
        )
        completed = self.run_builder(
            *command,
            "--previous-index",
            str(previous),
            "--previous-index-signature",
            str(previous_signature),
            "--previous-checkpoint",
            str(checkpoint),
            "--previous-checkpoint-sha256",
            digest(checkpoint.read_bytes()),
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(value["indexSequence"], 8)
        self.assertEqual(value["releases"][0], previous_entry)
        self.assertEqual(value["releases"][1]["release"], "2.0.4")
        self.assertEqual(value["releases"][1]["manifestSequence"], 2)
        self.assertEqual(value["releases"][1]["gitCommit"], commit)

    def test_release_index_rejects_checkpoint_that_does_not_name_previous_index(self) -> None:
        repo, manifest, signature, allowed, key, _commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.4", manifest_sequence=2)
        )
        previous_entry = {
            "gitCommit": "a" * 40,
            "launcherSHA256": "sha256:" + "b" * 64,
            "manifestSHA256": "sha256:" + "c" * 64,
            "manifestSequence": 1,
            "release": "2.0.3",
            "verifierSHA256": "sha256:" + "d" * 64,
        }
        previous = self.root / "external/previous-releases.json"
        previous.write_bytes(
            index_canonical(
                {
                    "generatedAt": "2026-07-01T12:00:00Z",
                    "indexSequence": 7,
                    "releases": [previous_entry],
                    "schema": "idc-skills-release-index/v1",
                    "validUntil": "2026-07-31T12:00:00Z",
                }
            )
        )
        previous_signature = self.sign_path(
            previous, key, "idc-skills-release-index-v1"
        )
        checkpoint = self.root / "external/previous-checkpoint.json"
        checkpoint.write_bytes(
            index_canonical(
                {
                    "indexSHA256": "sha256:" + "0" * 64,
                    "indexSequence": 7,
                    "releases": [previous_entry],
                    "schema": "idc-skills-freshness-checkpoint/v1",
                }
            )
        )
        output = self.root / "external/releases.json"
        command = self.release_index_command(
            repo=repo,
            manifest=manifest,
            signature=signature,
            allowed=allowed,
            fingerprint=fingerprint,
            output=output,
        )
        completed = self.run_builder(
            *command,
            "--previous-index",
            str(previous),
            "--previous-index-signature",
            str(previous_signature),
            "--previous-checkpoint",
            str(checkpoint),
            "--previous-checkpoint-sha256",
            digest(checkpoint.read_bytes()),
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("does not identify the supplied latest index", completed.stderr)
        self.assertFalse(output.exists())

    def run_release_payload_fixture(
        self,
        *,
        inventory_release: str = "2.0.4",
        expires: str | None = None,
        git_tree_override: str | None = None,
        archive_extra: tuple[str, bytes] | None = None,
        corrupt_index_signature: bool = False,
        corrupt_manifest_signature: bool = False,
    ) -> tuple[subprocess.CompletedProcess[str], Path]:
        repo, manifest, signature, allowed, key, commit, fingerprint = (
            self.prepare_signed_repository(release="2.0.4", manifest_sequence=2)
        )
        expires = expires or self.valid_until
        manifest_data = manifest.read_bytes()
        archive = self.root / "external/archive.tar.gz"
        archive.write_bytes(
            release_archive_bytes(
                repo, manifest_data, "2.0.4", extra=archive_extra
            )
        )
        index = self.root / "external/releases.json"
        index.write_bytes(
            index_canonical(
                {
                    "generatedAt": self.generated_at,
                    "indexSequence": 2,
                    "releases": [
                        {
                            "gitCommit": commit,
                            "launcherSHA256": digest(
                                (repo / "bootstrap/idc_verify_fresh.py").read_bytes()
                            ),
                            "manifestSHA256": digest(manifest_data),
                            "manifestSequence": 2,
                            "release": "2.0.4",
                            "verifierSHA256": digest(
                                (repo / "scripts/skill_integrity.py").read_bytes()
                            ),
                        }
                    ],
                    "schema": "idc-skills-release-index/v1",
                    "validUntil": self.valid_until,
                }
            )
        )
        index_signature = self.sign_path(
            index, key, "idc-skills-release-index-v1"
        )
        if corrupt_index_signature:
            index_signature.write_bytes(b"not an OpenSSH signature\n")
        if corrupt_manifest_signature:
            signature.write_bytes(b"not an OpenSSH signature\n")
        inventory_value = trust.build_install_inventory(manifest_data)
        inventory_value["release"] = inventory_release
        inventory = self.root / "external/install-inventory.json"
        inventory.write_bytes(trust.canonical_json(inventory_value))
        tree = subprocess.check_output(
            [str(GIT), "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True
        ).strip()
        output = self.root / "external/release-payload.json"
        completed = self.run_builder(
            "release-payload",
            "--repo",
            str(repo),
            "--release",
            "2.0.4",
            "--release-sequence",
            "2",
            "--root-version",
            "1",
            "--expires",
            expires,
            "--git-commit",
            commit,
            "--git-tree",
            git_tree_override or tree,
            "--archive",
            str(archive),
            "--freshness-index",
            str(index),
            "--freshness-index-signature",
            str(index_signature),
            "--install-inventory",
            str(inventory),
            "--manifest",
            str(manifest),
            "--manifest-signature",
            str(signature),
            "--registry",
            str(repo / "skills/registry.json"),
            "--content-public-key",
            str(self.root / "external/content-signing.pub"),
            "--content-allowed-signers",
            str(allowed),
            "--expected-content-fingerprint",
            fingerprint,
            "--git",
            str(GIT),
            "--git-sha256",
            digest(GIT.read_bytes()),
            "--ssh-keygen",
            str(SSH_KEYGEN),
            "--ssh-keygen-sha256",
            digest(SSH_KEYGEN.read_bytes()),
            "--output",
            str(output),
        )
        return completed, output

    def test_release_payload_rejects_inventory_for_another_release(self) -> None:
        completed, output = self.run_release_payload_fixture(
            inventory_release="9.9.9"
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("signed manifest expectation", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_payload_rejects_expired_metadata_before_signing(self) -> None:
        completed, output = self.run_release_payload_fixture(
            expires=self.expired_at
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("release payload is already expired", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_payload_rejects_threshold_bound_archive_extra(self) -> None:
        completed, output = self.run_release_payload_fixture(
            archive_extra=("unexpected.txt", b"not in the signed tree\n")
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("archive", completed.stderr.lower())
        self.assertFalse(output.exists())

    def test_release_payload_rejects_wrong_git_tree_before_signing(self) -> None:
        completed, output = self.run_release_payload_fixture(
            git_tree_override="0" * 40
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("tree differs", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_payload_rejects_invalid_index_signature_before_signing(self) -> None:
        completed, output = self.run_release_payload_fixture(
            corrupt_index_signature=True
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("release-index signature verification", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_payload_rejects_invalid_manifest_signature_before_signing(self) -> None:
        completed, output = self.run_release_payload_fixture(
            corrupt_manifest_signature=True
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("manifest signature verification", completed.stderr)
        self.assertFalse(output.exists())

    def test_release_payload_builder_emits_semantically_joined_payload(self) -> None:
        completed, output = self.run_release_payload_fixture()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        value = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(value["release"], "2.0.4")
        self.assertEqual(value["git"]["tag"], "2.0.4")
        self.assertEqual(
            value["artifacts"]["archive"]["sha256"],
            digest((self.root / "external/archive.tar.gz").read_bytes()),
        )


if __name__ == "__main__":
    unittest.main()
