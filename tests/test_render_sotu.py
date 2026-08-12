from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MISSION = REPO_ROOT / "ops" / "mission"


class MissionRendererTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
