from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
VERIFY_PATH = REPO / "skills/self-contained-ship/scripts/verify-egress-policy.py"
SCAN_PATH = REPO / "skills/self-contained-ship/scripts/scan-egress.sh"
SPEC = importlib.util.spec_from_file_location("verify_egress_policy", VERIFY_PATH)
assert SPEC and SPEC.loader
verify_egress_policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify_egress_policy)


@unittest.skipUnless(shutil.which("ssh-keygen"), "OpenSSH ssh-keygen is required")
class EgressPolicyTests(unittest.TestCase):
    revision = "a" * 40

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="idc-egress-policy-test-")
        self.root = Path(self.temporary.name)
        self.key = self.root / "waiver-key"
        subprocess.run(
            ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(self.key)],
            check=True,
            capture_output=True,
        )
        public_fields = self.key.with_suffix(".pub").read_text(encoding="utf-8").split()
        self.allowed = self.root / "allowed_signers"
        self.allowed.write_text(
            f"idc-egress-waiver {public_fields[0]} {public_fields[1]}\n",
            encoding="utf-8",
        )
        result = subprocess.run(
            ["ssh-keygen", "-E", "sha256", "-lf", str(self.key.with_suffix(".pub"))],
            check=True,
            capture_output=True,
            text=True,
        )
        self.fingerprint = result.stdout.split()[1]
        self.policy_path = self.root / "waivers.json"
        self.python = Path(sys.executable).resolve()
        self.ssh_keygen = Path(shutil.which("ssh-keygen") or "").resolve()
        self.python_digest = "sha256:" + hashlib.sha256(self.python.read_bytes()).hexdigest()
        self.ssh_keygen_digest = "sha256:" + hashlib.sha256(self.ssh_keygen.read_bytes()).hexdigest()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _stamp(value: dt.datetime) -> str:
        return value.astimezone(dt.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

    def _policy(self, waivers: list[dict[str, str]], *, expired: bool = False) -> dict[str, object]:
        now = dt.datetime.now(dt.timezone.utc)
        issued = now - dt.timedelta(hours=2 if expired else 1)
        expires = now - dt.timedelta(hours=1) if expired else now + dt.timedelta(hours=1)
        return {
            "schema": "idc-egress-waiver-policy/v1",
            "revision": self.revision,
            "issuedAt": self._stamp(issued),
            "expiresAt": self._stamp(expires),
            "waivers": waivers,
        }

    def _write_and_sign(self, policy: dict[str, object]) -> Path:
        self.policy_path.write_bytes(verify_egress_policy.canonical_bytes(policy))
        subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(self.key),
                "-n",
                "idc-egress-waiver",
                str(self.policy_path),
            ],
            check=True,
            capture_output=True,
        )
        return Path(str(self.policy_path) + ".sig")

    def _scan(
        self,
        artifact: Path,
        signature: Path | None = None,
        *,
        environment: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        args = ["/bin/bash", str(SCAN_PATH)]
        if signature is not None:
            args.extend(
                [
                    "--waiver-policy",
                    str(self.policy_path),
                    "--waiver-signature",
                    str(signature),
                    "--waiver-allowed-signers",
                    str(self.allowed),
                    "--waiver-fingerprint",
                    self.fingerprint,
                    "--revision",
                    self.revision,
                    "--policy-root",
                    str(self.root),
                    "--waiver-python",
                    str(self.python),
                    "--waiver-python-sha256",
                    self.python_digest,
                    "--waiver-ssh-keygen",
                    str(self.ssh_keygen),
                    "--waiver-ssh-keygen-sha256",
                    self.ssh_keygen_digest,
                ]
            )
        else:
            args.extend(["--policy-root", str(self.root)])
        args.append(str(artifact))
        return subprocess.run(
            args,
            capture_output=True,
            text=True,
            check=False,
            cwd=self.root,
            env=environment,
        )

    def _waiver_for_output(self, artifact: Path, output: str) -> dict[str, str]:
        match = re.search(r"\[fingerprint=(sha256:[0-9a-f]{64})\]", output)
        self.assertIsNotNone(match, output)
        now = dt.datetime.now(dt.timezone.utc)
        return {
            "path": artifact.relative_to(self.root).as_posix(),
            "fileSha256": "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest(),
            "findingFingerprint": match.group(1),  # type: ignore[union-attr]
            "reviewer": "independent-security-reviewer",
            "reason": "Reviewed fixture endpoint required for this bounded test.",
            "expiresAt": self._stamp(now + dt.timedelta(minutes=30)),
        }

    def test_signed_policy_waives_exact_finding(self) -> None:
        artifact = self.root / "artifact.js"
        artifact.write_text('fetch("//telemetry.invalid/required")\n', encoding="utf-8")
        red = self._scan(artifact)
        self.assertEqual(red.returncode, 1, red.stdout + red.stderr)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        green = self._scan(artifact, signature)
        self.assertEqual(green.returncode, 0, green.stdout + green.stderr)
        self.assertIn("WAIVED", green.stdout)

    def test_artifact_change_invalidates_signed_waiver(self) -> None:
        artifact = self.root / "artifact.js"
        artifact.write_text('fetch("//one.invalid/a")\n', encoding="utf-8")
        red = self._scan(artifact)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        artifact.write_text('fetch("//two.invalid/b")\n', encoding="utf-8")
        changed = self._scan(artifact, signature)
        self.assertEqual(changed.returncode, 1, changed.stdout + changed.stderr)
        self.assertIn("EGRESS", changed.stdout)

    def test_policy_tampering_invalidates_signature(self) -> None:
        artifact = self.root / "artifact.js"
        artifact.write_text('fetch("//one.invalid/a")\n', encoding="utf-8")
        red = self._scan(artifact)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        self.policy_path.write_bytes(self.policy_path.read_bytes().replace(b"Reviewed", b"Altered!"))
        tampered = self._scan(artifact, signature)
        self.assertEqual(tampered.returncode, 1, tampered.stdout + tampered.stderr)
        self.assertIn("signature invalid", tampered.stderr)

    def test_expired_policy_is_rejected(self) -> None:
        signature = self._write_and_sign(self._policy([], expired=True))
        with self.assertRaisesRegex(verify_egress_policy.PolicyError, "expired"):
            verify_egress_policy.verify(
                self.policy_path,
                signature,
                self.allowed,
                self.fingerprint,
                self.revision,
                self.python,
                self.python_digest,
                self.ssh_keygen,
                self.ssh_keygen_digest,
            )

    def test_uncertainty_cannot_be_waived(self) -> None:
        artifact = self.root / "artifact.ts"
        artifact.write_text("type X =\n  string | number\n/[a//]/.test(x)\n", encoding="utf-8")
        red = self._scan(artifact)
        self.assertIn("UNCERT", red.stdout)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        still_red = self._scan(artifact, signature)
        self.assertEqual(still_red.returncode, 1, still_red.stdout + still_red.stderr)
        self.assertIn("UNCERT", still_red.stdout)

    def test_binary_waiver_is_signed_and_exact(self) -> None:
        artifact = self.root / "font.woff2"
        artifact.write_bytes(b"\x00\x01reviewed-font-bytes")
        red = self._scan(artifact)
        self.assertEqual(red.returncode, 1, red.stdout + red.stderr)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        green = self._scan(artifact, signature)
        self.assertEqual(green.returncode, 0, green.stdout + green.stderr)
        self.assertIn("WAIVED-BINARY", green.stdout)

    def test_signed_scan_ignores_path_shadowed_python(self) -> None:
        artifact = self.root / "artifact.js"
        artifact.write_text('fetch("//telemetry.invalid/required")\n', encoding="utf-8")
        red = self._scan(artifact)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        fake_bin = self.root / "fake-python-bin"
        fake_bin.mkdir()
        marker = self.root / "path-python-ran"
        fake_python = fake_bin / "python3"
        fake_python.write_text(f"#!/bin/sh\nprintf ran > {marker}\nexit 0\n", encoding="utf-8")
        fake_python.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
        result = self._scan(artifact, signature, environment=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "PATH-shadowed python3 executed")

    def test_signed_scan_ignores_path_shadowed_ssh_keygen(self) -> None:
        artifact = self.root / "artifact.js"
        artifact.write_text('fetch("//telemetry.invalid/required")\n', encoding="utf-8")
        red = self._scan(artifact)
        waiver = self._waiver_for_output(artifact, red.stdout + red.stderr)
        signature = self._write_and_sign(self._policy([waiver]))
        fake_bin = self.root / "fake-ssh-bin"
        fake_bin.mkdir()
        marker = self.root / "path-ssh-keygen-ran"
        fake_ssh = fake_bin / "ssh-keygen"
        fake_ssh.write_text(f"#!/bin/sh\nprintf ran > {marker}\nexit 0\n", encoding="utf-8")
        fake_ssh.chmod(0o755)
        environment = dict(os.environ)
        environment["PATH"] = str(fake_bin) + os.pathsep + environment.get("PATH", "")
        result = self._scan(artifact, signature, environment=environment)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists(), "PATH-shadowed ssh-keygen executed")


if __name__ == "__main__":
    unittest.main()
