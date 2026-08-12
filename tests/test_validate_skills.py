from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from validate_skills import ForgeValidator  # noqa: E402


GOOD_DESCRIPTION = (
    "Validate one sample skill. Use when a test needs a minimal forge fixture. "
    "Differentiator - this fixture isolates validator behavior from the production pack."
)


class ForgeFixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        (root / "skills").mkdir(parents=True)
        self.entries: list[dict[str, object]] = []

    def add_skill(
        self,
        name: str,
        *,
        invocation: str = "model",
        description: str = GOOD_DESCRIPTION,
        extra_frontmatter: str = "",
        body: str = "# Sample\n\nDone when the fixture validates.\n",
        sidecar_policy: bool | None = None,
    ) -> Path:
        folder = self.root / "skills" / name
        (folder / "agents").mkdir(parents=True)
        if sidecar_policy is None:
            sidecar_policy = invocation == "user"
        frontmatter = f"---\nname: {name}\ndescription: {description}\n"
        if invocation == "user":
            frontmatter += "disable-model-invocation: true\n"
        frontmatter += extra_frontmatter
        (folder / "SKILL.md").write_text(frontmatter + "---\n\n" + body, encoding="utf-8")
        sidecar = (
            "interface:\n"
            f"  display_name: \"{name.replace('-', ' ').title()}\"\n"
            "  short_description: \"Minimal test skill\"\n"
        )
        if sidecar_policy:
            sidecar += "policy:\n  allow_implicit_invocation: false\n"
        (folder / "agents" / "openai.yaml").write_text(sidecar, encoding="utf-8")
        self.entries.append(
            {
                "name": name,
                "path": name,
                "invocation": invocation,
                "provenance": "test",
                "summary": "fixture",
                "triggers": [f"use {name}"],
            }
        )
        self.write_registry()
        return folder

    def write_registry(self) -> None:
        registry = {
            "version": 1,
            "release": "test",
            "buildOrder": [str(entry["name"]) for entry in self.entries],
            "skills": self.entries,
        }
        (self.root / "skills" / "registry.json").write_text(json.dumps(registry), encoding="utf-8")


class ValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.fixture = ForgeFixture(self.root)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def validate(self, profile: str = "canonical") -> dict[str, object]:
        return ForgeValidator(self.root, profile).validate()

    @staticmethod
    def codes(result: dict[str, object]) -> set[str]:
        return {item["code"] for item in result["diagnostics"]}  # type: ignore[index]

    def test_minimal_model_skill_passes(self) -> None:
        self.fixture.add_skill("sample-skill")
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"]["errors"], 0)  # type: ignore[index]

    def test_registry_folder_bijection_goes_red(self) -> None:
        self.fixture.add_skill("sample-skill")
        (self.root / "skills" / "rogue-skill").mkdir()
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("UNREGISTERED_SKILL_FOLDER", self.codes(result))

    def test_empty_registry_and_zero_skills_go_red(self) -> None:
        (self.root / "skills" / "registry.json").write_text("{}\n", encoding="utf-8")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertEqual(result["summary"]["skillsRegistered"], 0)  # type: ignore[index]
        self.assertEqual(result["summary"]["skillsLoaded"], 0)  # type: ignore[index]
        self.assertTrue({"REGISTRY_EMPTY", "NO_SKILLS_LOADED"}.issubset(self.codes(result)))

    def test_name_and_description_contracts_go_red(self) -> None:
        folder = self.fixture.add_skill("sample-skill")
        skill_path = folder / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        text = text.replace("name: sample-skill", "name: wrong-name")
        text = text.replace(GOOD_DESCRIPTION, "A vague summary without routing terms.")
        skill_path.write_text(text, encoding="utf-8")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertTrue({"NAME_MISMATCH", "DESCRIPTION_TRIGGER", "DESCRIPTION_DIFFERENTIATOR"}.issubset(self.codes(result)))

    def test_sidecar_invocation_policy_parity_goes_red(self) -> None:
        self.fixture.add_skill("user-skill", invocation="user", sidecar_policy=False)
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("OPENAI_POLICY_USER", self.codes(result))

    def test_scalar_cannot_gain_an_indented_mapping(self) -> None:
        folder = self.fixture.add_skill("sample-skill")
        skill_path = folder / "SKILL.md"
        text = skill_path.read_text(encoding="utf-8")
        text = text.replace(f"name: sample-skill\ndescription: {GOOD_DESCRIPTION}", f"name: sample-skill\n  description: {GOOD_DESCRIPTION}")
        skill_path.write_text(text, encoding="utf-8")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("FRONTMATTER_YAML", self.codes(result))

    def test_missing_and_chained_references_go_red(self) -> None:
        folder = self.fixture.add_skill(
            "sample-skill",
            body="# Sample\n\nSee [missing](references/missing.md) and [first](references/first.md).\n",
        )
        references = folder / "references"
        references.mkdir()
        (references / "first.md").write_text("Continue to [second](second.md).\n", encoding="utf-8")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertTrue({"REFERENCE_MISSING", "REFERENCE_CHAIN"}.issubset(self.codes(result)))

    def test_orphan_markdown_reference_goes_red(self) -> None:
        folder = self.fixture.add_skill("sample-skill")
        references = folder / "references"
        references.mkdir()
        orphan = references / "orphan.md"
        orphan.write_text("# Orphan\n", encoding="utf-8")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("REFERENCE_UNREACHABLE", self.codes(result))

        skill_path = folder / "SKILL.md"
        skill_path.write_text(skill_path.read_text(encoding="utf-8") + "\nSee [the reference](references/orphan.md).\n", encoding="utf-8")
        linked = self.validate()
        self.assertNotIn("REFERENCE_UNREACHABLE", self.codes(linked))

    def test_unlinked_non_markdown_reference_is_advisory(self) -> None:
        folder = self.fixture.add_skill("sample-skill")
        references = folder / "references"
        references.mkdir()
        (references / "template.cjs").write_text("module.exports = {};\n", encoding="utf-8")
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertIn("REFERENCE_NON_MARKDOWN_UNREACHABLE", self.codes(result))

    def test_angle_bracket_label_does_not_hide_a_concrete_absolute_target(self) -> None:
        self.fixture.add_skill("sample-skill", body="# Sample\n\nSee [<outside>](/definitely/absolute/missing.md).\n")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("REFERENCE_ABSOLUTE", self.codes(result))

    def test_placeholder_and_code_example_links_are_not_paths(self) -> None:
        self.fixture.add_skill(
            "sample-skill",
            body=(
                "# Sample\n\n"
                "Template: [<closed ticket>](link).\n\n"
                "Inline code: `[fake](/not/a/path.md)`.\n\n"
                "```markdown\n[fake](/also/not/a/path.md)\n```\n"
            ),
        )
        result = self.validate()
        self.assertTrue(result["valid"])
        self.assertNotIn("REFERENCE_ABSOLUTE", self.codes(result))

    def test_script_syntax_and_utf8_go_red(self) -> None:
        folder = self.fixture.add_skill("sample-skill", body="# Sample\n\nRun [the check](scripts/check.py).\n")
        scripts = folder / "scripts"
        scripts.mkdir()
        (scripts / "check.py").write_text("def broken(:\n", encoding="utf-8")
        (folder / "notes.txt").write_bytes(b"\xff")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertTrue({"PYTHON_SYNTAX", "INVALID_UTF8"}.issubset(self.codes(result)))

    def test_canonical_unknown_key_goes_red(self) -> None:
        self.fixture.add_skill("sample-skill", extra_frontmatter="mystery-key: true\n")
        result = self.validate()
        self.assertFalse(result["valid"])
        self.assertIn("FRONTMATTER_KEY", self.codes(result))

    def test_frontmatter_boundary_and_absolute_reference_go_red(self) -> None:
        folder = self.fixture.add_skill("sample-skill", body="# Sample\n\nSee [outside](/tmp/outside.md).\n")
        skill_path = folder / "SKILL.md"
        skill_path.write_text(skill_path.read_text(encoding="utf-8").replace("---\n", "--\n", 1), encoding="utf-8")
        boundary = self.validate()
        self.assertIn("FRONTMATTER_OPEN", self.codes(boundary))

        # Restore only the boundary; the absolute link is a separate invariant.
        skill_path.write_text(skill_path.read_text(encoding="utf-8").replace("--\n", "---\n", 1), encoding="utf-8")
        absolute = self.validate()
        self.assertIn("REFERENCE_ABSOLUTE", self.codes(absolute))

    def test_thirteen_user_invoked_profiles_are_reported_not_rewritten(self) -> None:
        original_bytes: dict[Path, bytes] = {}
        for index in range(13):
            folder = self.fixture.add_skill(
                f"user-skill-{index}",
                invocation="user",
                description="A concise human-facing command that performs one explicit test task safely.",
                extra_frontmatter=("argument-hint: \"What should this skill process?\"\n" if index < 5 else ""),
            )
            path = folder / "SKILL.md"
            original_bytes[path] = path.read_bytes()

        canonical = self.validate("canonical")
        self.assertTrue(canonical["valid"])
        self.assertEqual(canonical["summary"]["warnings"], 13)  # type: ignore[index]
        self.assertEqual(len(canonical["summary"]["warningSkills"]), 13)  # type: ignore[index]

        codex_strict = self.validate("codex-strict")
        self.assertFalse(codex_strict["valid"])
        self.assertEqual(codex_strict["summary"]["errors"], 13)  # type: ignore[index]
        self.assertEqual(self.codes(codex_strict), {"CODEX_STRICT_UNSUPPORTED_KEYS"})

        claude_ai = self.validate("claude-ai-supplied-2026-08-11")
        self.assertFalse(claude_ai["valid"])
        self.assertEqual(claude_ai["summary"]["errors"], 13)  # type: ignore[index]
        self.assertEqual(self.codes(claude_ai), {"CLAUDE_AI_SUPPLIED_UNSUPPORTED_KEYS"})
        for path, before in original_bytes.items():
            self.assertEqual(path.read_bytes(), before)

    def test_cli_json_is_machine_readable_and_exit_is_nonzero(self) -> None:
        self.fixture.add_skill("sample-skill", extra_frontmatter="mystery-key: true\n")
        completed = subprocess.run(
            [sys.executable, str(REPO_ROOT / "scripts" / "validate_skills.py"), "--root", str(self.root), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        self.assertEqual(completed.returncode, 1)
        result = json.loads(completed.stdout)
        self.assertFalse(result["valid"])
        self.assertEqual(result["summary"]["failedSkills"], ["sample-skill"])


class ProductionPackTests(unittest.TestCase):
    def test_current_pack_canonical_contract(self) -> None:
        result = ForgeValidator(REPO_ROOT, "canonical").validate()
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"]["skillsLoaded"], 50)
        self.assertEqual(result["summary"]["errors"], 0)
        self.assertEqual(result["summary"]["warnings"], 13)


if __name__ == "__main__":
    unittest.main()
