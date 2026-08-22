#!/usr/bin/env python3
"""Validate an IDC security evidence package without third-party dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


SCHEMA = "idc.security-evidence/v1"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
FINDING_RE = re.compile(r"\bK3-203-\d{3}\b")
STATUSES = {
    "accepted-residual",
    "confirmed",
    "false-positive",
    "fixed",
    "held",
    "open",
    "theoretical",
    "unverified",
}
SCRIPT_SUFFIXES = (".py", ".sh", ".mjs", ".js", ".ps1")


class EvidenceError(RuntimeError):
    pass


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"invalid evidence package {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("evidence package must be a JSON object")
    return value


def _safe_local_path(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty relative path")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts or "" in pure.parts:
        raise EvidenceError(f"{label} is not a safe relative path: {value!r}")
    path = root.joinpath(*pure.parts)
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise EvidenceError(f"{label} does not exist: {value!r}: {exc}") from exc
    if root != resolved and root not in resolved.parents:
        raise EvidenceError(f"{label} escapes evidence root: {value!r}")
    if path.is_symlink() or not path.is_file():
        raise EvidenceError(f"{label} must be a regular non-symlink file: {value!r}")
    return path


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _expect_digest(path: Path, expected: Any, label: str) -> None:
    if not isinstance(expected, str) or not SHA256_RE.fullmatch(expected):
        raise EvidenceError(f"{label} must be a lowercase SHA-256 digest")
    actual = _digest(path)
    if actual != expected:
        raise EvidenceError(f"{label} mismatch: expected {expected}, got {actual}")


def _git_blob(repo: Path, revision: Any, source_path: Any, label: str) -> bytes:
    if not isinstance(revision, str) or not REVISION_RE.fullmatch(revision):
        raise EvidenceError(f"{label}.revision must be an exact 40-character commit")
    if not isinstance(source_path, str) or not source_path:
        raise EvidenceError(f"{label}.path must be a non-empty repository path")
    pure = PurePosixPath(source_path)
    if pure.is_absolute() or ".." in pure.parts:
        raise EvidenceError(f"{label}.path is unsafe: {source_path!r}")
    process = subprocess.run(
        ["git", "-C", str(repo), "show", f"{revision}:{pure.as_posix()}"],
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise EvidenceError(
            f"{label} cannot resolve {revision}:{source_path}: {detail or 'missing blob'}"
        )
    return process.stdout


def _validate_location(repo: Path, location: Any, label: str) -> None:
    if not isinstance(location, dict):
        raise EvidenceError(f"{label} must be an object")
    blob = _git_blob(repo, location.get("revision"), location.get("path"), label)
    start = location.get("startLine")
    end = location.get("endLine")
    if not isinstance(start, int) or isinstance(start, bool) or start < 1:
        raise EvidenceError(f"{label}.startLine must be a positive integer")
    if not isinstance(end, int) or isinstance(end, bool) or end < start:
        raise EvidenceError(f"{label}.endLine must be an integer >= startLine")
    line_count = len(blob.splitlines())
    if end > line_count:
        raise EvidenceError(
            f"{label} line range {start}-{end} exceeds {line_count} lines at the cited revision"
        )


def _command_script(command: str) -> str | None:
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError as exc:
        raise EvidenceError(f"command is not valid shell syntax: {exc}") from exc
    if not tokens:
        raise EvidenceError("command must not be empty")
    for index, token in enumerate(tokens):
        if token in {"python", "python3", "bash", "sh", "node", "pwsh", "powershell"}:
            for candidate in tokens[index + 1 :]:
                if candidate == "-m":
                    return None
                if candidate.startswith("-"):
                    continue
                return candidate if candidate.endswith(SCRIPT_SUFFIXES) or "/" in candidate else None
        if token.startswith("./") or token.endswith(SCRIPT_SUFFIXES):
            return token
    return None


def _validate_command(repo: Path, command: Any, label: str) -> None:
    if not isinstance(command, str) or not command.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    script = _command_script(command)
    if script is None:
        return
    pure = PurePosixPath(script)
    if pure.is_absolute() or ".." in pure.parts:
        raise EvidenceError(f"{label} references an unsafe script path: {script!r}")
    target = repo.joinpath(*pure.parts)
    if not target.is_file() or target.is_symlink():
        raise EvidenceError(f"{label} references an absent script: {script!r}")


def _require_nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")


def validate_package(payload: Mapping[str, Any], package_path: Path, repo: Path) -> tuple[int, int]:
    if payload.get("schema") != SCHEMA:
        raise EvidenceError(f"schema must be {SCHEMA!r}")
    release_revision = payload.get("releaseRevision")
    if not isinstance(release_revision, str) or not REVISION_RE.fullmatch(release_revision):
        raise EvidenceError("releaseRevision must be an exact 40-character commit")

    root = package_path.parent.resolve()
    roster = payload.get("sourceRoster")
    if not isinstance(roster, dict):
        raise EvidenceError("sourceRoster must be an object")
    roster_path = _safe_local_path(root, roster.get("path"), "sourceRoster.path")
    _expect_digest(roster_path, roster.get("sha256"), "sourceRoster.sha256")
    try:
        roster_text = roster_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise EvidenceError(f"source roster must be UTF-8 text: {exc}") from exc
    roster_ids = set(FINDING_RE.findall(roster_text))
    if not roster_ids:
        raise EvidenceError("source roster contains no K3-203 finding IDs")

    expected = payload.get("expectedFindingIds")
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        raise EvidenceError("expectedFindingIds must be an array of strings")
    if len(expected) != len(set(expected)):
        raise EvidenceError("expectedFindingIds contains duplicates")
    if set(expected) != roster_ids:
        raise EvidenceError(
            "expectedFindingIds does not equal the IDs extracted from the preserved source roster"
        )

    records = payload.get("findings")
    if not isinstance(records, list):
        raise EvidenceError("findings must be an array")
    record_ids: list[str] = []
    for index, record in enumerate(records):
        label = f"findings[{index}]"
        if not isinstance(record, dict):
            raise EvidenceError(f"{label} must be an object")
        finding_id = record.get("id")
        if not isinstance(finding_id, str) or finding_id not in roster_ids:
            raise EvidenceError(f"{label}.id is not present in the source roster")
        record_ids.append(finding_id)
        _require_nonempty(record.get("title"), f"{label}.title")

        locations = record.get("sourceLocations")
        if not isinstance(locations, list) or not locations:
            raise EvidenceError(f"{label}.sourceLocations must be a non-empty array")
        for location_index, location in enumerate(locations):
            _validate_location(repo, location, f"{label}.sourceLocations[{location_index}]")

        fixture = record.get("fixture")
        if not isinstance(fixture, dict):
            raise EvidenceError(f"{label}.fixture must be an object")
        fixture_path = _safe_local_path(root, fixture.get("path"), f"{label}.fixture.path")
        _expect_digest(fixture_path, fixture.get("sha256"), f"{label}.fixture.sha256")

        execution = record.get("execution")
        if not isinstance(execution, dict):
            raise EvidenceError(f"{label}.execution must be an object")
        _validate_command(repo, execution.get("command"), f"{label}.execution.command")
        expected_exit = execution.get("expectedExit")
        observed_exit = execution.get("observedExit")
        if not isinstance(expected_exit, int) or isinstance(expected_exit, bool):
            raise EvidenceError(f"{label}.execution.expectedExit must be an integer")
        if not isinstance(observed_exit, int) or isinstance(observed_exit, bool):
            raise EvidenceError(f"{label}.execution.observedExit must be an integer")
        output_path = _safe_local_path(
            root, execution.get("outputPath"), f"{label}.execution.outputPath"
        )
        _expect_digest(
            output_path, execution.get("outputSha256"), f"{label}.execution.outputSha256"
        )
        if execution.get("fixtureSha256") != fixture.get("sha256"):
            raise EvidenceError(
                f"{label}.execution.fixtureSha256 does not bind the named fixture bytes"
            )

        discriminator = record.get("discriminator")
        if not isinstance(discriminator, dict):
            raise EvidenceError(f"{label}.discriminator must be an object")
        _require_nonempty(discriminator.get("description"), f"{label}.discriminator.description")
        if not isinstance(discriminator.get("passed"), bool):
            raise EvidenceError(f"{label}.discriminator.passed must be boolean")

        disposition = record.get("disposition")
        if not isinstance(disposition, dict):
            raise EvidenceError(f"{label}.disposition must be an object")
        status = disposition.get("status")
        if status not in STATUSES:
            raise EvidenceError(f"{label}.disposition.status is unsupported: {status!r}")
        _require_nonempty(disposition.get("rationale"), f"{label}.disposition.rationale")
        if status in {"confirmed", "fixed", "held"} and discriminator.get("passed") is not True:
            raise EvidenceError(
                f"{label} cannot claim {status!r} without a passing discriminator"
            )
        if observed_exit != expected_exit and discriminator.get("passed") is True:
            raise EvidenceError(
                f"{label} cannot pass while observedExit differs from expectedExit"
            )

    if len(record_ids) != len(set(record_ids)):
        raise EvidenceError("findings contains duplicate IDs")
    if set(record_ids) != roster_ids:
        missing = sorted(roster_ids - set(record_ids))
        extra = sorted(set(record_ids) - roster_ids)
        raise EvidenceError(f"finding records are incomplete: missing={missing} extra={extra}")
    return len(records), len(roster_ids)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    root = Path(__file__).resolve().parents[1]
    parser.add_argument("package", type=Path)
    parser.add_argument("--repo", type=Path, default=root)
    args = parser.parse_args(argv)
    try:
        payload = _load_object(args.package)
        records, roster = validate_package(payload, args.package.resolve(), args.repo.resolve())
    except EvidenceError as exc:
        print(f"EVIDENCE INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"EVIDENCE VALID records={records} roster={roster} schema={SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
