from __future__ import annotations

import contextlib
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

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


def run_unsigned_fixture_install(
    source_skills: Path,
    targets: list[install.TargetSpec],
    selected_skills: list[str] | None = None,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> install.InstallReport:
    """Exercise copy mechanics on synthetic trees; release CLI has no such opt-out."""
    return install._run_install(
        source_skills,
        targets,
        selected_skills,
        dry_run=dry_run,
        verify_only=verify_only,
        verify_integrity=False,
    )


def run_unsigned_fixture_export(
    profile: install.ExportProfile,
    source_skills: Path,
    output: Path,
    *,
    verify_only: bool = False,
) -> install.InstallReport:
    """Exercise export mechanics on synthetic trees; release APIs always verify."""
    return install._run_profile_export(
        profile,
        source_skills,
        output,
        verify_only=verify_only,
        verify_integrity=False,
    )


class InstallerTests(unittest.TestCase):
    def test_integrity_failure_refuses_install_before_target_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "target"
            with mock.patch.object(
                install.skill_integrity,
                "verify_repository",
                return_value={"readyToRun": False, "score": "4/5"},
            ):
                with self.assertRaisesRegex(
                    install.InstallError, "integrity verification failed"
                ):
                    install.run_install(
                        root / "skills",
                        [install.TargetSpec("custom", target)],
                        repo_root=root,
                    )
            self.assertFalse(target.exists())

    def test_unflagged_cli_install_verifies_before_target_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "target"
            with mock.patch.object(
                install.skill_integrity,
                "verify_repository",
                return_value={"readyToRun": False, "score": "4/5"},
            ) as verify:
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = install.main(
                        [
                            "--repo-root",
                            str(root),
                            "install",
                            "--custom-target",
                            f"fixture={target}",
                            "--json",
                        ]
                    )
            self.assertEqual(exit_code, 2)
            verify.assert_called_once()
            self.assertFalse(target.exists())
            with self.assertRaisesRegex(
                install.InstallError, "cannot disable signed integrity"
            ):
                install.run_install(
                    root / "skills",
                    [install.TargetSpec("custom", target)],
                    verify_integrity=False,
                    repo_root=root,
                )
            self.assertFalse(target.exists())

    def test_unflagged_export_verifies_before_output_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            direct_output = root / "direct-export"
            cli_output = root / "cli-export"
            with mock.patch.object(
                install.skill_integrity,
                "verify_repository",
                return_value={"readyToRun": False, "score": "4/5"},
            ) as verify:
                with self.assertRaisesRegex(
                    install.InstallError, "integrity verification failed"
                ):
                    install.run_claude_ai_snapshot_export(
                        root / "skills", direct_output, repo_root=root
                    )
                with contextlib.redirect_stdout(io.StringIO()):
                    exit_code = install.main(
                        [
                            "--repo-root",
                            str(root),
                            "export-claude-ai-snapshot",
                            "--output",
                            str(cli_output),
                            "--json",
                        ]
                    )
            self.assertEqual(exit_code, 2)
            self.assertEqual(verify.call_count, 2)
            self.assertFalse(direct_output.exists())
            self.assertFalse(cli_output.exists())

    def test_signed_file_map_binds_staged_install_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "alpha", MODEL_SKILL)
            expected_files = {
                path.relative_to(source).as_posix(): {
                    "sha256": install.skill_integrity.sha256_file(path),
                    "size": path.stat().st_size,
                }
                for path in source.rglob("*")
                if path.is_file()
            }
            (source / "SKILL.md").write_bytes(
                MODEL_SKILL.replace(b"# Alpha", b"# Poisoned Alpha")
            )
            target = root / "target"
            with mock.patch.object(
                install.skill_integrity,
                "verify_repository",
                return_value={
                    "readyToRun": True,
                    "score": "5/5",
                    "_verifiedManifest": {
                        "skills": {"alpha": {"files": expected_files}}
                    },
                },
            ):
                with self.assertRaisesRegex(
                    install.InstallError, "source differs from signed manifest"
                ):
                    install.run_install(
                        root / "skills",
                        [install.TargetSpec("custom", target)],
                        verify_integrity=True,
                        repo_root=root,
                    )
            self.assertFalse(target.exists())

    def test_native_install_detects_drift_repairs_and_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "alpha", MODEL_SKILL)
            target = root / "targets" / "cursor"
            spec = install.TargetSpec("cursor", target)

            first = run_unsigned_fixture_install(root / "skills", [spec])
            self.assertTrue(first.success)
            self.assertEqual(first.targets[0].skills[0].status, "installed")
            self.assertEqual(install.tree_manifest(source), install.tree_manifest(target / "alpha"))

            (target / "alpha" / "SKILL.md").write_bytes(b"drift")
            (target / "alpha" / "extra.txt").write_text("extra", encoding="utf-8")
            verify = run_unsigned_fixture_install(
                root / "skills", [spec], verify_only=True
            )
            self.assertFalse(verify.success)
            self.assertEqual(verify.targets[0].skills[0].status, "drift")
            self.assertIn("changed:SKILL.md", verify.targets[0].skills[0].differences)
            self.assertIn("extra:extra.txt", verify.targets[0].skills[0].differences)

            repaired = run_unsigned_fixture_install(root / "skills", [spec])
            self.assertTrue(repaired.success)
            self.assertEqual(repaired.targets[0].skills[0].status, "updated")
            self.assertEqual(install.tree_manifest(source), install.tree_manifest(target / "alpha"))
            rerun = run_unsigned_fixture_install(root / "skills", [spec])
            self.assertEqual(rerun.targets[0].skills[0].status, "unchanged")

    def test_dry_run_creates_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "not-created"
            report = run_unsigned_fixture_install(
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
                run_unsigned_fixture_install(
                    root / "skills",
                    [install.TargetSpec("custom", target)],
                    ["missing"],
                )
            self.assertFalse(target.exists())

    def test_all_destinations_are_preflighted_before_first_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            beta = MODEL_SKILL.replace(b"name: alpha", b"name: beta")
            write_skill(root, "beta", beta)
            target = root / "target"
            target.mkdir()
            (target / "beta").write_text("blocking file", encoding="utf-8")
            with self.assertRaisesRegex(install.InstallError, "not a directory"):
                run_unsigned_fixture_install(
                    root / "skills", [install.TargetSpec("custom", target)]
                )
            self.assertFalse((target / "alpha").exists())

    def test_unsafe_source_equal_or_overlapping_targets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            skills = root / "skills"
            for target in (skills, skills / "nested", root):
                with self.subTest(target=target):
                    with self.assertRaisesRegex(install.InstallError, "unsafe target"):
                        run_unsigned_fixture_install(
                            skills, [install.TargetSpec("bad", target)]
                        )

    def test_equal_target_paths_are_explicitly_covered_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            target = root / "target"
            report = run_unsigned_fixture_install(
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

    def test_explicit_absent_optional_target_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            targets = install.select_targets(root / "home", ["claude"])
            with self.assertRaisesRegex(
                install.InstallError, "explicitly selected optional target does not exist"
            ):
                run_unsigned_fixture_install(root / "skills", targets, dry_run=True)

    def test_default_topology_reports_optional_absence_and_skill_selection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            beta_data = MODEL_SKILL.replace(b"name: alpha", b"name: beta")
            write_skill(root, "beta", beta_data)
            targets = install.select_targets(root / "home", None)
            report = run_unsigned_fixture_install(
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

    @unittest.skipIf(os.name == "nt", "POSIX executable bits are not meaningful on Windows")
    def test_posix_executable_mode_drift_is_detected_and_repaired(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "alpha", MODEL_SKILL)
            script = source / "scripts" / "run.sh"
            script.parent.mkdir()
            script.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            script.chmod(0o755)
            target = root / "target"
            spec = install.TargetSpec("custom", target)
            run_unsigned_fixture_install(root / "skills", [spec])
            installed = target / "alpha" / "scripts" / "run.sh"
            installed.chmod(0o644)
            verify = run_unsigned_fixture_install(
                root / "skills", [spec], verify_only=True
            )
            self.assertFalse(verify.success)
            self.assertIn("changed:scripts/run.sh", verify.targets[0].skills[0].differences)
            repaired = run_unsigned_fixture_install(root / "skills", [spec])
            self.assertTrue(repaired.success)
            self.assertEqual(stat.S_IMODE(installed.stat().st_mode), 0o755)

    def test_manifest_digest_includes_posix_mode_when_present(self) -> None:
        regular = install.ManifestEntry("scripts/run.sh", 1, "a", posix_mode=0o644)
        executable = install.ManifestEntry("scripts/run.sh", 1, "a", posix_mode=0o755)
        self.assertNotEqual(
            install._manifest_digest([regular]), install._manifest_digest([executable])
        )

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

    def test_transform_preserves_existing_metadata_indentation(self) -> None:
        data = USER_SKILL.replace(
            b"disable-model-invocation: true\n",
            b"metadata:\n    owner: idc\ndisable-model-invocation: true\n",
        )
        transformed, moved = install.transform_claude_ai_frontmatter(data, "fixture")
        text = transformed.decode("utf-8")
        self.assertEqual(moved, ("disable-model-invocation", "argument-hint"))
        self.assertIn(
            "metadata:\n    disable-model-invocation: true\n"
            '    argument-hint: "What should run?"\n'
            "    owner: idc\n",
            text,
        )
        frontmatter, _, _ = install._frontmatter_lines(transformed, "fixture")
        keys = install._top_level_keys(frontmatter, "fixture")
        install._validate_profile_frontmatter_shape(
            frontmatter, keys, "fixture", set()
        )

    def test_transform_rejects_metadata_collision_and_duplicate(self) -> None:
        collision = USER_SKILL.replace(
            b"disable-model-invocation: true\n",
            b"metadata:\n  disable-model-invocation: false\n"
            b"disable-model-invocation: true\n",
        )
        with self.assertRaisesRegex(install.InstallError, "collides with moved field"):
            install.transform_claude_ai_frontmatter(collision, "fixture")

        duplicate = USER_SKILL.replace(
            b"disable-model-invocation: true\n",
            b"metadata:\n  owner: one\n  owner: two\n"
            b"disable-model-invocation: true\n",
        )
        with self.assertRaisesRegex(install.InstallError, "duplicate metadata key"):
            install.transform_claude_ai_frontmatter(duplicate, "fixture")

    def test_transform_rejects_nested_metadata_it_cannot_extend_losslessly(self) -> None:
        nested = USER_SKILL.replace(
            b"disable-model-invocation: true\n",
            b"metadata:\n  owner:\n    name: idc\n"
            b"disable-model-invocation: true\n",
        )
        with self.assertRaisesRegex(
            install.InstallError, "must be an inline scalar|nested or inconsistent metadata"
        ):
            install.transform_claude_ai_frontmatter(nested, "fixture")

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

    def test_claude_ai_snapshot_export_is_deterministic_and_never_mutates_canonical(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = write_skill(root, "invoked", USER_SKILL)
            source_before = install.tree_manifest(source)
            output = root / "exports" / "claude-ai"

            first = run_unsigned_fixture_export(
                install.CLAUDE_AI_SNAPSHOT_PROFILE, root / "skills", output
            )
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
            self.assertEqual(manifest["archiveLayout"], "<skill-name>/<skill files>")

            archive_bytes = (output / "invoked.zip").read_bytes()
            with zipfile.ZipFile(output / "invoked.zip") as archive:
                self.assertTrue(all(name.startswith("invoked/") for name in archive.namelist()))
                exported = archive.read("invoked/SKILL.md").decode("utf-8")
            self.assertIn("metadata:\n  disable-model-invocation: true", exported)
            self.assertEqual(install.tree_manifest(source), source_before)

            rerun = run_unsigned_fixture_export(
                install.CLAUDE_AI_SNAPSHOT_PROFILE, root / "skills", output
            )
            self.assertEqual(rerun.targets[0].skills[0].status, "unchanged")
            self.assertEqual((output / "invoked.zip").read_bytes(), archive_bytes)
            self.assertEqual(install.tree_manifest(source), source_before)

            (output / "invoked.zip").write_bytes(b"drift")
            verify = run_unsigned_fixture_export(
                install.CLAUDE_AI_SNAPSHOT_PROFILE,
                root / "skills",
                output,
                verify_only=True,
            )
            self.assertFalse(verify.success)
            self.assertEqual(verify.targets[0].skills[0].status, "drift")
            self.assertEqual(install.tree_manifest(source), source_before)

    def test_current_claude_ai_export_uses_root_folder_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            output = root / "exports" / "current"
            report = run_unsigned_fixture_export(
                install.CLAUDE_AI_CURRENT_PROFILE, root / "skills", output
            )
            self.assertTrue(report.success)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["profileId"], "claude-ai-current-20260811")
            self.assertEqual(manifest["descriptionMax"], 200)
            self.assertEqual(manifest["userOnlyPolicy"], "reject")
            with zipfile.ZipFile(output / "alpha.zip") as archive:
                self.assertIn("alpha/SKILL.md", archive.namelist())
                self.assertNotIn("SKILL.md", archive.namelist())

    def test_current_claude_ai_export_fails_closed_on_long_description(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            long_description = b"A" * 201
            data = MODEL_SKILL.replace(
                b"Alpha test skill. Use when testing the installer. Differentiator - fixture only.",
                long_description,
            )
            write_skill(root, "alpha", data)
            output = root / "exports" / "current"
            with self.assertRaisesRegex(install.InstallError, "descriptions over 200"):
                run_unsigned_fixture_export(
                    install.CLAUDE_AI_CURRENT_PROFILE, root / "skills", output
                )
            self.assertFalse(output.exists())

    def test_current_claude_ai_export_fails_closed_on_user_only_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "invoked", USER_SKILL)
            output = root / "exports" / "current"
            with self.assertRaisesRegex(
                install.InstallError, "user-only invocation cannot be preserved"
            ):
                run_unsigned_fixture_export(
                    install.CLAUDE_AI_CURRENT_PROFILE, root / "skills", output
                )
            self.assertFalse(output.exists())

    def test_claude_ai_export_rejects_output_inside_canonical_skills(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            with self.assertRaisesRegex(install.InstallError, "unsafe target"):
                run_unsigned_fixture_export(
                    install.CLAUDE_AI_CURRENT_PROFILE,
                    root / "skills",
                    root / "skills" / "export",
                )

    def test_claude_ai_unknown_frontmatter_key_fails_closed(self) -> None:
        data = MODEL_SKILL.replace(b"description:", b"mystery: value\ndescription:")
        with self.assertRaisesRegex(install.InstallError, "outside.*allow-list"):
            install.transform_claude_ai_frontmatter(data, "fixture")

    def test_cli_json_and_human_output_are_unicode_safe_before_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_skill(root, "alpha", MODEL_SKILL)
            repository = Path(install.__file__).resolve().parents[1]
            environment = os.environ.copy()
            environment["PYTHONIOENCODING"] = "cp1252:strict"
            child = """
import sys
from pathlib import Path
from unittest import mock
from scripts import install

fixture_root = Path(sys.argv[1])
source = fixture_root / "skills" / "alpha"
files = {
    path.relative_to(source).as_posix(): install.skill_integrity._file_record(path)
    for path in install.skill_integrity._walk_regular_files(source)
}
verified = {
    "readyToRun": True,
    "score": "5/5",
    "_verifiedManifest": {"skills": {"alpha": {"files": files}}},
}
with mock.patch.object(
    install.skill_integrity, "verify_repository", return_value=verified
):
    raise SystemExit(install.main(sys.argv[2:]))
"""

            for json_mode in (True, False):
                target = root / ("target-中-json" if json_mode else "target-中-human")
                command = [
                    sys.executable,
                    "-B",
                    "-c",
                    child,
                    str(root),
                    "--repo-root",
                    str(root),
                    "install",
                    "--custom-target",
                    f"buzz={target}",
                    "--skill",
                    "alpha",
                ]
                if json_mode:
                    command.append("--json")
                completed = subprocess.run(
                    command,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env=environment,
                    cwd=repository,
                    check=False,
                )
                self.assertEqual(
                    completed.returncode,
                    0,
                    completed.stderr.decode("utf-8", errors="replace"),
                )
                output = completed.stdout.decode("utf-8")
                if json_mode:
                    parsed = json.loads(output)
                    self.assertEqual(parsed["targets"][0]["name"], "buzz")
                else:
                    self.assertIn("target-中-human", output)
                self.assertTrue((target / "alpha" / "SKILL.md").is_file())
                self.assertNotIn(b"Traceback", completed.stderr)

    def test_install_help_names_topology_and_transaction_boundary(self) -> None:
        parser_help = install.build_parser().format_help()
        self.assertIn("install", parser_help)
        install_help = install.build_parser()._subparsers._group_actions[0].choices[
            "install"
        ].format_help()
        for path in (
            "~/.agents/skills",
            "~/.claude/skills",
            "~/.pi/agent/skills",
            "~/.hermes/skills",
        ):
            self.assertIn(path, install_help)
        self.assertIn("not rollback-atomic", install_help)


if __name__ == "__main__":
    unittest.main()
