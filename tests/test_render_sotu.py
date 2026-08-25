from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "ops" / "mission"


class MissionRendererTests(unittest.TestCase):
    def test_release_runbook_commands_name_every_required_external_anchor(self) -> None:
        state = json.loads((MISSION / "state.json").read_text(encoding="utf-8"))
        g6 = next(phase for phase in state["phases"] if phase["id"] == "G6")
        commands = {gate["id"]: gate["command"] for gate in g6["gates"]}

        for flag in (
            "--repo-root",
            "--git",
            "--git-sha256",
            "--review-authorities",
            "--review-authorities-sha256",
            "--ssh-keygen",
            "--ssh-keygen-sha256",
        ):
            self.assertIn(flag, commands["G6-G2"])
        for flag in (
            "--repo-root",
            "--git",
            "--git-sha256",
            "--canonical-repository",
            "--site-host",
            "--trusted-root",
            "--trusted-root-sha256",
            "--ssh-keygen",
            "--ssh-keygen-sha256",
            "--observer-authority",
            "--observer-authority-sha256",
        ):
            self.assertIn(flag, commands["G6-G3"])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for renderer tests")
    def test_journal_line_endings_render_identically(self) -> None:
        with tempfile.TemporaryDirectory(prefix="idc-render-test-") as temporary:
            fixture = Path(temporary)
            shutil.copy2(MISSION / "render-sotu.mjs", fixture / "render-sotu.mjs")
            shutil.copy2(MISSION / "state.json", fixture / "state.json")
            journal = (MISSION / "journal.md").read_text(encoding="utf-8")
            journal = journal.replace("\r\n", "\n").replace("\r", "\n")

            outputs: list[bytes] = []
            for newline in ("\n", "\r\n"):
                (fixture / "journal.md").write_bytes(journal.replace("\n", newline).encode("utf-8"))
                subprocess.run(
                    ["node", "render-sotu.mjs"],
                    cwd=fixture,
                    check=True,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                )
                outputs.append((fixture / "state-of-the-union.html").read_bytes())

            self.assertEqual(outputs[0], outputs[1])

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for renderer tests")
    def test_metric_prose_is_not_coerced_into_green_numeric_progress(self) -> None:
        with tempfile.TemporaryDirectory(prefix="idc-render-tone-") as temporary:
            fixture = Path(temporary)
            shutil.copy2(MISSION / "render-sotu.mjs", fixture / "render-sotu.mjs")
            state = json.loads((MISSION / "state.json").read_text(encoding="utf-8"))
            state["metrics"] = [{
                "label": "Signed content gate",
                "baseline": "0/5",
                "current": "Historical 2.0.2/v2 signature only; 2.0.3/v3 pending",
                "target": "2.0.3/v3 contentReady",
                "direction": "up",
            }]
            (fixture / "state.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8", newline="\n")
            (fixture / "journal.md").write_text("", encoding="utf-8", newline="\n")

            subprocess.run(
                ["node", "render-sotu.mjs"], cwd=fixture, check=True,
                capture_output=True, text=True, encoding="utf-8")
            output = (fixture / "state-of-the-union.html").read_text(encoding="utf-8")
            self.assertIn(
                '<span class="chip amber">Historical 2.0.2/v2 signature only; '
                '2.0.3/v3 pending</span>', output)
            self.assertNotIn(
                '<span class="chip green">Historical 2.0.2/v2 signature only; '
                '2.0.3/v3 pending</span>', output)

    @unittest.skipUnless(shutil.which("node"), "Node.js is required for renderer tests")
    def test_untrusted_controls_and_unicode_format_characters_are_removed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="idc-render-controls-") as temporary:
            fixture = Path(temporary)
            shutil.copy2(MISSION / "render-sotu.mjs", fixture / "render-sotu.mjs")
            state = json.loads((MISSION / "state.json").read_text(encoding="utf-8"))
            hostile = "left\x00\x07\x1b\r\x85\u200b\u202e\u2066right"
            state["mission"]["name"] = hostile
            (fixture / "state.json").write_text(
                json.dumps(state, ensure_ascii=False), encoding="utf-8", newline="\n"
            )
            (fixture / "journal.md").write_text(
                f"## {hostile}\n", encoding="utf-8", newline="\n"
            )

            subprocess.run(
                ["node", "render-sotu.mjs"], cwd=fixture, check=True,
                capture_output=True, text=True, encoding="utf-8")
            output = (fixture / "state-of-the-union.html").read_text(encoding="utf-8")
            self.assertIn("leftright", output)
            for unsafe in ("\x00", "\x07", "\x1b", "\r", "\x85", "\u200b", "\u202e", "\u2066"):
                self.assertNotIn(unsafe, output)


if __name__ == "__main__":
    unittest.main()
