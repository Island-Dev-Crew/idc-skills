from __future__ import annotations

import copy
import json
import unittest
from unittest import mock

from scripts import verify_provenance as provenance


REPO = provenance.REPO


class ProvenanceTests(unittest.TestCase):
    def test_current_forge_provenance_closes_registered_and_vendored_sources(self) -> None:
        report = provenance.verify()
        self.assertTrue(report["pass"])
        self.assertEqual(report["registrySkills"], 50)
        self.assertEqual(report["sources"], 4)
        self.assertEqual(report["vendoredProtocolFiles"], 18)

    def test_unpinned_source_cannot_be_silently_promoted(self) -> None:
        original = provenance.load

        def forged(relative: str):
            value = copy.deepcopy(original(relative))
            if relative == "provenance.json":
                icm = next(item for item in value["sources"] if item["id"] == "icm-architect")
                icm["commit"] = "a" * 40
            return value

        with mock.patch.object(provenance, "load", side_effect=forged):
            with self.assertRaisesRegex(provenance.ProvenanceError, "laundered"):
                provenance.verify()

    def test_vendored_result_hash_tamper_is_rejected(self) -> None:
        original = provenance.load

        def forged(relative: str):
            value = copy.deepcopy(original(relative))
            if relative.endswith("UPSTREAM.json"):
                value["modifiedFiles"][0]["resultSHA256"] = "sha256:" + "0" * 64
            return value

        with mock.patch.object(provenance, "load", side_effect=forged):
            with self.assertRaisesRegex(provenance.ProvenanceError, "modified vendored"):
                provenance.verify()

    def test_executable_inventory_names_each_actual_tool_family(self) -> None:
        inventory = json.loads(
            (REPO / "executable-dependencies.json").read_text(encoding="utf-8")
        )
        names = {item["name"] for item in inventory["dependencies"]}
        self.assertTrue(
            {
                "bash",
                "python3",
                "git",
                "ssh-keygen",
                "node",
                "jq",
                "uuidgen",
                "ffmpeg",
                "ffprobe",
                "yt-dlp",
                "gh",
                "op",
                "curl",
                "shasum",
                "sha256sum",
            }.issubset(names)
        )
        self.assertFalse({name for name in names if "/" in name})
        ssh_keygen = next(
            item for item in inventory["dependencies"] if item["name"] == "ssh-keygen"
        )
        self.assertNotIn("every verifier consumer", ssh_keygen["pinMechanism"])
        self.assertIn("PATH-resolved", ssh_keygen["pinMechanism"])


if __name__ == "__main__":
    unittest.main()
