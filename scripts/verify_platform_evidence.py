#!/usr/bin/env python3
"""Fail closed unless real macOS and Windows records bind the exact candidate."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


HEAD_RE = re.compile(r"[0-9a-f]{40}\Z")
DIGEST_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
SCHEMA = "idc-platform-evidence/v1"


class PlatformEvidenceError(RuntimeError):
    pass


def _exact(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PlatformEvidenceError(f"{label} keys differ")
    return value


def validate(value: Any, expected_head: str) -> None:
    root = _exact(value, {"schema", "candidateHead", "records"}, "platform evidence")
    if root["schema"] != SCHEMA:
        raise PlatformEvidenceError("platform evidence schema differs")
    if HEAD_RE.fullmatch(expected_head) is None or root["candidateHead"] != expected_head:
        raise PlatformEvidenceError("platform evidence does not bind the exact candidate head")
    records = root["records"]
    if not isinstance(records, list) or len(records) != 2:
        raise PlatformEvidenceError("exactly two platform records are required")
    expected_keys = {
        "platform",
        "status",
        "runner",
        "osVersion",
        "filesystem",
        "python",
        "bash",
        "sshKeygen",
        "command",
        "outputSHA256",
    }
    seen: set[str] = set()
    for index, item in enumerate(records):
        record = _exact(item, expected_keys, f"records[{index}]")
        platform = record["platform"]
        if platform not in {"macos", "windows"} or platform in seen:
            raise PlatformEvidenceError("platform records must uniquely cover macos and windows")
        seen.add(platform)
        if record["status"] != "passed":
            raise PlatformEvidenceError(f"{platform} platform evidence is not passed")
        for key in ("runner", "osVersion", "filesystem", "python", "sshKeygen", "command"):
            if not isinstance(record[key], str) or not record[key].strip():
                raise PlatformEvidenceError(f"{platform}.{key} must be non-empty")
        if platform == "macos" and not isinstance(record["bash"], str):
            raise PlatformEvidenceError("macos.bash must be recorded")
        if platform == "windows" and record["filesystem"].casefold() != "ntfs":
            raise PlatformEvidenceError("Windows release evidence must come from NTFS")
        if DIGEST_RE.fullmatch(record["outputSHA256"]) is None:
            raise PlatformEvidenceError(f"{platform}.outputSHA256 is invalid")
    if seen != {"macos", "windows"}:
        raise PlatformEvidenceError("macos and windows evidence are both required")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--candidate-head", required=True)
    args = parser.parse_args(argv)
    try:
        validate(json.loads(args.evidence.read_text(encoding="utf-8")), args.candidate_head)
    except (OSError, json.JSONDecodeError, PlatformEvidenceError) as exc:
        print(f"PLATFORM EVIDENCE REFUSED - {exc}", file=sys.stderr)
        return 2
    print(f"PLATFORM EVIDENCE OK - macos+windows head={args.candidate_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
