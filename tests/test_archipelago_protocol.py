from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
import unicodedata
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO / "skills/archipelago/protocol"


def write_loop_fixture(
    root: Path,
    *,
    gate_id: str = "P0-G4",
    stage: str = "S4",
    gate_command: str | None = None,
    gate_status: str = "passed",
) -> Path:
    mission = root / "ops/mission"
    mission.mkdir(parents=True)
    if gate_command is None:
        gate_command = f"{shlex.quote(sys.executable)} -c pass"
    idea_path = mission / "idea.lock.json"
    plan_path = mission / "plan.lock.json"
    idea_path.write_text("{}\n", encoding="utf-8")
    plan_path.write_text(
        json.dumps(
            {
                "phases": [
                    {
                        "id": "P0",
                        "gates": [
                            {
                                "id": gate_id,
                                "title": "fixture gate",
                                "command": gate_command,
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    digest = lambda path: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    state = {
        "mission": {"name": "fixture", "updated": ""},
        "phases": [
            {
                "id": "P0",
                "title": "fixture",
                "status": "in_progress",
                "gates": [
                    {
                        "id": gate_id,
                        "title": "fixture gate",
                        "command": gate_command,
                        "status": gate_status,
                        "evidence": None,
                        "lastRun": None,
                    }
                ],
            }
        ],
        "resume": {"activePhase": "P0"},
        "archipelago": {
            "ideaLock": "ops/mission/idea.lock.json",
            "ideaLockSHA256": digest(idea_path),
            "planLock": "ops/mission/plan.lock.json",
            "planLockSHA256": digest(plan_path),
            "loop": {"cycle": 1, "stage": stage, "loopbacks": []},
        },
    }
    (mission / "state.json").write_text(json.dumps(state), encoding="utf-8")
    return mission


class ArchipelagoProtocolTests(unittest.TestCase):
    def test_dependency_free_validator_checks_every_named_artifact(self) -> None:
        validator = PROTOCOL / "scripts/validate_contracts.py"
        good = PROTOCOL / "examples/idea.lock.json"
        with tempfile.TemporaryDirectory() as temporary:
            bad = Path(temporary) / "idea.lock.bad.json"
            value = json.loads(good.read_text(encoding="utf-8"))
            value["counterfeit"] = True
            bad.write_text(json.dumps(value), encoding="utf-8")
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(validator), str(good), str(bad)],
                text=True,
                capture_output=True,
                check=False,
            )
        self.assertEqual(process.returncode, 1)
        self.assertIn(f"[PASS] {good.name}", process.stdout)
        self.assertIn(f"[FAIL] {bad.name}", process.stdout)
        self.assertIn("unknown property 'counterfeit'", process.stdout)

        with tempfile.TemporaryDirectory() as temporary:
            duplicate = Path(temporary) / "idea.lock.duplicate.json"
            duplicate.write_text(
                good.read_text(encoding="utf-8").replace(
                    '"schemaVersion": "1.0",',
                    '"schemaVersion": "1.0", "schemaVersion": "1.0",',
                    1,
                ),
                encoding="utf-8",
            )
            refused = subprocess.run(
                [sys.executable, "-I", "-B", str(validator), str(duplicate)],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("duplicate JSON key", refused.stdout)

    def test_kickoff_validates_and_hash_binds_both_locks(self) -> None:
        kickoff = PROTOCOL / "scripts/kickoff.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = root / "ops/mission"
            mission.mkdir(parents=True)
            idea = mission / "idea.lock.json"
            plan = mission / "plan.lock.json"
            shutil.copy2(PROTOCOL / "examples/idea.lock.json", idea)
            shutil.copy2(PROTOCOL / "examples/plan.lock.json", plan)
            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(kickoff),
                    "--idea",
                    "ops/mission/idea.lock.json",
                    "--plan",
                    "ops/mission/plan.lock.json",
                    "--repo",
                    "fixture/repo",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            state = json.loads((mission / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(
                state["archipelago"]["ideaLockSHA256"],
                "sha256:" + hashlib.sha256(idea.read_bytes()).hexdigest(),
            )
            self.assertEqual(
                state["archipelago"]["planLockSHA256"],
                "sha256:" + hashlib.sha256(plan.read_bytes()).hexdigest(),
            )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = root / "ops/mission"
            mission.mkdir(parents=True)
            shutil.copy2(PROTOCOL / "examples/idea.lock.json", mission / "idea.lock.json")
            value = json.loads((PROTOCOL / "examples/plan.lock.json").read_text(encoding="utf-8"))
            value.pop("hitl")
            (mission / "plan.lock.json").write_text(json.dumps(value), encoding="utf-8")
            refused = subprocess.run(
                [sys.executable, "-I", "-B", str(kickoff), "--idea", "ops/mission/idea.lock.json", "--plan", "ops/mission/plan.lock.json", "--repo", "fixture/repo"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn("contract validation refused kickoff", refused.stderr)
            self.assertFalse((mission / "state.json").exists())

    def test_plan_schema_rejects_path_unsafe_gate_ids(self) -> None:
        validator = PROTOCOL / "scripts/validate_contracts.py"
        for gate_id in (
            "../../escaped-G4",
            "P0-G4-suffix",
            "P" + "9" * 300 + "-G4",
        ):
            with self.subTest(gate_id=gate_id), tempfile.TemporaryDirectory() as temporary:
                plan = Path(temporary) / "plan.lock.json"
                value = json.loads(
                    (PROTOCOL / "examples/plan.lock.json").read_text(encoding="utf-8")
                )
                value["phases"][0]["gates"][0]["id"] = gate_id
                plan.write_text(json.dumps(value), encoding="utf-8")
                process = subprocess.run(
                    [sys.executable, "-I", "-B", str(validator), str(plan)],
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(process.returncode, 0)
                self.assertIn("does not match required pattern", process.stdout)

    def test_loop_rejects_unsafe_gate_ids_before_evidence_path_construction(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = write_loop_fixture(root, gate_id="../../escaped-G4")
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("unsafe gate id", process.stderr)
            self.assertEqual(list((root / "ops").glob("escaped-G4-*.txt")), [])
            self.assertFalse((mission / "ledger.jsonl").exists())

    def test_oversized_gate_id_is_rejected_before_command_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "command-ran"
            command = (
                f"{shlex.quote(sys.executable)} -c "
                + shlex.quote(
                    "from pathlib import Path; Path('command-ran').write_text('ran')"
                )
            )
            mission = write_loop_fixture(
                root,
                gate_id="P" + "9" * 300 + "-G4",
                gate_command=command,
                gate_status="pending",
            )
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("unsafe gate id", process.stderr)
            self.assertFalse(marker.exists())
            self.assertFalse((mission / "ledger.jsonl").exists())

    @unittest.skipIf(os.name == "nt", "read-only directory fixture requires POSIX")
    def test_evidence_open_failure_prevents_command_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "command-ran"
            command = (
                f"{shlex.quote(sys.executable)} -c "
                + shlex.quote(
                    "from pathlib import Path; Path('command-ran').write_text('ran')"
                )
            )
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            evidence = mission / "evidence"
            evidence.mkdir()
            evidence.chmod(0o500)
            try:
                process = subprocess.run(
                    [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                    cwd=root,
                    text=True,
                    capture_output=True,
                    check=False,
                )
            finally:
                evidence.chmod(0o700)
            self.assertNotEqual(process.returncode, 0)
            self.assertFalse(marker.exists())
            self.assertFalse((mission / "ledger.jsonl").exists())

    @unittest.skipIf(os.name == "nt", "directory symlink fixture requires POSIX")
    def test_symlinked_evidence_directory_is_rejected_before_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "command-ran"
            command = (
                f"{shlex.quote(sys.executable)} -c "
                + shlex.quote(
                    "from pathlib import Path; Path('command-ran').write_text('ran')"
                )
            )
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            outside = root / "outside"
            outside.mkdir()
            (mission / "evidence").symlink_to(outside, target_is_directory=True)
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("evidence directory", process.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(list(outside.iterdir()), [])
            self.assertFalse((mission / "ledger.jsonl").exists())

    @unittest.skipIf(os.name == "nt", "file symlink fixture requires POSIX")
    def test_symlinked_ledger_is_rejected_before_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "command-ran"
            command = (
                f"{shlex.quote(sys.executable)} -c "
                + shlex.quote(
                    "from pathlib import Path; Path('command-ran').write_text('ran')"
                )
            )
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            outside_ledger = root / "outside-ledger.jsonl"
            outside_ledger.write_bytes(b"")
            (mission / "ledger.jsonl").symlink_to(outside_ledger)
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("ledger", process.stderr)
            self.assertFalse(marker.exists())
            self.assertEqual(outside_ledger.read_bytes(), b"")

    @unittest.skipIf(os.name == "nt", "file symlink fixture requires POSIX")
    def test_symlinked_state_is_rejected_before_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            marker = root / "command-ran"
            command = (
                f"{shlex.quote(sys.executable)} -c "
                + shlex.quote(
                    "from pathlib import Path; Path('command-ran').write_text('ran')"
                )
            )
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            state_path = mission / "state.json"
            outside_state = root / "outside-state.json"
            outside_state.write_bytes(state_path.read_bytes())
            state_path.unlink()
            state_path.symlink_to(outside_state)
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("state.json", process.stderr)
            self.assertFalse(marker.exists())

    def test_gate_observes_durable_start_record_before_execution(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            probe = (
                "import json; from pathlib import Path; "
                "p=Path('ops/mission/ledger.jsonl'); "
                "entries=[json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []; "
                "ok=bool(entries) and entries[-1].get('event')=='gate-start' and "
                "Path(entries[-1].get('evidence','')).is_file(); "
                "raise SystemExit(0 if ok else 7)"
            )
            command = f"{shlex.quote(sys.executable)} -c {shlex.quote(probe)}"
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            events = [
                json.loads(line)
                for line in (mission / "ledger.jsonl").read_text().splitlines()
            ]
            self.assertEqual([event["event"] for event in events], ["gate-start", "gate-run"])
            self.assertEqual(events[-1]["status"], "passed")

    def test_gate_output_is_bounded_and_streamed_to_evidence(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            noisy = (
                "import sys; "
                "sys.stdout.buffer.write(b'O'*(2*1024*1024)); "
                "sys.stderr.buffer.write(b'E'*(2*1024*1024))"
            )
            command = f"{shlex.quote(sys.executable)} -c {shlex.quote(noisy)}"
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            evidence = next((mission / "evidence").glob("P0-G4-*.txt"))
            self.assertLessEqual(evidence.stat().st_size, 1024 * 1024 + 64 * 1024)
            self.assertIn(b"truncated", evidence.read_bytes())

    def test_gate_timeout_terminates_and_records_failure(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            sleeper = "import time; time.sleep(2)"
            command = f"{shlex.quote(sys.executable)} -c {shlex.quote(sleeper)}"
            mission = write_loop_fixture(
                root, gate_command=command, gate_status="pending"
            )
            environment = dict(os.environ)
            environment["IDC_ARCHIPELAGO_GATE_TIMEOUT_SECONDS"] = "0.1"
            process = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                env=environment,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 1, process.stderr)
            evidence = next((mission / "evidence").glob("P0-G4-*.txt"))
            self.assertIn(b"timedOut true", evidence.read_bytes())
            events = [
                json.loads(line)
                for line in (mission / "ledger.jsonl").read_text().splitlines()
            ]
            self.assertTrue(events[-1]["timedOut"])
            state = json.loads((mission / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["phases"][0]["gates"][0]["status"], "failed")

    def test_fail_route_is_a_valid_non_forward_loopback_stage(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        state_schema = json.loads(
            (PROTOCOL / "schemas/state.extension.schema.json").read_text(encoding="utf-8")
        )
        route_enum = state_schema["properties"]["archipelago"]["properties"]["loop"][
            "properties"
        ]["loopbacks"]["items"]["properties"]["toStage"]["enum"]
        self.assertEqual(route_enum, [f"S{index}" for index in range(8)])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = write_loop_fixture(root, stage="S4")
            before = (mission / "state.json").read_bytes()

            invalid = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(loop),
                    "fail",
                    "P0-G4",
                    "--reason",
                    "fixture",
                    "--route",
                    "NOT-A-STAGE",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(invalid.returncode, 0)
            self.assertIn("invalid choice", invalid.stderr)
            self.assertEqual((mission / "state.json").read_bytes(), before)

            forward = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(loop),
                    "fail",
                    "P0-G4",
                    "--reason",
                    "fixture",
                    "--route",
                    "S7",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(forward.returncode, 0)
            self.assertIn("cannot move forward", forward.stderr)
            self.assertEqual((mission / "state.json").read_bytes(), before)
            self.assertFalse((mission / "ledger.jsonl").exists())

    def test_fallback_pulse_removes_c0_c1_and_unicode_format_controls(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = write_loop_fixture(root, stage="S4")
            state_path = mission / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            poisoned = "visible\x00\x85\u202e\u2066<script>"
            state["mission"]["name"] = poisoned
            state["phases"][0]["title"] = poisoned
            state["archipelago"]["loop"]["cycle"] = poisoned
            state_path.write_text(json.dumps(state), encoding="utf-8")

            process = subprocess.run(
                [
                    sys.executable,
                    "-I",
                    "-B",
                    str(loop),
                    "fail",
                    "P0-G4",
                    "--reason",
                    "fixture",
                ],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            rendered = (mission / "state-of-the-union.html").read_text(
                encoding="utf-8"
            )
            self.assertFalse(
                any(
                    unicodedata.category(character) in {"Cc", "Cf"}
                    for character in rendered
                )
            )
            self.assertNotIn("<script>", rendered)
            self.assertIn("visible&lt;script&gt;", rendered)

    def test_loopback_resets_gate_and_blocks_close_until_passing_rerun(self) -> None:
        loop = PROTOCOL / "scripts/loop.py"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mission = root / "ops/mission"
            mission.mkdir(parents=True)
            gate_command = f"{shlex.quote(sys.executable)} -c pass"
            idea_path = mission / "idea.lock.json"
            plan_path = mission / "plan.lock.json"
            idea_path.write_text("{}\n", encoding="utf-8")
            plan_path.write_text(
                json.dumps(
                    {
                        "phases": [
                            {
                                "id": "P0",
                                "gates": [
                                    {
                                        "id": "P0-G4",
                                        "title": "fixture gate",
                                        "command": gate_command,
                                    }
                                ],
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            digest = lambda path: "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            state = {
                "mission": {"name": "fixture", "updated": ""},
                "phases": [
                    {
                        "id": "P0",
                        "title": "fixture",
                        "status": "in_progress",
                        "gates": [
                            {
                                "id": "P0-G4",
                                "title": "fixture gate",
                                "command": gate_command,
                                "status": "passed",
                                "evidence": None,
                                "lastRun": None,
                            }
                        ],
                    }
                ],
                "resume": {"activePhase": "P0"},
                "archipelago": {
                    "ideaLock": "ops/mission/idea.lock.json",
                    "ideaLockSHA256": digest(idea_path),
                    "planLock": "ops/mission/plan.lock.json",
                    "planLockSHA256": digest(plan_path),
                    "loop": {"cycle": 1, "stage": "S4", "loopbacks": []},
                },
            }
            (mission / "state.json").write_text(json.dumps(state), encoding="utf-8")

            failed = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "fail", "P0-G4", "--reason", "fixture"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(failed.returncode, 0, failed.stderr)
            after_fail = json.loads((mission / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(after_fail["phases"][0]["gates"][0]["status"], "failed")
            self.assertEqual(after_fail["archipelago"]["loop"]["loopbacks"][0]["gate"], "P0-G4")
            self.assertEqual(after_fail["archipelago"]["loop"]["loopbacks"][0]["fromGate"], "G4")

            rerun = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "run-gates", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rerun.returncode, 0, rerun.stderr)
            after_rerun = json.loads((mission / "state.json").read_text(encoding="utf-8"))
            self.assertIn("resolvedAt", after_rerun["archipelago"]["loop"]["loopbacks"][0])
            evidence = list((mission / "evidence").glob("P0-G4-*.txt"))
            self.assertEqual(len(evidence), 1)

            closed = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "close-phase", "P0"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(closed.returncode, 0, closed.stderr)

            plan_path.write_text('{"phases": []}\n', encoding="utf-8")
            drifted = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "status"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(drifted.returncode, 0)
            self.assertIn("plan.lock differs from the kickoff digest", drifted.stderr)

            plan_path.write_text(json.dumps({"phases": [{"id": "P0", "gates": [{"id": "P0-G4", "title": "fixture gate", "command": gate_command}]}]}), encoding="utf-8")
            changed_state = json.loads((mission / "state.json").read_text(encoding="utf-8"))
            changed_state["phases"][0]["gates"][0]["command"] = "echo counterfeit"
            (mission / "state.json").write_text(json.dumps(changed_state), encoding="utf-8")
            command_drift = subprocess.run(
                [sys.executable, "-I", "-B", str(loop), "status"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(command_drift.returncode, 0)
            self.assertIn("mission gate commands differ", command_drift.stderr)


if __name__ == "__main__":
    unittest.main()
