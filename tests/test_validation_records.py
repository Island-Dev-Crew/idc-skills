from __future__ import annotations

import html
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts import verify_validation_records


REPO = Path(__file__).resolve().parents[1]


class ValidationRecordTests(unittest.TestCase):
    def run_gate(self, records: Path, report: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "python3",
                str(REPO / "scripts/verify_validation_records.py"),
                "--registry",
                str(REPO / "skills/registry.json"),
                "--records",
                str(records),
                "--report",
                str(report),
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_current_fifty_records_and_report_pass(self) -> None:
        process = self.run_gate(
            REPO / "ops/validation/skill-records.json", REPO / "docs/report.html"
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        self.assertIn("records=50 cases=150 registry=50 report=50", process.stdout)

    def test_renderer_writes_canonical_lf_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "report.html"
            process = subprocess.run(
                [
                    "python3",
                    str(REPO / "scripts/render_validation_report.py"),
                    "--output",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(process.returncode, 0, process.stderr)
            rendered = report.read_bytes()
            self.assertNotIn(b"\r\n", rendered)
            self.assertEqual(rendered, (REPO / "docs/report.html").read_bytes())

    def test_missing_record_fails_name_set_gate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            records = json.loads(
                (REPO / "ops/validation/skill-records.json").read_text(encoding="utf-8")
            )
            records["records"].pop()
            target = Path(temporary) / "records.json"
            target.write_text(json.dumps(records), encoding="utf-8")
            process = self.run_gate(target, REPO / "docs/report.html")
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("registry/record name mismatch", process.stderr)

    def test_report_name_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (REPO / "docs/report.html").read_text(encoding="utf-8")
            match = verify_validation_records.REPORT_DATA_RE.search(source)
            self.assertIsNotNone(match)
            data = json.loads(html.unescape(match.group(1)))
            data[0]["skill"] = "not-a-registry-skill"
            altered = source[: match.start(1)] + html.escape(
                json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            ) + source[match.end(1) :]
            report = Path(temporary) / "report.html"
            report.write_text(altered, encoding="utf-8")
            process = self.run_gate(
                REPO / "ops/validation/skill-records.json", report
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("rendered report skill names", process.stderr)

    def test_report_record_content_drift_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (REPO / "docs/report.html").read_text(encoding="utf-8")
            match = verify_validation_records.REPORT_DATA_RE.search(source)
            self.assertIsNotNone(match)
            data = json.loads(html.unescape(match.group(1)))
            data[0]["cases"][0]["whatHappened"] = "tampered rendered evidence"
            altered = source[: match.start(1)] + html.escape(
                json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            ) + source[match.end(1) :]
            report = Path(temporary) / "report.html"
            report.write_text(altered, encoding="utf-8")
            process = self.run_gate(
                REPO / "ops/validation/skill-records.json", report
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("records do not equal source", process.stderr)

    def test_visible_report_drift_fails_full_byte_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = (REPO / "docs/report.html").read_text(encoding="utf-8")
            altered = source.replace("mean case score", "forged mean score", 1)
            self.assertNotEqual(altered, source)
            report = Path(temporary) / "report.html"
            report.write_text(altered, encoding="utf-8")
            process = self.run_gate(
                REPO / "ops/validation/skill-records.json", report
            )
            self.assertNotEqual(process.returncode, 0)
            self.assertIn("bytes differ from deterministic renderer", process.stderr)


if __name__ == "__main__":
    unittest.main()
