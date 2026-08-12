#!/usr/bin/env python3
"""Verify that every gauntlet builder received an independent, falsifiable critique."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
REVIEWS_DIR = REPO_ROOT / "ops" / "gauntlet" / "reviews"
EXPECTED = {
    "P0-T1-contract-critique.json": (
        "P0-T1",
        "ca4257bb2790ddfea59175e850c6438fee3445e7",
    ),
    "P0-T2-validator-critique.json": (
        "P0-T2",
        "a083552def772489ae238bf6931cd275d471b263",
    ),
    "P0-T3-installer-critique.json": (
        "P0-T3",
        "b1ab04c31015b11a086020fa3a4d0d01654127e6",
    ),
}
SEVERITIES = {"critical", "high", "medium", "low"}


def _require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def verify() -> list[str]:
    errors: list[str] = []
    found = {path.name for path in REVIEWS_DIR.glob("*.json")}
    _require(found == set(EXPECTED), f"review set mismatch: {sorted(found)}", errors)

    seen_tasks: set[str] = set()
    seen_commits: set[str] = set()
    for filename, (task_id, commit) in EXPECTED.items():
        path = REVIEWS_DIR / filename
        if not path.is_file():
            errors.append(f"missing review: {filename}")
            continue
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{filename}: invalid JSON: {exc}")
            continue

        actual_task = record.get("taskId")
        actual_commit = record.get("reviewedCommit")
        _require(actual_task == task_id, f"{filename}: taskId drift", errors)
        _require(actual_commit == commit, f"{filename}: reviewedCommit drift", errors)
        _require(
            isinstance(actual_commit, str) and re.fullmatch(r"[0-9a-f]{40}", actual_commit) is not None,
            f"{filename}: reviewedCommit is not a full SHA",
            errors,
        )
        _require(actual_task not in seen_tasks, f"{filename}: duplicate taskId", errors)
        _require(actual_commit not in seen_commits, f"{filename}: duplicate reviewedCommit", errors)
        if isinstance(actual_task, str):
            seen_tasks.add(actual_task)
        if isinstance(actual_commit, str):
            seen_commits.add(actual_commit)

        independence = str(record.get("independence", "")).lower()
        _require("same-family" in independence, f"{filename}: family not disclosed", errors)
        _require(
            "not a cross-family" in independence,
            f"{filename}: cross-family limitation not disclosed",
            errors,
        )
        _require(bool(record.get("criticSeat")), f"{filename}: critic seat missing", errors)
        _require(
            record.get("disposition") == "changes-requested",
            f"{filename}: critique did not force a repair disposition",
            errors,
        )

        findings = record.get("findings")
        _require(isinstance(findings, list) and bool(findings), f"{filename}: findings missing", errors)
        for index, finding in enumerate(findings if isinstance(findings, list) else [], start=1):
            prefix = f"{filename}: finding {index}"
            _require(isinstance(finding, dict), f"{prefix} is not an object", errors)
            if not isinstance(finding, dict):
                continue
            _require(finding.get("severity") in SEVERITIES, f"{prefix} severity invalid", errors)
            for field in ("title", "evidence", "recompute"):
                _require(bool(str(finding.get(field, "")).strip()), f"{prefix} {field} missing", errors)

    return errors


def main() -> int:
    errors = verify()
    if errors:
        for error in errors:
            print(f"ERROR {error}", file=sys.stderr)
        return 1
    print(
        "gauntlet records verified: 3 exact builder commits, 3 non-author "
        "same-family critiques, cross-family verdict not claimed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
