#!/usr/bin/env python3
"""Replay one preserved Kimi evidence record after rechecking its byte bindings.

This command does not rerun an exploit against the current candidate. It proves that the
fixture and captured output named by the G0 ledger are the exact preserved bytes the ledger
hashes, then emits that captured output unchanged. Candidate regressions live in the G2-G5
test suites; G0's job is immutable source-evidence reconciliation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path, PurePosixPath


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(128 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def local_file(root: Path, value: str) -> Path:
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"unsafe evidence path: {value!r}")
    path = root.joinpath(*relative.parts)
    resolved = path.resolve(strict=True)
    if root != resolved and root not in resolved.parents:
        raise ValueError(f"evidence path escapes package: {value!r}")
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"evidence path is not a regular file: {value!r}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, dest="finding_id")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()
    try:
        package_path = args.evidence.resolve(strict=True)
        package = json.loads(package_path.read_text(encoding="utf-8"))
        matches = [record for record in package.get("findings", []) if record.get("id") == args.finding_id]
        if len(matches) != 1:
            raise ValueError(f"expected exactly one record for {args.finding_id}, found {len(matches)}")
        record = matches[0]
        root = package_path.parent
        fixture = local_file(root, record["fixture"]["path"])
        output = local_file(root, record["execution"]["outputPath"])
        if digest(fixture) != record["fixture"]["sha256"]:
            raise ValueError("fixture digest differs from the reconciled ledger")
        if record["execution"]["fixtureSha256"] != record["fixture"]["sha256"]:
            raise ValueError("execution record is not bound to the fixture digest")
        if digest(output) != record["execution"]["outputSha256"]:
            raise ValueError("captured-output digest differs from the reconciled ledger")
        sys.stdout.buffer.write(output.read_bytes())
        return int(record["execution"]["observedExit"])
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        print(f"KIMI EVIDENCE REPLAY REFUSED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
