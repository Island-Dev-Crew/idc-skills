from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import install


MODEL_SKILL = b"""---
name: alpha
description: Alpha test skill. Use when testing the installer. Differentiator - fixture only.
---

# Alpha
"""

USER_SKILL = b"""---
name: invoked
description: User-only fixture.
disable-model-invocation: true
argument-hint: "What should run?"
---

# Invoked
"""


def write_skill(root: Path, name: str, data: bytes, extra: bytes = b"payload\x00") -> Path:
    skill = root / "skills" / name
    (skill / "agents").mkdir(parents=True)
    (skill / "SKILL.md").write_bytes(data)
    (skill / "agents" / "openai.yaml").write_bytes(extra)
    return skill


class InstallerTests(unittest.TestCase):
    def test_native_install_detects_drift_repairs_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "alpha", MODEL_SKILL)
            target = root / "targets" / "cursor"
            spec = install.TargetSpec("cursor", target)

            first = install.run_install(root / "skills", [spec])
            self.assertTrue(first.success)
            self.assertEqual(first.targets[0].skills[0].status, "installed")
            self.assertEqual(install.tree_manifest(source), install.tree_manifest(target / "alpha"))

            (target / "alpha" / "SKILL.md").write_bytes(b"drift")
            (target / "alpha" / "extra.txt").write_text("extra", encoding="utf-8")
            verify = install.run_install(root / "skills", [spec], verify_only=True)
            self.assertFalse(verify.success)
            self.assertEqual(verify.targets[0].skills[0].status, "drift")
            self.assertIn("changed:SKILL.md", verify.targets[0].skills[0].differences)
            self.assertIn("extra:extra.txt", verify.targets[0].skills[0].differences)

            repaired = install.run_install(root / "skills", [spec])
            self.assertTrue(repaired.success)
            self.assertEqual(repaired.targets[0].skills[0].status, "updated")
            self.assertEqual(install.tree_manifest(source), install.tree_manifest(target / "alpha"))
            rerun = install.run_install(root / "skills", [spec])
            self.assertEqual(rerun.targets[0].skills[0].status, "unchanged")

    def test_dry_run_creates_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "not-created"
            report = install.run_install(
                root / "skills", [install.TargetSpec("custom", target)], dry_run=True
            )
            self.assertTrue(report.success)
            self.assertEqual(report.targets[0].skills[0].status, "would-install")
            self.assertFalse(target.exists())

    def test_missing_skill_fails_before_any_target_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "target"
            with self.assertRaisesRegex(install.InstallError, "requested skill.*not found"):
                install.run_install(
                    root / "skills",
                    [install.TargetSpec("custom", target)],
                    ["missing"],
                )
            self.assertFalse(target.exists())

    def test_unsafe_source_equal_or_overlapping_targets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            skills = root / "skills"
            for target in (skills, skills / "nested", root):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(install.InstallError, "unsafe target"):
                        install.run_install(skills, [install.TargetSpec("bad", target)])

    def test_equal_target_paths_are_explicitly_covered_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "target"
            report = install.run_install(
                root / "skills",
                [install.TargetSpec("first", target), install.TargetSpec("alias", target)],
            )
            self.assertTrue(report.success)
            self.assertEqual(report.targets[0].status, "ok")
            self.assertEqual(report.targets[1].status, "covered")
            self.assertEqual(report.targets[1].covered_by, "first")

    def test_custom_target_selection_does_not_imply_fleet_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            custom = install.parse_custom_targets([f"buzz={Path(temporary) / 'buzz'}"])
            targets = install.select_targets(home, None, custom)
            self.assertEqual([target.name for target in targets], ["buzz"])

    def test_default_topology_reports_optional_absence_and_skill_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            beta_data = MODEL_SKILL.replace(b"name: alpha", b"name: beta")
            write_skill(root, "beta", beta_data)
            targets = install.select_targets(root / "home", None)
            report = install.run_install(
                root / "skills", targets, ["beta"], dry_run=True
            )
            self.assertEqual(
                [(target.name, target.status) for target in report.targets],
                [
                    ("agents", "changes-planned"),
                    ("claude", "skipped-absent"),
                    ("pi", "skipped-absent"),
                    ("hermes", "changes-planned"),
                ],
            )
            operated = [skill.skill for target in report.targets for skill in target.skills]
            self.assertEqual(operated, ["beta", "beta"])

    def test_claude_ai_transform_preserves_values_and_allowed_keys(self) -> None:
        transformed, moved = install.transform_claude_ai_frontmatter(USER_SKILL, "fixture")
        text = transformed.decode("utf-8")
        self.assertEqual(moved, ("disable-model-invocation", "argument-hint"))
        self.assertIn("metadata:\n", text)
        self.assertIn("  disable-model-invocation: true\n", text)
        self.assertIn('  argument-hint: "What should run?"\n', text)
        frontmatter, _, _ = install._frontmatter_lines(transformed, "fixture")
        keys = {key for _, key, _ in install._top_level_keys(frontmatter, "fixture")}
        self.assertLessEqual(keys, set(install.CLAUDE_AI_ALLOWED_KEYS))

    def test_transform_engine_is_profile_driven(self) -> None:
        profile = install.ExportProfile(
            identifier="future-strict",
            harness="future.strict",
            allowed_top_level_keys=("description", "metadata", "name"),
            keys_to_metadata=("argument-hint", "disable-model-invocation"),
            assumption="fixture contract",
            assumption_status="verified fixture",
            assumption_source="unit test",
            semantics_note="metadata only",
        )
        transformed, moved = install.transform_frontmatter_for_profile(
            USER_SKILL, profile, "fixture"
        )
        self.assertEqual(moved, ("disable-model-invocation", "argument-hint"))
        frontmatter, _, _ = install._frontmatter_lines(transformed, "fixture")
        keys = {key for _, key, _ in install._top_level_keys(frontmatter, "fixture")}
        self.assertLessEqual(keys, set(profile.allowed_top_level_keys))

    def test_claude_ai_export_is_deterministic_and_never_mutates_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "invoked", USER_SKILL)
            source_before = install.tree_manifest(source)
            output = root / "exports" / "claude-ai"

            first = install.run_claude_ai_export(root / "skills", output)
            self.assertTrue(first.success)
            self.assertEqual(first.targets[0].skills[0].status, "installed")
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["canonicalMutation"])
            self.assertEqual(manifest["profileId"], "claude-ai-supplied-20260811")
            self.assertEqual(manifest["allowedFrontmatterKeys"], list(install.CLAUDE_AI_ALLOWED_KEYS))
            self.assertIn("not official current", manifest["compatibilityAssumption"]["status"])
            self.assertIn("current upload acceptance unverified", manifest["compatibilityAssumption"]["status"])
            self.assertEqual(manifest["metadataTransform"]["invocationSemantics"], "not asserted")
            self.assertIn("ignores", manifest["metadataTransform"]["note"])

            archive_bytes = (output / "invoked.zip").read_bytes()
            with zipfile.ZipFile(output / "invoked.zip") as archive:
                exported = archive.read("SKILL.md").decode("utf-8")
            self.assertIn("metadata:\n  disable-model-invocation: true", exported)
            self.assertEqual(install.tree_manifest(source), source_before)

            rerun = install.run_claude_ai_export(root / "skills", output)
            self.assertEqual(rerun.targets[0].skills[0].status, "unchanged")
            self.assertEqual((output / "invoked.zip").read_bytes(), archive_bytes)
            self.assertEqual(install.tree_manifest(source), source_before)

            (output / "invoked.zip").write_bytes(b"drift")
            verify = install.run_claude_ai_export(root / "skills", output, verify_only=True)
            self.assertFalse(verify.success)
            self.assertEqual(verify.targets[0].skills[0].status, "drift")
            self.assertEqual(install.tree_manifest(source), source_before)

    def test_claude_ai_export_rejects_output_inside_canonical_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            with self.assertRaisesRegex(install.InstallError, "unsafe target"):
                install.run_claude_ai_export(root / "skills", root / "skills" / "export")

    def test_claude_ai_unknown_frontmatter_key_fails_closed(self) -> None:
        data = MODEL_SKILL.replace(b"description:", b"mystery: value\ndescription:")
        with self.assertRaisesRegex(install.InstallError, "outside.*allow-list"):
            install.transform_claude_ai_frontmatter(data, "fixture")


if __name__ == "__main__":
    unittest.main()
