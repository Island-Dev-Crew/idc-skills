from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import skill_integrity
from scripts import verify_fleet_parity as parity


class FleetParityTests(unittest.TestCase):
    def fixture(self, root: Path):
        names = [f"skill-{index:02d}" for index in range(50)]
        roots = {label: root / label for label in parity.ROOT_LABELS}
        skills = {}
        for name in names:
            source = root / "source" / name
            source.mkdir(parents=True)
            (source / "SKILL.md").write_text(f"# {name}\n", encoding="utf-8")
            (source / "agents").mkdir()
            (source / "agents/openai.yaml").write_text("interface: {}\n", encoding="utf-8")
            files = {
                path.relative_to(source).as_posix(): skill_integrity._skill_file_record(path)
                for path in skill_integrity._walk_regular_files(source)
            }
            skills[name] = {"files": files}
            for fleet_root in roots.values():
                target = fleet_root / name
                target.mkdir(parents=True)
                (target / "agents").mkdir()
                (target / "SKILL.md").write_bytes((source / "SKILL.md").read_bytes())
                (target / "agents/openai.yaml").write_bytes((source / "agents/openai.yaml").read_bytes())
        report = {
            "contentReady": True,
            "profile": "release",
            "score": "5/5",
            "_verifiedManifest": {
                "release": "fixture",
                "manifestSequence": 1,
                "skillNames": names,
                "skills": skills,
            },
        }
        return roots, report

    def test_four_exact_roots_pass_byte_mode_and_loader_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots, authenticated = self.fixture(Path(temporary))
            with mock.patch.object(parity.verify_provenance, "verify", return_value={"pass": True}):
                report = parity.verify_roots(Path(temporary), roots, authenticated)
            self.assertTrue(report["pass"])
            self.assertEqual(report["skillsPerRoot"], 50)
            self.assertEqual(len(report["roots"]), 4)

    def test_byte_drift_and_extra_inventory_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            roots, authenticated = self.fixture(Path(temporary))
            (roots["agents"] / "skill-00/SKILL.md").write_text("poisoned\n", encoding="utf-8")
            with self.assertRaisesRegex(parity.FleetParityError, "byte drift"):
                parity.verify_roots(Path(temporary), roots, copy.deepcopy(authenticated))

        with tempfile.TemporaryDirectory() as temporary:
            roots, authenticated = self.fixture(Path(temporary))
            (roots["hermes"] / "counterfeit").mkdir()
            with self.assertRaisesRegex(parity.FleetParityError, "inventory differs"):
                parity.verify_roots(Path(temporary), roots, authenticated)


if __name__ == "__main__":
    unittest.main()
