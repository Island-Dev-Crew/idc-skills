from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import skill_integrity


REPO = Path(__file__).resolve().parents[1]


def write_executable(path: Path, body: str) -> None:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body, encoding="utf-8")
    path.chmod(0o755)


def load_integrity_hook():
    hook = REPO / "scripts/pretooluse-skill-integrity.py"
    spec = importlib.util.spec_from_file_location("idc_integrity_hook_test", hook)
    if spec is None or spec.loader is None:
        raise AssertionError("could not load integrity hook")
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, {"skill_integrity": skill_integrity}):
        spec.loader.exec_module(module)
    return module


class SecurityScriptTests(unittest.TestCase):
    def test_integrity_hook_requires_installed_skill_root(self) -> None:
        process = subprocess.run(
            [
                sys.executable,
                str(REPO / "scripts/pretooluse-skill-integrity.py"),
                "--repo-root",
                str(REPO),
                "--skill",
                "short",
            ],
            input="{}",
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(process.returncode, 2)
        self.assertIn("--installed-skills", process.stderr)

    def test_integrity_hook_blocks_red_gate_unknown_skill_and_installed_drift(self) -> None:
        module = load_integrity_hook()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installed = root / "installed"
            installed.mkdir()
            shutil.copytree(REPO / "skills" / "short", installed / "short")
            source = installed / "short"
            expected = {
                path.relative_to(source).as_posix(): skill_integrity._file_record(path)
                for path in skill_integrity._walk_regular_files(source)
            }
            verified = {
                "readyToRun": True,
                "score": "5/5",
                "_verifiedManifest": {
                    "skills": {"short": {"files": expected}}
                },
            }

            def invoke(
                report: dict[str, object],
                skill: str,
                payload: dict[str, object] | None = None,
            ) -> tuple[int, str, str]:
                output = io.StringIO()
                error = io.StringIO()
                with mock.patch.object(
                    module, "_read_payload", return_value=payload or {}
                ):
                    with mock.patch.object(
                        module.skill_integrity,
                        "verify_repository",
                        return_value=copy.deepcopy(report),
                    ):
                        with contextlib.redirect_stdout(output):
                            with contextlib.redirect_stderr(error):
                                exit_code = module.main(
                                    [
                                        "--repo-root",
                                        str(REPO),
                                        "--installed-skills",
                                        str(installed),
                                        "--skill",
                                        skill,
                                    ]
                                )
                return exit_code, output.getvalue(), error.getvalue()

            red_code, _, red_error = invoke(
                {"readyToRun": False, "score": "0/5"}, "short"
            )
            self.assertEqual(red_code, 2)
            self.assertIn("integrity gate is 0/5", red_error)

            ready_code, ready_output, ready_error = invoke(verified, "short")
            self.assertEqual(ready_code, 0, ready_error)
            self.assertIn("READY 5/5", ready_output)

            unknown_code, _, unknown_error = invoke(verified, "not-in-forge")
            self.assertEqual(unknown_code, 2)
            self.assertIn("unknown or unreadable skill", unknown_error)

            mismatch_code, _, mismatch_error = invoke(
                verified, "short", {"skill": "research"}
            )
            self.assertEqual(mismatch_code, 2)
            self.assertIn("explicit skill and hook payload disagree", mismatch_error)

            (installed / "short" / "SKILL.md").write_bytes(b"poisoned\n")
            drift_code, _, drift_error = invoke(verified, "short")
            self.assertEqual(drift_code, 2)
            self.assertIn("installed bytes drifted", drift_error)
            for message in (
                red_error,
                ready_output,
                ready_error,
                unknown_error,
                mismatch_error,
                drift_error,
            ):
                message.encode("ascii")

    def test_integrity_hook_unexpected_exception_is_blocking_exit_two(self) -> None:
        module = load_integrity_hook()

        error = io.StringIO()
        with mock.patch.object(module, "_authorize", side_effect=RuntimeError("secret")):
            with contextlib.redirect_stderr(error):
                exit_code = module.main(["--installed-skills", str(REPO / "skills")])
        self.assertEqual(exit_code, 2)
        self.assertIn("integrity adapter failure: RuntimeError", error.getvalue())
        self.assertNotIn("secret", error.getvalue())

    def test_smoke_readiness_failure_writes_verdict_and_never_runs_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            write_executable(tools / "curl", "exit 1\n")
            write_executable(tools / "sleep", "exit 0\n")
            driver = root / "flow.sh"
            write_executable(driver, "touch driver-ran\n")
            environment = os.environ.copy()
            environment["PATH"] = f"{tools}:{environment['PATH']}"
            process = subprocess.run(
                [
                    "bash",
                    str(REPO / "skills/computer-use-smoke/scripts/smoke.sh"),
                    "http://127.0.0.1:4173/health",
                    "./flow.sh",
                ],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 3, process.stderr)
            self.assertFalse((root / "driver-ran").exists())
            verdicts = list((root / "build/smoke").glob("*/verdict.txt"))
            self.assertEqual(len(verdicts), 1)
            self.assertIn("STAGE=readiness", verdicts[0].read_text(encoding="utf-8"))

    def test_smoke_rejects_external_driver(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            process = subprocess.run(
                [
                    "bash",
                    str(REPO / "skills/computer-use-smoke/scripts/smoke.sh"),
                    "https://example.invalid/health",
                    "/bin/true",
                ],
                cwd=temporary,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 2)
            self.assertIn("flow driver", process.stderr)

    def test_video_grab_refuses_stale_output_and_failed_download(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            write_executable(
                tools / "yt-dlp",
                """
if [[ " $* " == *" --get-id "* ]]; then printf 'fixture-id\\n'; exit 0; fi
if [[ " $* " == *" --skip-download "* ]]; then exit 1; fi
exit 9
""",
            )
            write_executable(tools / "ffmpeg", "exit 0\n")
            write_executable(tools / "ffprobe", "printf '10.0\\n'\n")
            environment = os.environ.copy()
            environment["PATH"] = f"{tools}:{environment['PATH']}"
            script = REPO / "skills/video-analysis/scripts/grab.sh"

            stale = root / "stale"
            stale.mkdir()
            (stale / "source.mp4").write_bytes(b"old")
            stale_run = subprocess.run(
                ["bash", str(script), "https://youtu.be/fixture", "3", str(stale)],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(stale_run.returncode, 2)
            self.assertIn("refusing stale evidence", stale_run.stderr)

            failed = root / "fresh"
            failed_run = subprocess.run(
                ["bash", str(script), "https://youtu.be/fixture", "3", str(failed)],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(failed_run.returncode, 4)
            self.assertIn("download failed", failed_run.stderr)

    @unittest.skipIf(os.name == "nt", "POSIX mode assertion")
    def test_wizard_env_write_is_private_and_host_confirmed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            tools = root / "tools"
            tools.mkdir()
            write_executable(tools / "open", "exit 0\n")
            write_executable(tools / "gh", "exit 1\n")
            environment = os.environ.copy()
            environment["PATH"] = f"{tools}:{environment['PATH']}"
            environment["ENV_FILE"] = str(root / ".env")
            process = subprocess.run(
                ["bash", str(REPO / "skills/wizard/template.sh")],
                cwd=root,
                env=environment,
                input="y\n\nfixture-secret\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            env_file = root / ".env"
            self.assertEqual(stat.S_IMODE(env_file.stat().st_mode), 0o600)
            self.assertEqual(
                env_file.read_text(encoding="utf-8"), "EXAMPLE_API_KEY=fixture-secret\n"
            )


if __name__ == "__main__":
    unittest.main()
