from __future__ import annotations

import hashlib
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
PROTOCOL = REPO / "skills/archipelago/protocol"


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
