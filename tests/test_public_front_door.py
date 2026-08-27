from __future__ import annotations

import importlib.util
import json
import re
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
CATALOG = ROOT / "docs" / "catalog.md"
HERO = ROOT / "assets" / "forge-50" / "hero-welded-constellation.webp"
RENDERER = ROOT / "scripts" / "render_catalog.py"
PUBLIC_DOCS = (
    ROOT / "README.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
    ROOT / "assets" / "forge-50" / "README.md",
    ROOT / "docs" / "README.md",
    ROOT / "docs" / "catalog.md",
    ROOT / "docs" / "getting-started.md",
    ROOT / "docs" / "verification.md",
    ROOT / "docs" / "2.0.5-release-scope.md",
)


def load_renderer() -> ModuleType:
    spec = importlib.util.spec_from_file_location("render_catalog", RENDERER)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load catalog renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicFrontDoorTests(unittest.TestCase):
    def test_catalog_is_deterministic_and_covers_registry_order(self) -> None:
        registry = json.loads((ROOT / "skills" / "registry.json").read_text(encoding="utf-8"))
        renderer = load_renderer()
        self.assertEqual(CATALOG.read_text(encoding="utf-8"), renderer.render(registry))
        catalog = CATALOG.read_text(encoding="utf-8")
        rendered_order = re.findall(
            r"^### \d{2}\. \[([^]]+)\]\(\.\./skills/[^)]+/SKILL\.md\)$",
            catalog,
            flags=re.MULTILINE,
        )
        self.assertEqual(rendered_order, registry["buildOrder"])
        self.assertEqual(len(rendered_order), 50)

    def test_catalog_cli_check_and_scratch_render(self) -> None:
        checked = subprocess.run(
            [sys.executable, "-B", str(RENDERER), "--check"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr or checked.stdout)
        self.assertIn("CATALOG OK", checked.stdout)
        with tempfile.TemporaryDirectory(prefix="forge-catalog-") as temporary:
            drifted = Path(temporary) / "drifted.md"
            drifted.write_bytes(CATALOG.read_bytes() + b"\n")
            rejected = subprocess.run(
                [sys.executable, "-B", str(RENDERER), "--check", "--output", str(drifted)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("catalog bytes differ", rejected.stderr)
            output = Path(temporary) / "catalog.md"
            rendered = subprocess.run(
                [sys.executable, "-B", str(RENDERER), "--output", str(output)],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(rendered.returncode, 0, rendered.stderr or rendered.stdout)
            self.assertEqual(output.read_bytes(), CATALOG.read_bytes())

    def test_outcome_routes_name_25_unique_registry_skills(self) -> None:
        registry = json.loads((ROOT / "skills" / "registry.json").read_text(encoding="utf-8"))
        renderer = load_renderer()
        curated = [name for route in renderer.ROUTES for name in route["skills"]]
        self.assertEqual(len(curated), 25)
        self.assertEqual(len(set(curated)), 25)
        self.assertTrue(set(curated).issubset(set(registry["buildOrder"])))
        readme = README.read_text(encoding="utf-8")
        for route in renderer.ROUTES:
            start_here = "**Start here:** " + " · ".join(
                f"[`{name}`](skills/{name}/SKILL.md)" for name in route["skills"]
            )
            self.assertIn(start_here, readme)
            for name in route["skills"]:
                self.assertIn(f'<a id="{name}"></a>', CATALOG.read_text(encoding="utf-8"))

    def test_readme_has_one_semantic_h1_and_selected_local_hero(self) -> None:
        readme = README.read_text(encoding="utf-8")
        markdown_h1 = re.findall(r"^# (.+)$", readme, flags=re.MULTILINE)
        self.assertEqual(markdown_h1, ["Forge 50"])
        self.assertEqual(readme.count("assets/forge-50/hero-welded-constellation.webp"), 1)
        self.assertIn("Velocity, welded to proof.", readme)
        self.assertIn("contentReady", readme)
        self.assertIn("not <code>readyToRun=true</code>", readme)
        self.assertNotIn("five exist nowhere else", readme.casefold())
        self.assertNotIn("only idc ships", readme.casefold())

    def test_public_markdown_local_targets_exist(self) -> None:
        checked: list[str] = []
        for document in PUBLIC_DOCS:
            text = document.read_text(encoding="utf-8")
            targets = re.findall(r"!?\[[^]]*\]\(([^)]+)\)", text)
            for target in targets:
                target = target.strip().split(maxsplit=1)[0]
                if target.startswith(("http://", "https://", "#", "mailto:")):
                    continue
                path_text = target.split("#", 1)[0]
                if not path_text:
                    continue
                candidate = (document.parent / path_text).resolve(strict=False)
                try:
                    candidate.relative_to(ROOT)
                except ValueError:
                    self.fail(f"public target escapes repository: {document}: {target}")
                self.assertTrue(candidate.exists(), f"missing target in {document}: {target}")
                checked.append(candidate.relative_to(ROOT).as_posix())
        self.assertGreaterEqual(len(checked), 100)

    def test_public_markdown_has_one_h1_each(self) -> None:
        for document in PUBLIC_DOCS:
            headings = re.findall(r"^# (.+)$", document.read_text(encoding="utf-8"), re.MULTILINE)
            self.assertEqual(len(headings), 1, f"{document}: H1 count differs")

    def test_public_release_line_is_2_0_5_sequence_3(self) -> None:
        registry = json.loads((ROOT / "skills" / "registry.json").read_text(encoding="utf-8"))
        self.assertEqual(registry["release"], "2.0.5")
        self.assertEqual(registry["manifestSequence"], 3)
        for document in (ROOT / "README.md", ROOT / "SECURITY.md", ROOT / "docs" / "getting-started.md", ROOT / "docs" / "verification.md"):
            text = document.read_text(encoding="utf-8")
            self.assertIn("2.0.5", text, f"{document}: missing release line")
        self.assertIn("_idc-skills-2-0-5.islanddevcrew.com", README.read_text(encoding="utf-8"))

    def test_selected_hero_is_bounded_metadata_free_webp(self) -> None:
        data = HERO.read_bytes()
        self.assertLessEqual(len(data), 300_000)
        self.assertEqual(data[:4], b"RIFF")
        self.assertEqual(data[8:12], b"WEBP")
        self.assertEqual(data[12:16], b"VP8 ")
        self.assertEqual(data[23:26], b"\x9d\x01\x2a")
        width = struct.unpack_from("<H", data, 26)[0] & 0x3FFF
        height = struct.unpack_from("<H", data, 28)[0] & 0x3FFF
        self.assertEqual((width, height), (1796, 876))
        chunks: list[bytes] = []
        offset = 12
        while offset + 8 <= len(data):
            name = data[offset : offset + 4]
            size = struct.unpack_from("<I", data, offset + 4)[0]
            chunks.append(name)
            offset += 8 + size + (size % 2)
        self.assertEqual(chunks, [b"VP8 "])
        self.assertTrue(data.endswith(b"\x00") or offset == len(data))


if __name__ == "__main__":
    unittest.main()
