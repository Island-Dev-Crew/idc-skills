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
        context = {
            "gitCommit": "a" * 40,
            "gitTag": "fixture",
            "gitTree": "b" * 40,
            "indexSHA256": "sha256:" + "c" * 64,
            "installInventorySHA256": "sha256:" + "d" * 64,
            "manifestSHA256": "sha256:" + "e" * 64,
            "release": "fixture",
        }
        return root / "source", roots, report, context

    def test_four_exact_roots_pass_byte_mode_and_loader_parity(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            with mock.patch.object(parity.verify_provenance, "verify", return_value={"pass": True}):
                report = parity.verify_roots(repo_root, roots, authenticated, context)
            self.assertTrue(report["pass"])
            self.assertEqual(report["authority"], "observation-only")
            self.assertFalse(report["readyToRun"])
            self.assertEqual(report["skillsPerRoot"], 50)
            self.assertEqual(len(report["roots"]), 4)
            self.assertEqual(
                report["candidate"],
                {
                    "commit": context["gitCommit"],
                    "tag": context["gitTag"],
                    "tree": context["gitTree"],
                },
            )
            self.assertEqual(report["indexSHA256"], context["indexSHA256"])
            self.assertEqual(
                report["installInventorySHA256"],
                context["installInventorySHA256"],
            )
            self.assertEqual(report["manifestSHA256"], context["manifestSHA256"])

    def test_release_context_parser_requires_complete_authenticated_identity(self) -> None:
        environment = {
            variable: {
                "gitCommit": "a" * 40,
                "gitTag": "2.0.4",
                "gitTree": "b" * 40,
                "indexSHA256": "sha256:" + "c" * 64,
                "installInventorySHA256": "sha256:" + "d" * 64,
                "manifestSHA256": "sha256:" + "e" * 64,
                "release": "2.0.4",
            }[key]
            for key, variable in parity.PARITY_CONTEXT_ENV.items()
        }
        parsed = parity.parse_release_context(
            environment, "sha256:" + "c" * 64
        )
        self.assertEqual(parsed["gitTag"], "2.0.4")
        with self.assertRaisesRegex(parity.FleetParityError, "handoff differs"):
            parity.parse_release_context(environment, "sha256:" + "9" * 64)
        environment.pop("IDC_SKILLS_PARITY_INDEX_SHA256")
        with self.assertRaisesRegex(parity.FleetParityError, "context is invalid"):
            parity.parse_release_context(environment, "sha256:" + "c" * 64)

    def test_byte_drift_and_extra_inventory_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            (roots["agents"] / "skill-00/SKILL.md").write_text("poisoned\n", encoding="utf-8")
            with self.assertRaisesRegex(parity.FleetParityError, "byte drift"):
                parity.verify_roots(
                    repo_root, roots, copy.deepcopy(authenticated), context
                )

        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            (roots["hermes"] / "counterfeit").mkdir()
            with self.assertRaisesRegex(parity.FleetParityError, "inventory differs"):
                parity.verify_roots(repo_root, roots, authenticated, context)

    def test_roots_must_be_distinct_and_outside_candidate_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            one_root = {label: roots["agents"] for label in parity.ROOT_LABELS}
            with self.assertRaisesRegex(parity.FleetParityError, "physically distinct"):
                parity.verify_roots(repo_root, one_root, authenticated, context)

        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            roots["agents"] = repo_root
            with self.assertRaisesRegex(parity.FleetParityError, "outside the candidate"):
                parity.verify_roots(repo_root, roots, authenticated, context)

    def test_case_variant_samefile_cannot_launder_candidate_as_installed_root(self) -> None:
        with tempfile.TemporaryDirectory(
            prefix=".parity-case-", dir=Path(__file__).resolve().parents[1]
        ) as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            parts = list(repo_root.parts)
            for index, part in enumerate(parts):
                if any(character.isalpha() for character in part):
                    parts[index] = "".join(
                        character.swapcase() if character.isalpha() else character
                        for character in part
                    )
                    break
            alternate = Path(*parts)
            try:
                same_file = alternate.samefile(repo_root)
            except OSError:
                self.skipTest("filesystem does not expose a case-variant same-file path")
            if not same_file or alternate == repo_root:
                self.skipTest("filesystem is case-sensitive for this path")
            roots["agents"] = alternate
            with self.assertRaisesRegex(parity.FleetParityError, "outside the candidate"):
                parity.verify_roots(repo_root, roots, authenticated, context)

    def test_extra_file_and_symlink_inventory_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            (roots["agents"] / "counterfeit.txt").write_text("extra\n", encoding="utf-8")
            with self.assertRaisesRegex(parity.FleetParityError, "non-directory entry"):
                parity.verify_roots(repo_root, roots, authenticated, context)

        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            (roots["agents"] / "counterfeit").symlink_to("skill-00", target_is_directory=True)
            with self.assertRaisesRegex(parity.FleetParityError, "symlink entry"):
                parity.verify_roots(repo_root, roots, authenticated, context)

    def test_release_context_mismatch_rejects_parity_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            repo_root, roots, authenticated, context = self.fixture(Path(temporary))
            context["release"] = "2.0.4"
            with self.assertRaisesRegex(parity.FleetParityError, "context differs"):
                parity.verify_roots(repo_root, roots, authenticated, context)


if __name__ == "__main__":
    unittest.main()
