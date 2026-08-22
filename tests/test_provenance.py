from __future__ import annotations

import copy
import unittest
from unittest import mock

from scripts import verify_provenance as provenance


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


if __name__ == "__main__":
    unittest.main()
