#!/usr/bin/env python3
"""Fail closed unless validation records, registry, and rendered report agree."""

from __future__ import annotations

import argparse
import html
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping, Sequence


SCHEMA = "idc-skill-validation/v1"
REPORT_DATA_RE = re.compile(
    r'<script id="validation-data" type="application/json">(.*?)</script>', re.DOTALL
)


class ValidationError(RuntimeError):
    pass


def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"invalid {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{label} must be a JSON object: {path}")
    return value


def validate_records(registry: Mapping[str, Any], payload: Mapping[str, Any]) -> list[str]:
    failures: list[str] = []
    if payload.get("schema") != SCHEMA:
        failures.append(f"records schema must be {SCHEMA!r}")
    registry_entries = registry.get("skills")
    records = payload.get("records")
    if not isinstance(registry_entries, list) or not isinstance(records, list):
        return failures + ["registry.skills and records must be arrays"]

    registry_map = {
        item.get("name"): item for item in registry_entries if isinstance(item, dict)
    }
    record_map: dict[str, Mapping[str, Any]] = {}
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("skill"), str):
            failures.append(f"records[{index}] requires a skill name")
            continue
        name = record["skill"]
        if name in record_map:
            failures.append(f"duplicate validation record: {name}")
            continue
        record_map[name] = record

    missing = sorted(set(registry_map) - set(record_map))
    extra = sorted(set(record_map) - set(registry_map))
    if missing or extra:
        failures.append(f"registry/record name mismatch: missing={missing} extra={extra}")
    if len(record_map) != 50:
        failures.append(f"expected exactly 50 unique records, found {len(record_map)}")

    for name, record in sorted(record_map.items()):
        if name not in registry_map:
            continue
        if record.get("inv") != registry_map[name].get("invocation"):
            failures.append(f"{name}: invocation does not match registry")
        for field in ("oneLiner", "standoutStrength", "residual"):
            if not isinstance(record.get(field), str) or not record[field].strip():
                failures.append(f"{name}: missing non-empty {field}")
        confidence = record.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool) or not 0 <= confidence <= 10:
            failures.append(f"{name}: confidence must be numeric 0..10")
        cases = record.get("cases")
        if not isinstance(cases, list) or len(cases) != 3:
            failures.append(f"{name}: requires exactly three cases")
            continue
        scores: list[float] = []
        for case_index, case in enumerate(cases, start=1):
            if not isinstance(case, dict):
                failures.append(f"{name}: case {case_index} must be an object")
                continue
            for field in ("title", "whatHappened"):
                if not isinstance(case.get(field), str) or not case[field].strip():
                    failures.append(f"{name}: case {case_index} missing {field}")
            score = case.get("score")
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not 0 <= score <= 10:
                failures.append(f"{name}: case {case_index} score must be numeric 0..10")
            else:
                scores.append(float(score))
        if len(scores) == 3:
            expected_average = round(sum(scores) / 3, 1)
            actual_average = record.get("caseAvg")
            if not isinstance(actual_average, (int, float)) or not math.isclose(
                float(actual_average), expected_average, abs_tol=0.01
            ):
                failures.append(
                    f"{name}: caseAvg={actual_average!r}, recomputed={expected_average}"
                )
    return failures


def report_records(path: Path) -> list[dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ValidationError(f"invalid rendered report {path}: {exc}") from exc
    match = REPORT_DATA_RE.search(text)
    if not match:
        raise ValidationError("rendered report is missing its machine-readable validation data")
    try:
        data = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError as exc:
        raise ValidationError(f"rendered report data is invalid JSON: {exc}") from exc
    if not isinstance(data, list):
        raise ValidationError("rendered report data must be an array")
    if not all(isinstance(item, dict) for item in data):
        raise ValidationError("rendered report contains a non-object validation record")
    names = [item.get("skill") for item in data]
    if not all(isinstance(name, str) for name in names):
        raise ValidationError("rendered report contains a record without a skill name")
    return data


def _deterministic_report_failures(
    registry_path: Path,
    records_path: Path,
    report_path: Path,
) -> list[str]:
    renderer = Path(__file__).with_name("render_validation_report.py")
    with tempfile.TemporaryDirectory(prefix="idc-validation-report-") as temporary:
        expected = Path(temporary) / "report.html"
        process = subprocess.run(
            [
                sys.executable,
                str(renderer),
                "--registry",
                str(registry_path),
                "--records",
                str(records_path),
                "--output",
                str(expected),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if process.returncode != 0:
            detail = (process.stderr or process.stdout).strip()
            return [f"deterministic report renderer failed: {detail}"]
        try:
            expected_bytes = expected.read_bytes()
            actual_bytes = report_path.read_bytes()
        except OSError as exc:
            return [f"cannot compare deterministic report bytes: {exc}"]
    if actual_bytes != expected_bytes:
        return ["rendered report bytes differ from deterministic renderer output"]
    return []


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("--registry", type=Path, default=root / "skills" / "registry.json")
    parser.add_argument(
        "--records", type=Path, default=root / "ops" / "validation" / "skill-records.json"
    )
    parser.add_argument("--report", type=Path, default=root / "docs" / "report.html")
    args = parser.parse_args(argv)
    try:
        registry = _load_object(args.registry, "registry")
        payload = _load_object(args.records, "validation records")
        failures = validate_records(registry, payload)
        registry_names = sorted(item["name"] for item in registry.get("skills", []))
        rendered_records = report_records(args.report)
        rendered_names = sorted(item["skill"] for item in rendered_records)
        if rendered_names != registry_names:
            failures.append("rendered report skill names do not equal registry skill names")
        if rendered_records != payload.get("records"):
            failures.append("rendered report records do not equal source validation records")
        failures.extend(
            _deterministic_report_failures(args.registry, args.records, args.report)
        )
    except (ValidationError, KeyError, TypeError) as exc:
        failures = [str(exc)]
    if failures:
        for failure in failures:
            print(f"VALIDATION RECORDS FAIL — {failure}", file=sys.stderr)
        return 1
    print("VALIDATION RECORDS OK — records=50 cases=150 registry=50 report=50")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
