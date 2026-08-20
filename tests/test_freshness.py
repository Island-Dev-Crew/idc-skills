from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from bootstrap import idc_verify_fresh as fresh


def _ssh_keygen_executable() -> str:
    """Prefer the native Windows OpenSSH tool over Git-for-Windows shims."""

    if os.name == "nt":
        system_root = os.environ.get("SystemRoot") or os.environ.get("WINDIR")
        if system_root:
            native = Path(system_root) / "System32" / "OpenSSH" / "ssh-keygen.exe"
            if native.is_file():
                return str(native.resolve())
    candidate = shutil.which("ssh-keygen")
    if candidate is None:
        raise RuntimeError("ssh-keygen is required for freshness tests")
    return str(Path(candidate).resolve())


def _sign(path: Path, private_key: Path, namespace: str) -> Path:
    signature = Path(str(path) + ".sig")
    if signature.exists():
        signature.unlink()
    subprocess.run(
        [
            "ssh-keygen",
            "-Y",
            "sign",
            "-f",
            str(private_key),
            "-n",
            namespace,
            str(path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return signature


class FreshnessFixture:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.repo = self.root / "repo"
        self.trust = self.root / "trust"
        self.runtime = self.root / "runtime"
        self.repo.mkdir()
        self.trust.mkdir(mode=0o700)
        self.runtime.mkdir(mode=0o700)
        (self.repo / "keys").mkdir()
        (self.repo / "integrity").mkdir()
        (self.repo / "scripts").mkdir()
        (self.repo / "bootstrap").mkdir()

        self.private_key = self.trust / "signing"
        self.ssh_keygen = _ssh_keygen_executable()
        self.git = str(Path(shutil.which("git") or "").resolve())
        self.python = str(Path(os.path.realpath(os.sys.executable)).resolve())
        subprocess.run(
            [
                self.ssh_keygen,
                "-q",
                "-t",
                "ed25519",
                "-N",
                "",
                "-f",
                str(self.private_key),
            ],
            check=True,
        )
        public = Path(str(self.private_key) + ".pub").read_bytes()
        self.public_key = self.repo / "keys" / "idc-skills-signing.pub"
        self.public_key.write_bytes(public)
        fields = public.decode("utf-8").split()
        self.allowed = self.repo / "keys" / "allowed_signers"
        self.allowed.write_text(
            f"{fresh.SIGN_IDENTITY} {fields[0]} {fields[1]}\n",
            encoding="utf-8",
        )
        self.fingerprint = fresh._fingerprint_public_key(
            f"{fields[0]} {fields[1]}\n", self.ssh_keygen
        )

        self.verifier = self.repo / "scripts" / "skill_integrity.py"
        self.verifier.write_text("# fixture verifier bytes\n", encoding="utf-8")
        self.installer = self.repo / "scripts" / "install.py"
        self.installer.write_text("# original installer bytes\n", encoding="utf-8")
        os.chmod(self.installer, 0o755)
        self.launcher_source = self.repo / "bootstrap" / "idc_verify_fresh.py"
        self.launcher_source.write_bytes(Path(fresh.__file__).read_bytes())
        repository_files = {}
        for path in (
            self.public_key,
            self.allowed,
            self.verifier,
            self.installer,
            self.launcher_source,
        ):
            relative = path.relative_to(self.repo).as_posix()
            data = path.read_bytes()
            repository_files[relative] = {
                "sha256": fresh.sha256_bytes(data),
                "size": len(data),
                "posixMode": path.stat().st_mode & 0o777,
            }
        self.manifest = self.repo / "integrity" / "manifest.json"
        self.manifest.write_bytes(
            fresh.canonical_bytes(
                {
                    "schema": fresh.MANIFEST_SCHEMA,
                    "profile": "release",
                    "release": "2.0.3",
                    "manifestSequence": 1,
                    "skillCount": 50,
                    "repositoryFiles": repository_files,
                }
            )
        )
        self.manifest_signature = _sign(
            self.manifest, self.private_key, fresh.MANIFEST_NAMESPACE
        )
        self.launcher = self.runtime / "idc-verify-fresh"
        self.launcher.write_bytes(self.launcher_source.read_bytes())
        os.chmod(self.launcher, 0o700)
        subprocess.run([self.git, "init", "-q", str(self.repo)], check=True)
        subprocess.run(
            [self.git, "-C", str(self.repo), "config", "user.email", "fixture@example.invalid"],
            check=True,
        )
        subprocess.run(
            [self.git, "-C", str(self.repo), "config", "user.name", "Fixture"],
            check=True,
        )
        subprocess.run([self.git, "-C", str(self.repo), "add", "."], check=True)
        subprocess.run(
            [self.git, "-C", str(self.repo), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        self.commit = subprocess.run(
            [self.git, "-C", str(self.repo), "rev-parse", "HEAD"],
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
        self.checkpoint = self.runtime / "state" / "checkpoint.json"
        self.index = self.trust / "releases.json"
        self.index_signature = Path(str(self.index) + ".sig")
        self.config = self.runtime / "freshness.json"
        self.now = dt.datetime(2026, 8, 19, 12, 0, tzinfo=dt.timezone.utc)
        self.entry = {
            "release": "2.0.3",
            "manifestSequence": 1,
            "manifestSHA256": fresh.sha256_bytes(self.manifest.read_bytes()),
            "verifierSHA256": fresh.sha256_bytes(self.verifier.read_bytes()),
            "launcherSHA256": fresh.sha256_bytes(self.launcher.read_bytes()),
            "gitCommit": self.commit,
        }
        self.write_index([self.entry])
        self.write_config()

    def write_index(
        self,
        releases: list[dict[str, object]],
        *,
        sequence: int = 1,
        namespace: str = fresh.INDEX_NAMESPACE,
        generated: str = "2026-08-19T11:00:00Z",
        valid_until: str = "2026-08-26T11:00:00Z",
    ) -> None:
        self.index.write_bytes(
            fresh.canonical_bytes(
                {
                    "schema": fresh.INDEX_SCHEMA,
                    "indexSequence": sequence,
                    "generatedAt": generated,
                    "validUntil": valid_until,
                    "releases": releases,
                }
            )
        )
        self.index_signature = _sign(self.index, self.private_key, namespace)

    def write_config(self, *, bootstrap_digest: str | None = None) -> None:
        self.config.write_bytes(
            fresh.canonical_bytes(
                {
                    "schema": fresh.CONFIG_SCHEMA,
                    "source": {
                        "type": "file",
                        "indexPath": str(self.index),
                        "signaturePath": str(self.index_signature),
                    },
                    "checkpointPath": str(self.checkpoint),
                    "bootstrapIndexSHA256": bootstrap_digest
                    or fresh.sha256_bytes(self.index.read_bytes()),
                    "minimumIndexSequence": 1,
                    "minimumManifestSequence": 1,
                    "requireGitCommit": True,
                    "executables": {
                        "python": {
                            "path": self.python,
                            "sha256": fresh.sha256_bytes(Path(self.python).read_bytes()),
                        },
                        "git": {
                            "path": self.git,
                            "sha256": fresh.sha256_bytes(Path(self.git).read_bytes()),
                        },
                        "sshKeygen": {
                            "path": self.ssh_keygen,
                            "sha256": fresh.sha256_bytes(Path(self.ssh_keygen).read_bytes()),
                        },
                    },
                    "consumerPath": [str(Path(self.python).parent)],
                    "consumerHome": str(self.runtime),
                }
            )
        )

    @staticmethod
    def content_runner(
        verifier: bytes,
        manifest: bytes,
        signature: bytes,
        public_key: bytes,
        allowed_signers: bytes,
        repo_root: Path,
        python_executable: str,
        ssh_keygen: str,
    ) -> dict[str, object]:
        del (
            verifier,
            manifest,
            signature,
            public_key,
            allowed_signers,
            repo_root,
            python_executable,
            ssh_keygen,
        )
        return {
            "schema": "idc-skill-integrity-report/v2",
            "contentReady": True,
            "score": "5/5",
            "profile": "release",
            "skillsChecked": 50,
            "authority": "content-only",
            "release": "2.0.3",
            "manifestSequence": 1,
        }

    def verify(self, **overrides: object) -> dict[str, object]:
        arguments: dict[str, object] = {
            "launcher_path": self.launcher,
            "expected_fingerprint": self.fingerprint,
            "now": self.now,
            "content_runner": self.content_runner,
        }
        arguments.update(overrides)
        return fresh.verify_release(self.repo, self.config, **arguments)  # type: ignore[arg-type]


def _prepare_real_content_fixture(fixture: FreshnessFixture) -> None:
    """Replace the stub fixture with a signed, real-verifier 50-skill release."""

    source_verifier = Path(__file__).resolve().parents[1] / "scripts" / "skill_integrity.py"
    verifier_source = source_verifier.read_text(encoding="utf-8")
    trusted_line = (
        f'EXPECTED_SIGNING_FINGERPRINT = "{fresh.EXPECTED_SIGNING_FINGERPRINT}"'
    )
    fixture_line = f'EXPECTED_SIGNING_FINGERPRINT = "{fixture.fingerprint}"'
    if verifier_source.count(trusted_line) != 1:
        raise AssertionError("fixture could not locate the verifier trust-anchor constant")
    fixture.verifier.write_text(
        verifier_source.replace(trusted_line, fixture_line),
        encoding="utf-8",
    )
    os.chmod(fixture.verifier, 0o755)

    skill_names = [f"fixture-skill-{index:02d}" for index in range(50)]
    skills_root = fixture.repo / "skills"
    skills_root.mkdir()
    for name in skill_names:
        directory = skills_root / name
        directory.mkdir()
        (directory / "SKILL.md").write_text(
            f"# {name}\n\nThis fixture skill contains no external instructions.\n",
            encoding="utf-8",
        )
    (skills_root / "registry.json").write_bytes(
        fresh.canonical_bytes(
            {
                "manifestSequence": 1,
                "release": "2.0.3",
                "skills": [{"name": name, "path": name} for name in skill_names],
            }
        )
    )

    policy = {
        "schema": "idc-skill-integrity-policy/v1",
        "profile": "release",
        "expectedSigningFingerprint": fixture.fingerprint,
        "expectedSkillCount": 50,
        "expectedSkills": skill_names,
        "externalReferences": [],
        "deniedPatternExceptions": [],
        "controlFiles": [],
    }
    (fixture.repo / "integrity" / "policy.json").write_bytes(
        fresh.canonical_bytes(policy)
    )

    required_controls = (
        ".gitattributes",
        ".github/workflows/validate.yml",
        "AGENTS.md",
        "bootstrap/idc_verify_fresh.py",
        "CONTEXT.md",
        "integrity/README.md",
        "scripts/install.py",
        "scripts/install.sh",
        "scripts/pretooluse-skill-integrity.py",
        "scripts/reaccept.py",
        "scripts/setup-signing-wizard.sh",
        "scripts/test-skill-integrity.sh",
        "tests/test_install.py",
        "tests/test_freshness.py",
        "tests/test_security_scripts.py",
        "tests/test_skill_integrity.py",
    )
    for relative in required_controls:
        path = fixture.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "bootstrap/idc_verify_fresh.py":
            path.write_bytes(Path(fresh.__file__).read_bytes())
        elif relative == ".gitattributes":
            path.write_text("# fixture attributes\n", encoding="utf-8")
        elif not path.exists():
            path.write_text(f"fixture control: {relative}\n", encoding="utf-8")

    subprocess.run([fixture.git, "-C", str(fixture.repo), "add", "."], check=True)
    subprocess.run(
        [
            fixture.git,
            "-C",
            str(fixture.repo),
            "commit",
            "-q",
            "-m",
            "real verifier fixture",
        ],
        check=True,
    )

    spec = importlib.util.spec_from_file_location(
        "fixture_skill_integrity", fixture.verifier
    )
    if spec is None or spec.loader is None:
        raise AssertionError("fixture verifier module could not be loaded")
    verifier_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier_module)
    tracked_paths = verifier_module._tracked_repository_paths(fixture.repo)
    manifest = verifier_module.build_manifest(
        fixture.repo,
        fixture.repo / "skills",
        fixture.repo / "integrity" / "policy.json",
        fetch_remotes=False,
        repository_file_paths=tracked_paths,
    )
    fixture.manifest.write_bytes(verifier_module.canonical_bytes(manifest))
    fixture.manifest_signature = _sign(
        fixture.manifest, fixture.private_key, fresh.MANIFEST_NAMESPACE
    )
    subprocess.run(
        [
            fixture.git,
            "-C",
            str(fixture.repo),
            "add",
            "integrity/manifest.json",
            "integrity/manifest.json.sig",
        ],
        check=True,
    )
    subprocess.run(
        [
            fixture.git,
            "-C",
            str(fixture.repo),
            "commit",
            "-q",
            "-m",
            "sign real verifier fixture",
        ],
        check=True,
    )
    fixture.commit = subprocess.run(
        [fixture.git, "-C", str(fixture.repo), "rev-parse", "HEAD"],
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    fixture.entry = {
        "release": "2.0.3",
        "manifestSequence": 1,
        "manifestSHA256": fresh.sha256_bytes(fixture.manifest.read_bytes()),
        "verifierSHA256": fresh.sha256_bytes(fixture.verifier.read_bytes()),
        "launcherSHA256": fresh.sha256_bytes(fixture.launcher.read_bytes()),
        "gitCommit": fixture.commit,
    }
    fixture.write_index([fixture.entry])
    fixture.write_config()


class FreshnessTests(unittest.TestCase):
    def test_signed_index_and_captured_content_are_both_required_for_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))

            report = fixture.verify()

            self.assertIs(report["readyToRun"], True)
            self.assertIs(report["freshnessVerified"], True)
            self.assertEqual(report["authority"], "external-signed-index")
            checkpoint = fresh.load_canonical_json(
                fixture.checkpoint.read_bytes(),
                "checkpoint",
                fresh.MAX_CHECKPOINT_BYTES,
            )
            self.assertEqual(checkpoint["indexSHA256"], report["indexSHA256"])

    def test_wrong_index_namespace_fails_before_content_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.write_index([fixture.entry], namespace=fresh.MANIFEST_NAMESPACE)
            fixture.write_config()
            runner = mock.Mock(side_effect=AssertionError("content runner must not execute"))

            with self.assertRaisesRegex(fresh.FreshnessError, "signature invalid"):
                fixture.verify(content_runner=runner)
            runner.assert_not_called()

    def test_verifier_digest_mismatch_fails_before_content_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.verifier.write_text("# rolled back or replaced\n", encoding="utf-8")
            runner = mock.Mock(side_effect=AssertionError("content runner must not execute"))

            with self.assertRaisesRegex(
                fresh.FreshnessError,
                "captured content verifier differs|signed repository file drifted|release tuple",
            ):
                fixture.verify(content_runner=runner)
            runner.assert_not_called()

    def test_captured_verifier_and_launcher_must_equal_signed_sources(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            runner = mock.Mock(side_effect=AssertionError("content runner must not execute"))

            fixture.launcher.write_bytes(b"# separately indexed but unreviewed launcher\n")
            fixture.entry["launcherSHA256"] = fresh.sha256_bytes(
                fixture.launcher.read_bytes()
            )
            fixture.write_index([fixture.entry])
            fixture.write_config()
            with self.assertRaisesRegex(
                fresh.FreshnessError, "captured freshness launcher differs"
            ):
                fixture.verify(content_runner=runner)
            runner.assert_not_called()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            captured_verifier = b"# separately indexed but unreviewed verifier\n"
            fixture.entry["verifierSHA256"] = fresh.sha256_bytes(captured_verifier)
            fixture.write_index([fixture.entry])
            fixture.write_config()
            original_snapshot = fresh._read_regular_snapshot
            supplied = False

            def split_snapshot(
                path: Path,
                label: str,
                maximum: int,
                *,
                require_single_link: bool = False,
            ) -> bytes:
                nonlocal supplied
                if path == fixture.verifier and label == "content verifier" and not supplied:
                    supplied = True
                    return captured_verifier
                return original_snapshot(
                    path,
                    label,
                    maximum,
                    require_single_link=require_single_link,
                )

            with (
                mock.patch.object(fresh, "_read_regular_snapshot", split_snapshot),
                self.assertRaisesRegex(
                    fresh.FreshnessError, "captured content verifier differs"
                ),
            ):
                fixture.verify(content_runner=runner)
            runner.assert_not_called()

    def test_git_commit_rejects_extra_blob_drift_and_mode_drift(self) -> None:
        def commit_head(fixture: FreshnessFixture, message: str) -> str:
            subprocess.run(
                [fixture.git, "-C", str(fixture.repo), "commit", "-q", "-m", message],
                check=True,
            )
            return subprocess.run(
                [fixture.git, "-C", str(fixture.repo), "rev-parse", "HEAD"],
                text=True,
                capture_output=True,
                check=True,
            ).stdout.strip()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            (fixture.repo / "EXTRA.txt").write_text("not in signed closure\n", encoding="utf-8")
            subprocess.run(
                [fixture.git, "-C", str(fixture.repo), "add", "EXTRA.txt"], check=True
            )
            fixture.entry["gitCommit"] = commit_head(fixture, "unexpected tracked file")
            fixture.write_index([fixture.entry])
            fixture.write_config()
            with self.assertRaisesRegex(
                fresh.FreshnessError, "signed repository closure differs"
            ):
                fixture.verify()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            changed = b"# signed live installer bytes absent from committed blob\n"
            fixture.installer.write_bytes(changed)
            manifest = fresh.load_canonical_json(
                fixture.manifest.read_bytes(), "manifest", fresh.MAX_MANIFEST_BYTES
            )
            manifest["repositoryFiles"]["scripts/install.py"] = {
                "sha256": fresh.sha256_bytes(changed),
                "size": len(changed),
                "posixMode": 0o755,
            }
            fixture.manifest.write_bytes(fresh.canonical_bytes(manifest))
            fixture.manifest_signature = _sign(
                fixture.manifest, fixture.private_key, fresh.MANIFEST_NAMESPACE
            )
            subprocess.run(
                [
                    fixture.git,
                    "-C",
                    str(fixture.repo),
                    "add",
                    "integrity/manifest.json",
                    "integrity/manifest.json.sig",
                ],
                check=True,
            )
            fixture.entry["gitCommit"] = commit_head(fixture, "manifest without blob")
            fixture.entry["manifestSHA256"] = fresh.sha256_bytes(
                fixture.manifest.read_bytes()
            )
            fixture.write_index([fixture.entry])
            fixture.write_config()
            with self.assertRaisesRegex(
                fresh.FreshnessError,
                "signed bytes differ from Git tree object: scripts/install.py",
            ):
                fixture.verify()

        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            subprocess.run(
                [
                    fixture.git,
                    "-C",
                    str(fixture.repo),
                    "update-index",
                    "--chmod=-x",
                    "scripts/install.py",
                ],
                check=True,
            )
            fixture.entry["gitCommit"] = commit_head(fixture, "mode-only drift")
            fixture.write_index([fixture.entry])
            fixture.write_config()
            with self.assertRaisesRegex(
                fresh.FreshnessError, "signed POSIX mode differs from Git tree"
            ):
                fixture.verify()

    def test_first_run_requires_externally_pinned_exact_index_digest(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.write_config(bootstrap_digest="sha256:" + "0" * 64)

            with self.assertRaisesRegex(fresh.FreshnessError, "first-run index"):
                fixture.verify()
            self.assertFalse(fixture.checkpoint.exists())

    def test_same_sequence_equivocation_and_history_rewrite_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.verify()
            accepted = fixture.index.read_bytes()
            accepted_digest = fresh.sha256_bytes(accepted)
            checkpoint = fixture.checkpoint.read_bytes()

            changed = {**fixture.entry, "gitCommit": "b" * 40}
            fixture.write_index([changed], sequence=1)
            equivocated = fresh.parse_index(fixture.index.read_bytes(), now=fixture.now)
            with self.assertRaisesRegex(fresh.FreshnessError, "equivocation"):
                fresh.validate_checkpoint(
                    checkpoint,
                    equivocated,
                    fresh.sha256_bytes(fixture.index.read_bytes()),
                    accepted_digest,
                )

            newer = {**fixture.entry, "manifestSequence": 2, "release": "2.0.4"}
            fixture.write_index([newer], sequence=2)
            rewritten = fresh.parse_index(fixture.index.read_bytes(), now=fixture.now)
            with self.assertRaisesRegex(fresh.FreshnessError, "rewrote or removed"):
                fresh.validate_checkpoint(
                    checkpoint,
                    rewritten,
                    fresh.sha256_bytes(fixture.index.read_bytes()),
                    accepted_digest,
                )

    def test_external_authority_paths_may_not_resolve_inside_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            in_tree_launcher = fixture.repo / "bootstrap.py"
            in_tree_launcher.write_bytes(fixture.launcher.read_bytes())
            with self.assertRaisesRegex(fresh.FreshnessError, "outside the repository"):
                fixture.verify(launcher_path=in_tree_launcher)

            in_tree_index = fixture.repo / "releases.json"
            in_tree_index.write_bytes(fixture.index.read_bytes())
            in_tree_signature = Path(str(in_tree_index) + ".sig")
            in_tree_signature.write_bytes(fixture.index_signature.read_bytes())
            value = json.loads(fixture.config.read_text(encoding="utf-8"))
            value["source"]["indexPath"] = str(in_tree_index)
            value["source"]["signaturePath"] = str(in_tree_signature)
            fixture.config.write_bytes(fresh.canonical_bytes(value))
            with self.assertRaisesRegex(fresh.FreshnessError, "outside the repository"):
                fixture.verify()

            alternate_case_repo = fixture.repo.with_name(fixture.repo.name.swapcase())
            if alternate_case_repo.exists() and os.path.samefile(
                alternate_case_repo, fixture.repo
            ):
                alternate_launcher = alternate_case_repo / "case-alias-launcher.py"
                in_tree_launcher.write_bytes(fixture.launcher.read_bytes())
                in_tree_launcher.rename(fixture.repo / alternate_launcher.name)
                with self.assertRaisesRegex(
                    fresh.FreshnessError, "outside the repository"
                ):
                    fixture.verify(launcher_path=alternate_launcher)

    def test_release_config_requires_true_git_policy_and_pinned_runtime_digests(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            value = json.loads(fixture.config.read_text(encoding="utf-8"))
            value["requireGitCommit"] = False
            fixture.config.write_bytes(fresh.canonical_bytes(value))
            with self.assertRaisesRegex(fresh.FreshnessError, "must be true"):
                fixture.verify()

            value["requireGitCommit"] = True
            value["executables"]["python"]["sha256"] = "sha256:" + "0" * 64
            fixture.config.write_bytes(fresh.canonical_bytes(value))
            with self.assertRaisesRegex(fresh.FreshnessError, "digest differs"):
                fixture.verify()

    def test_candidate_git_fsmonitor_is_never_executed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            marker = fixture.runtime / "fsmonitor-executed"
            filter_marker = fixture.runtime / "filter-executed"
            hook = fixture.trust / "malicious-fsmonitor.sh"
            hook.write_text(
                "#!/bin/sh\nprintf executed > \"$1\"\nexit 0\n".replace("$1", str(marker)),
                encoding="utf-8",
            )
            os.chmod(hook, 0o700)
            clean_filter = fixture.trust / "malicious-filter.sh"
            clean_filter.write_text(
                "#!/bin/sh\nprintf executed > \"$1\"\ncat\n".replace(
                    "$1", str(filter_marker)
                ),
                encoding="utf-8",
            )
            os.chmod(clean_filter, 0o700)
            (fixture.repo / ".git" / "info" / "attributes").write_text(
                "scripts/install.py filter=evil\n", encoding="utf-8"
            )
            subprocess.run(
                [
                    fixture.git,
                    "-C",
                    str(fixture.repo),
                    "config",
                    "core.fsmonitor",
                    str(hook),
                ],
                check=True,
            )
            subprocess.run(
                [
                    fixture.git,
                    "-C",
                    str(fixture.repo),
                    "config",
                    "filter.evil.clean",
                    str(clean_filter),
                ],
                check=True,
            )

            report = fixture.verify()

            self.assertIs(report["readyToRun"], True)
            self.assertFalse(marker.exists())
            self.assertFalse(filter_marker.exists())

    def test_linked_or_external_git_metadata_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            external_git = fixture.runtime / "external.git"
            fixture.repo.joinpath(".git").rename(external_git)
            fixture.repo.joinpath(".git").write_text(
                f"gitdir: {external_git}\n", encoding="utf-8"
            )

            with self.assertRaisesRegex(fresh.FreshnessError, "Git metadata"):
                fixture.verify()

    def test_index_expiry_is_rechecked_before_checkpoint_transition(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.write_index(
                [fixture.entry],
                generated="2026-08-19T11:00:00Z",
                valid_until="2026-08-19T12:00:02Z",
            )
            fixture.write_config()
            clock = mock.Mock(
                side_effect=[
                    dt.datetime(2026, 8, 19, 12, 0, 0, tzinfo=dt.timezone.utc),
                    dt.datetime(2026, 8, 19, 12, 0, 3, tzinfo=dt.timezone.utc),
                ]
            )

            with self.assertRaisesRegex(fresh.FreshnessError, "expired"):
                fixture.verify(now=None, clock=clock)
            self.assertFalse(fixture.checkpoint.exists())

    def test_manifest_floor_and_ci_source_are_required_without_downgrade(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            value = json.loads(fixture.config.read_text(encoding="utf-8"))
            value["minimumManifestSequence"] = 2
            fixture.config.write_bytes(fresh.canonical_bytes(value))
            runner = mock.Mock(side_effect=AssertionError("content must not execute"))
            with self.assertRaisesRegex(fresh.FreshnessError, "manifest floor"):
                fixture.verify(content_runner=runner)
            runner.assert_not_called()

            value["minimumManifestSequence"] = 1
            fixture.config.write_bytes(fresh.canonical_bytes(value))
            fixture.index.unlink()
            fixture.index_signature.unlink()
            with self.assertRaisesRegex(fresh.FreshnessError, "release index"):
                fixture.verify(mode="ci", content_runner=runner)
            runner.assert_not_called()

    def test_offline_mode_is_content_only_and_has_distinct_nonready_exit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.index.unlink()
            fixture.index_signature.unlink()

            report = fixture.verify(mode="offline")

            self.assertIs(report["contentReady"], True)
            self.assertIs(report["readyToRun"], False)
            self.assertIs(report["freshnessVerified"], False)
            self.assertEqual(report["freshness"], "UNVERIFIED")
            self.assertFalse(fixture.checkpoint.exists())

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(fresh, "verify_release", return_value=report),
                contextlib.redirect_stdout(stdout),
                contextlib.redirect_stderr(stderr),
            ):
                exit_code = fresh.main(
                    [
                        "--repo-root",
                        str(fixture.repo),
                        "--config",
                        str(fixture.config),
                        "--mode",
                        "offline",
                        "verify",
                    ]
                )
            self.assertEqual(exit_code, 3)
            self.assertIn("FRESHNESS UNVERIFIED", stderr.getvalue())
            self.assertNotIn("READY 5/5", stdout.getvalue())

            def mutate_live_verifier(*args: object) -> dict[str, object]:
                report = FreshnessFixture.content_runner(*args)  # type: ignore[arg-type]
                fixture.verifier.write_text(
                    "# changed after the signed snapshot\n", encoding="utf-8"
                )
                return report

            with self.assertRaisesRegex(
                fresh.FreshnessError, "changed during offline content verification"
            ):
                fixture.verify(mode="offline", content_runner=mutate_live_verifier)

    def test_private_stage_excludes_ignored_bytes_and_preserves_signed_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            (fixture.repo / ".git" / "info" / "exclude").write_text(
                "*.pyc\n.env\n", encoding="utf-8"
            )
            ignored_cache = fixture.repo / "scripts" / "json.pyc"
            ignored_secret = fixture.repo / ".env"
            ignored_cache.write_bytes(b"attacker-controlled ignored cache")
            ignored_secret.write_text("TOKEN=must-not-stage\n", encoding="utf-8")

            def consumer(
                staged: Path, handoff: str, config: dict[str, object]
            ) -> int:
                del handoff, config
                self.assertFalse((staged / "scripts" / "json.pyc").exists())
                self.assertFalse((staged / ".env").exists())
                self.assertEqual(
                    (staged / "scripts" / "install.py").stat().st_mode & 0o777,
                    0o755,
                )
                fixture.installer.write_text("# post-stage mutation\n", encoding="utf-8")
                self.assertEqual(
                    (staged / "scripts" / "install.py").read_text(encoding="utf-8"),
                    "# original installer bytes\n",
                )
                return 0

            report = fixture.verify(consumer_runner=consumer)

            self.assertEqual(report["consumerExitCode"], 0)

    def test_consumer_rejects_root_abbreviation_and_strips_hostile_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            staged = root / "stage"
            scripts = staged / "scripts"
            scripts.mkdir(parents=True)
            capture = root / "capture.json"
            installer = scripts / "install.py"
            installer.write_text(
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "target = Path(sys.argv[sys.argv.index('--capture') + 1])\n"
                "target.write_text(json.dumps({'argv': sys.argv, 'env': dict(os.environ)}))\n",
                encoding="utf-8",
            )
            python = str(Path(os.path.realpath(os.sys.executable)).resolve())
            git = str(Path(shutil.which("git") or "").resolve())
            ssh_keygen = _ssh_keygen_executable()
            config: dict[str, object] = {
                "executables": {
                    "python": python,
                    "git": git,
                    "sshKeygen": ssh_keygen,
                },
                "consumerPath": [str(Path(python).parent)],
                "consumerHome": str(root),
            }
            abbreviated = argparse.Namespace(
                command="hook", consumer_args=["--repo-roo", str(root / "rollback")]
            )
            with self.assertRaisesRegex(fresh.FreshnessError, "override"):
                fresh._run_consumer(abbreviated, staged, "sha256:" + "a" * 64, config)

            args = argparse.Namespace(
                command="install",
                consumer_args=["--", "--capture", str(capture)],
            )
            hostile = {
                "PATH": str(root / "attacker-bin"),
                "PYTHONPATH": str(root / "attacker-python"),
                "LD_PRELOAD": str(root / "inject.so"),
                "DYLD_INSERT_LIBRARIES": str(root / "inject.dylib"),
                "BASH_ENV": str(root / "bash-env"),
                "NODE_OPTIONS": "--require=attacker.js",
                "SSL_CERT_FILE": str(root / "attacker-ca"),
                "GIT_CONFIG_COUNT": "1",
                "HOME": str(root / "attacker-home"),
                "TMPDIR": str(root / "attacker-tmp"),
            }
            with mock.patch.dict(os.environ, hostile, clear=False):
                exit_code = fresh._run_consumer(
                    args, staged, "sha256:" + "b" * 64, config
                )
            self.assertEqual(exit_code, 0)
            observed = json.loads(capture.read_text(encoding="utf-8"))
            self.assertEqual(observed["argv"][1:4], ["--repo-root", str(staged), "install"])
            self.assertEqual(
                observed["env"]["IDC_SKILLS_FRESHNESS_HANDOFF"],
                "sha256:" + "b" * 64,
            )
            for key in hostile:
                if key not in {"PATH", "HOME", "TMPDIR"}:
                    self.assertNotIn(key, observed["env"])
            self.assertNotIn(str(root / "attacker-bin"), observed["env"]["PATH"])
            self.assertEqual(observed["env"]["HOME"], str(root))
            self.assertNotEqual(observed["env"]["TMPDIR"], hostile["TMPDIR"])

    def test_failed_consumer_never_prints_launcher_readiness(self) -> None:
        report = {"consumerExitCode": 7, "readyToRun": True}
        stdout = io.StringIO()
        stderr = io.StringIO()
        with (
            mock.patch.object(fresh, "verify_release", return_value=report),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            exit_code = fresh.main(
                [
                    "--repo-root",
                    "/unused",
                    "--config",
                    "/unused",
                    "install",
                ]
            )
        self.assertEqual(exit_code, 7)
        self.assertNotIn("READY", stdout.getvalue())
        self.assertNotIn("READY", stderr.getvalue())

    def test_noncanonical_duplicate_unknown_and_invalid_index_values_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            canonical = fixture.index.read_bytes()
            with self.assertRaisesRegex(fresh.FreshnessError, "canonical"):
                fresh.parse_index(canonical.rstrip(b"\n"), now=fixture.now)

            duplicate = canonical.replace(
                b'  "indexSequence": 1,',
                b'  "indexSequence": 1,\n  "indexSequence": 1,',
            )
            with self.assertRaisesRegex(fresh.FreshnessError, "duplicate JSON key"):
                fresh.parse_index(duplicate, now=fixture.now)

            value = json.loads(canonical)
            value["unexpected"] = True
            with self.assertRaisesRegex(fresh.FreshnessError, "unknown"):
                fresh.parse_index(fresh.canonical_bytes(value), now=fixture.now)

            value = json.loads(canonical)
            value["indexSequence"] = True
            with self.assertRaisesRegex(fresh.FreshnessError, "integer"):
                fresh.parse_index(fresh.canonical_bytes(value), now=fixture.now)

    def test_expired_or_future_index_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            fixture.write_index(
                [fixture.entry],
                generated="2026-08-01T00:00:00Z",
                valid_until="2026-08-02T00:00:00Z",
            )
            with self.assertRaisesRegex(fresh.FreshnessError, "expired"):
                fresh.parse_index(fixture.index.read_bytes(), now=fixture.now)

            fixture.write_index(
                [fixture.entry],
                generated="2026-08-20T00:00:00Z",
                valid_until="2026-08-21T00:00:00Z",
            )
            with self.assertRaisesRegex(fresh.FreshnessError, "future"):
                fresh.parse_index(fixture.index.read_bytes(), now=fixture.now)

    def test_in_tree_ready_field_is_rejected_even_when_false(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))

            def runner(*args: object) -> dict[str, object]:
                del args
                return {
                    **fixture.content_runner(
                        b"",
                        b"",
                        b"",
                        b"",
                        b"",
                        fixture.repo,
                        fixture.python,
                        fixture.ssh_keygen,
                    ),
                    "readyToRun": False,
                }

            with self.assertRaisesRegex(fresh.FreshnessError, "improperly emitted"):
                fixture.verify(content_runner=runner)

    def test_real_captured_verifier_proves_content_before_external_readiness(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            fixture = FreshnessFixture(Path(temporary))
            _prepare_real_content_fixture(fixture)
            content_reports: list[dict[str, object]] = []

            def run_real_verifier(*args: object) -> dict[str, object]:
                report = fresh._run_content_verifier(*args)  # type: ignore[arg-type]
                content_reports.append(report)
                return report

            report = fixture.verify(content_runner=run_real_verifier)

            self.assertEqual(len(content_reports), 1)
            self.assertIs(content_reports[0]["contentReady"], True)
            self.assertEqual(content_reports[0]["authority"], "content-only")
            self.assertEqual(content_reports[0]["score"], "5/5")
            self.assertEqual(
                set(content_reports[0]["checks"]),
                {
                    "signature",
                    "local_bytes",
                    "external_reference_set",
                    "remote_content_pins",
                    "fetch_execute_policy",
                },
            )
            self.assertNotIn("readyToRun", content_reports[0])
            self.assertIs(report["readyToRun"], True)
            self.assertEqual(report["authority"], "external-signed-index")


if __name__ == "__main__":
    unittest.main()
