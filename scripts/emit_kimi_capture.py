#!/usr/bin/env python3
"""Emit one digest-verified preserved Kimi capture without asserting execution."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Sequence

try:
    from .validate_evidence import (
        EvidenceError,
        MAX_FINDINGS,
        SourceBundle,
        _load_object,
        _resolve_capture,
        _resolve_fixture,
        _validate_semantic_binding,
    )
except ImportError:  # direct ``python scripts/emit_kimi_capture.py`` execution
    from validate_evidence import (  # type: ignore[no-redef]
        EvidenceError,
        MAX_FINDINGS,
        SourceBundle,
        _load_object,
        _resolve_capture,
        _resolve_fixture,
        _validate_semantic_binding,
    )


def _friendly_error(exc: EvidenceError) -> EvidenceError:
    message = str(exc)
    if ".fixture.sha256 mismatch" in message:
        return EvidenceError(f"fixture digest differs from the ledger: {message}")
    if "outputSha256 mismatch" in message:
        return EvidenceError(f"capture digest differs from the ledger: {message}")
    if (
        "is not a safe relative path" in message
        or "symlink ancestor" in message
        or "escapes" in message
    ):
        return EvidenceError(f"unsafe evidence path: {message}")
    return exc


def emit_capture(package_path: Path, finding_id: str) -> bytes:
    package = _load_object(package_path)
    records = package.get("findings")
    if not isinstance(records, list) or len(records) > MAX_FINDINGS:
        raise EvidenceError(f"findings must be an array of at most {MAX_FINDINGS} records")
    matches = [
        record
        for record in records
        if isinstance(record, dict) and record.get("id") == finding_id
    ]
    if len(matches) != 1:
        raise EvidenceError(
            f"expected exactly one record for {finding_id}, found {len(matches)}"
        )
    record: dict[str, Any] = matches[0]
    forbidden = {
        "execution",
        "expectedExit",
        "observedExit",
        "assertedExit",
    } & set(record)
    if forbidden:
        raise EvidenceError(
            f"execution claims are unsupported in preserved evidence: {sorted(forbidden)}"
        )
    root = package_path.parent.resolve(strict=True)
    bundle = None
    if "sourceBundle" in package:
        bundle = SourceBundle(root, package.get("sourceBundle"))
    try:
        fixture_bytes, fixture_digest = _resolve_fixture(
            root, record.get("fixture"), bundle, "finding.fixture"
        )
        capture_bytes, bound_fixture_digest = _resolve_capture(
            root, record.get("capture"), bundle, "finding.capture"
        )
        if bound_fixture_digest != fixture_digest:
            raise EvidenceError("capture does not bind the fixture digest")
        if "semanticBinding" in record:
            _validate_semantic_binding(
                record.get("semanticBinding"),
                fixture_bytes,
                capture_bytes,
                "finding.semanticBinding",
            )
    except EvidenceError as exc:
        raise _friendly_error(exc) from exc
    return capture_bytes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--id", required=True, dest="finding_id")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        package_path = args.evidence.absolute()
        output = emit_capture(package_path, args.finding_id)
        sys.stdout.buffer.write(output)
        sys.stdout.buffer.flush()
        return 0
    except (EvidenceError, OSError, BrokenPipeError) as exc:
        print(f"KIMI EVIDENCE EMIT REFUSED — {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
