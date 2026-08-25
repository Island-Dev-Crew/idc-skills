#!/usr/bin/env python3
"""Validate a bounded IDC security-evidence v2 ledger and its preserved bytes."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


SCHEMA = "idc.security-evidence/v2"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$", re.ASCII)
REVISION_RE = re.compile(r"^[0-9a-f]{40}$", re.ASCII)
FINDING_ID_RE = re.compile(r"^K3-203-[0-9]{3}$", re.ASCII)
FINDING_SCAN_RE = re.compile(r"(?<![\w-])K3-203-[0-9]{3}(?![\w-])")
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

MAX_PACKAGE_BYTES = 2 * 1024 * 1024
MAX_LOCAL_FILE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BUNDLE_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BUNDLE_MEMBERS = 4096
MAX_SOURCE_BUNDLE_MEMBER_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BUNDLE_TOTAL_BYTES = 128 * 1024 * 1024
MAX_GIT_BLOB_BYTES = 8 * 1024 * 1024
MAX_FINDINGS = 128
MAX_SOURCE_LOCATIONS = 16
MAX_SEMANTIC_ASSERTIONS = 16
MAX_PATH_BYTES = 1024
MAX_TEXT_BYTES = 16 * 1024
GIT_TIMEOUT_SECONDS = 15


class EvidenceError(RuntimeError):
    pass


def _exact_keys(value: Any, required: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    keys = set(value)
    missing = sorted(required - keys)
    extra = sorted(keys - required)
    if missing:
        raise EvidenceError(f"{label} is missing required keys: {missing}")
    if extra:
        raise EvidenceError(f"{label} has unexpected keys: {extra}")
    return value


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _read_regular_bounded(path: Path, limit: int, label: str) -> bytes:
    try:
        before = path.lstat()
    except OSError as exc:
        raise EvidenceError(f"{label} does not exist: {exc}") from exc
    if not stat.S_ISREG(before.st_mode):
        raise EvidenceError(f"{label} must be a regular non-symlink file")
    if before.st_size > limit:
        raise EvidenceError(f"{label} exceeds the {limit}-byte size limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise EvidenceError(f"cannot open {label} safely: {exc}") from exc
    try:
        opened = os.fstat(descriptor)
        identity = lambda item: (
            item.st_dev,
            item.st_ino,
            item.st_mode,
            item.st_size,
            item.st_mtime_ns,
        )
        if identity(before) != identity(opened) or not stat.S_ISREG(opened.st_mode):
            raise EvidenceError(f"{label} changed before capture")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            data = handle.read(limit + 1)
        after = os.fstat(descriptor)
        if identity(opened) != identity(after):
            raise EvidenceError(f"{label} changed during capture")
    finally:
        os.close(descriptor)
    if len(data) > limit:
        raise EvidenceError(f"{label} exceeds the {limit}-byte size limit")
    if len(data) != before.st_size:
        raise EvidenceError(f"{label} size changed during capture")
    return data


def _load_object(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise EvidenceError("evidence package must not be a symlink")
    data = _read_regular_bounded(path, MAX_PACKAGE_BYTES, "evidence package")
    try:
        text = data.decode("utf-8")
        value = json.loads(text, object_pairs_hook=_reject_duplicate_keys)
    except EvidenceError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise EvidenceError(f"invalid evidence package {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError("evidence package must be a JSON object")
    return value


def _safe_relative(value: Any, label: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} must be a non-empty relative path")
    if len(value.encode("utf-8")) > MAX_PATH_BYTES:
        raise EvidenceError(f"{label} exceeds the path length limit")
    if "\\" in value or any(
        unicodedata.category(character) in {"Cc", "Cf"} for character in value
    ):
        raise EvidenceError(f"{label} is not a safe relative path: {value!r}")
    pure = PurePosixPath(value)
    if (
        pure.is_absolute()
        or value in {".", ".."}
        or ".." in pure.parts
        or pure.as_posix() != value
    ):
        raise EvidenceError(f"{label} is not a safe relative path: {value!r}")
    return pure


def _safe_local_path(root: Path, value: Any, label: str) -> Path:
    relative = _safe_relative(value, label)
    candidate = root
    for index, part in enumerate(relative.parts):
        candidate = candidate / part
        try:
            mode = candidate.lstat().st_mode
        except OSError as exc:
            raise EvidenceError(f"{label} does not exist: {value!r}: {exc}") from exc
        if stat.S_ISLNK(mode):
            raise EvidenceError(f"{label} has a symlink ancestor: {value!r}")
        if index < len(relative.parts) - 1 and not stat.S_ISDIR(mode):
            raise EvidenceError(f"{label} has a non-directory ancestor: {value!r}")
    if not candidate.is_file():
        raise EvidenceError(f"{label} must be a regular non-symlink file: {value!r}")
    return candidate


def _digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _expect_digest_bytes(data: bytes, expected: Any, label: str) -> None:
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        raise EvidenceError(f"{label} must be a lowercase SHA-256 digest")
    actual = _digest_bytes(data)
    if actual != expected:
        raise EvidenceError(f"{label} mismatch: expected {expected}, got {actual}")


def _require_nonempty(value: Any, label: str, *, limit: int = MAX_TEXT_BYTES) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    if len(value.encode("utf-8")) > limit:
        raise EvidenceError(f"{label} exceeds the {limit}-byte text limit")
    return value


class SourceBundle:
    """A digest-bound, fully indexed safe tar archive."""

    def __init__(self, root: Path, specification: Any):
        spec = _exact_keys(specification, {"path", "sha256"}, "sourceBundle")
        path = _safe_local_path(root, spec.get("path"), "sourceBundle.path")
        archive_bytes = _read_regular_bounded(
            path, MAX_SOURCE_BUNDLE_BYTES, "sourceBundle.path"
        )
        _expect_digest_bytes(archive_bytes, spec.get("sha256"), "sourceBundle.sha256")
        self._members: dict[str, bytes] = {}
        try:
            with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
                members = archive.getmembers()
                if len(members) > MAX_SOURCE_BUNDLE_MEMBERS:
                    raise EvidenceError(
                        "source bundle member count exceeds "
                        f"{MAX_SOURCE_BUNDLE_MEMBERS}"
                    )
                names: set[str] = set()
                total = 0
                for member in members:
                    try:
                        normalized = _safe_relative(member.name, "source bundle member")
                    except EvidenceError as exc:
                        raise EvidenceError(
                            f"unsafe source bundle member {member.name!r}: {exc}"
                        ) from exc
                    name = normalized.as_posix()
                    if name in names:
                        raise EvidenceError(f"duplicate source bundle member: {name!r}")
                    names.add(name)
                    if member.isdir():
                        if member.size != 0:
                            raise EvidenceError(
                                f"source bundle directory has nonzero size: {name!r}"
                            )
                        continue
                    if not member.isfile():
                        raise EvidenceError(
                            f"source bundle member is not a regular file or directory: {name!r}"
                        )
                    if member.size > MAX_SOURCE_BUNDLE_MEMBER_BYTES:
                        raise EvidenceError(
                            f"source bundle member exceeds size limit: {name!r}"
                        )
                    total += member.size
                    if total > MAX_SOURCE_BUNDLE_TOTAL_BYTES:
                        raise EvidenceError("source bundle expanded bytes exceed total size limit")
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise EvidenceError(f"cannot read source bundle member: {name!r}")
                    data = stream.read(member.size + 1)
                    if len(data) != member.size:
                        raise EvidenceError(
                            f"source bundle member size differs from header: {name!r}"
                        )
                    self._members[name] = data
        except EvidenceError:
            raise
        except (tarfile.TarError, OSError) as exc:
            raise EvidenceError(f"sourceBundle.path is not a valid bounded gzip tar: {exc}") from exc

    def read(self, member_name: Any, label: str) -> bytes:
        member = _safe_relative(member_name, label).as_posix()
        try:
            return self._members[member]
        except KeyError as exc:
            raise EvidenceError(f"{label} is not a regular source bundle member: {member!r}") from exc


def _safe_git_environment() -> dict[str, str]:
    return {
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "LC_ALL": "C",
    }


def _git_command(repo: Path, arguments: list[str], label: str) -> subprocess.CompletedProcess[bytes]:
    git = shutil.which("git", path=os.defpath)
    if git is None:
        raise EvidenceError("cannot resolve the system Git executable")
    try:
        process = subprocess.run(
            [git, "-C", str(repo), "--no-pager", *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=GIT_TIMEOUT_SECONDS,
            env=_safe_git_environment(),
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise EvidenceError(f"{label} Git lookup failed: {exc}") from exc
    return process


def _git_error(stderr: bytes) -> str:
    text = stderr[:2048].decode("utf-8", errors="replace")
    return "".join(
        character
        if character == "\t" or unicodedata.category(character) not in {"Cc", "Cf"}
        else " "
        for character in text
    ).strip()


def _git_blob(repo: Path, revision: Any, source_path: Any, label: str) -> bytes:
    if not isinstance(revision, str) or REVISION_RE.fullmatch(revision) is None:
        raise EvidenceError(f"{label}.revision must be an exact 40-character commit")
    pure = _safe_relative(source_path, f"{label}.path")
    if ":" in pure.as_posix() or pure.as_posix().startswith("-"):
        raise EvidenceError(f"{label}.path is unsafe for git show: {source_path!r}")
    specification = f"{revision}:{pure.as_posix()}"
    size_process = _git_command(repo, ["cat-file", "-s", specification], label)
    if size_process.returncode != 0:
        detail = _git_error(size_process.stderr)
        raise EvidenceError(
            f"{label} cannot resolve {revision}:{source_path}: {detail or 'missing blob'}"
        )
    try:
        size = int(size_process.stdout.strip())
    except ValueError as exc:
        raise EvidenceError(f"{label} Git returned an invalid blob size") from exc
    if size < 0 or size > MAX_GIT_BLOB_BYTES:
        raise EvidenceError(f"{label} cited blob exceeds the bounded git-show size limit")
    process = _git_command(
        repo,
        ["show", "--no-ext-diff", "--no-textconv", specification],
        label,
    )
    if process.returncode != 0:
        detail = _git_error(process.stderr)
        raise EvidenceError(
            f"{label} cannot resolve {revision}:{source_path}: {detail or 'missing blob'}"
        )
    if len(process.stdout) != size or len(process.stdout) > MAX_GIT_BLOB_BYTES:
        raise EvidenceError(f"{label} bounded git show returned an unexpected byte count")
    return process.stdout


def _validate_location(
    repo: Path, location: Any, release_revision: str, label: str
) -> None:
    value = _exact_keys(
        location,
        {"revision", "path", "startLine", "endLine"},
        label,
    )
    if value.get("revision") != release_revision:
        raise EvidenceError(f"{label}.revision must equal releaseRevision")
    blob = _git_blob(repo, value.get("revision"), value.get("path"), label)
    start = value.get("startLine")
    end = value.get("endLine")
    if not isinstance(start, int) or isinstance(start, bool) or start < 1:
        raise EvidenceError(f"{label}.startLine must be a positive integer")
    if not isinstance(end, int) or isinstance(end, bool) or end < start:
        raise EvidenceError(f"{label}.endLine must be an integer >= startLine")
    line_count = len(blob.splitlines())
    if end > line_count:
        raise EvidenceError(
            f"{label} line range {start}-{end} exceeds {line_count} lines at the cited revision"
        )


def _resolve_fixture(
    root: Path, fixture: Any, bundle: SourceBundle | None, label: str
) -> tuple[bytes, str]:
    if not isinstance(fixture, dict):
        raise EvidenceError(f"{label} must be an object")
    anchor = fixture.get("anchor")
    if anchor == "candidate-preserved":
        value = _exact_keys(fixture, {"anchor", "path", "sha256"}, label)
        path = _safe_local_path(root, value.get("path"), f"{label}.path")
        data = _read_regular_bounded(path, MAX_LOCAL_FILE_BYTES, f"{label}.path")
    elif anchor == "source-bundle":
        value = _exact_keys(fixture, {"anchor", "member", "sha256"}, label)
        if bundle is None:
            raise EvidenceError(f"{label} requires sourceBundle")
        data = bundle.read(value.get("member"), f"{label}.member")
    else:
        raise EvidenceError(
            f"{label}.anchor must be 'candidate-preserved' or 'source-bundle'"
        )
    expected = value.get("sha256")
    _expect_digest_bytes(data, expected, f"{label}.sha256")
    return data, str(expected)


def _resolve_capture(
    root: Path, capture: Any, bundle: SourceBundle | None, label: str
) -> tuple[bytes, str]:
    value = _exact_keys(
        capture,
        {"kind", "source", "sha256", "fixtureSha256"},
        label,
    )
    if value.get("kind") != "preserved-observation":
        raise EvidenceError(f"{label}.kind must be 'preserved-observation'")
    source = value.get("source")
    if not isinstance(source, dict):
        raise EvidenceError(f"{label}.source must be an object")
    source_type = source.get("type")
    if source_type == "local":
        source_value = _exact_keys(source, {"type", "path"}, f"{label}.source")
        path = _safe_local_path(
            root, source_value.get("path"), f"{label}.source.path"
        )
        data = _read_regular_bounded(path, MAX_LOCAL_FILE_BYTES, f"{label}.source.path")
    elif source_type == "bundle-member":
        source_value = _exact_keys(source, {"type", "member"}, f"{label}.source")
        if bundle is None:
            raise EvidenceError(f"{label}.source requires sourceBundle")
        data = bundle.read(
            source_value.get("member"), f"{label}.source.member"
        )
    else:
        raise EvidenceError(f"{label}.source.type must be 'local' or 'bundle-member'")
    expected = value.get("sha256")
    if not isinstance(expected, str) or SHA256_RE.fullmatch(expected) is None:
        raise EvidenceError(f"{label}.sha256 must be a lowercase SHA-256 digest")
    actual = _digest_bytes(data)
    if actual != expected:
        raise EvidenceError(
            f"{label} outputSha256 mismatch (capture.sha256): expected {expected}, got {actual}"
        )
    return data, str(value.get("fixtureSha256"))


def _validate_semantic_binding(
    semantic: Any, fixture_bytes: bytes, capture_bytes: bytes, label: str
) -> None:
    value = _exact_keys(semantic, {"description", "assertions"}, label)
    _require_nonempty(value.get("description"), f"{label}.description")
    assertions = value.get("assertions")
    if (
        not isinstance(assertions, list)
        or not assertions
        or len(assertions) > MAX_SEMANTIC_ASSERTIONS
    ):
        raise EvidenceError(
            f"{label}.assertions must contain 1-{MAX_SEMANTIC_ASSERTIONS} entries"
        )
    targets: dict[str, bytes] = {"fixture": fixture_bytes, "capture": capture_bytes}
    for index, assertion in enumerate(assertions):
        assertion_label = f"{label}.assertions[{index}]"
        item = _exact_keys(assertion, {"target", "contains"}, assertion_label)
        target = item.get("target")
        if target not in targets:
            raise EvidenceError(f"{assertion_label}.target must be 'fixture' or 'capture'")
        contains = _require_nonempty(
            item.get("contains"), f"{assertion_label}.contains", limit=4096
        )
        target_bytes = targets[str(target)]
        try:
            target_bytes.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise EvidenceError(
                f"{assertion_label} target is not valid UTF-8: {exc}"
            ) from exc
        if contains.encode("utf-8") not in target_bytes:
            raise EvidenceError(
                f"{assertion_label} semantic assertion is absent from {target} bytes"
            )


def validate_package(
    payload: Mapping[str, Any], package_path: Path, repo: Path
) -> tuple[int, int]:
    top = _exact_keys(
        payload,
        {
            "schema",
            "releaseRevision",
            "sourceBundle",
            "sourceRoster",
            "expectedFindingIds",
            "findings",
        },
        "evidence package",
    )
    if top.get("schema") != SCHEMA:
        raise EvidenceError(f"schema must be {SCHEMA!r}")
    release_revision = top.get("releaseRevision")
    if not isinstance(release_revision, str) or REVISION_RE.fullmatch(release_revision) is None:
        raise EvidenceError("releaseRevision must be an exact 40-character commit")

    root = package_path.parent.resolve(strict=True)
    bundle = SourceBundle(root, top.get("sourceBundle"))
    roster = _exact_keys(top.get("sourceRoster"), {"path", "sha256"}, "sourceRoster")
    roster_path = _safe_local_path(root, roster.get("path"), "sourceRoster.path")
    roster_bytes = _read_regular_bounded(
        roster_path, MAX_LOCAL_FILE_BYTES, "sourceRoster.path"
    )
    _expect_digest_bytes(roster_bytes, roster.get("sha256"), "sourceRoster.sha256")
    try:
        roster_text = roster_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise EvidenceError(f"source roster must be UTF-8 text: {exc}") from exc
    roster_ids = set(FINDING_SCAN_RE.findall(roster_text))
    if not roster_ids:
        if "K3-203-" in roster_text:
            raise EvidenceError("source roster finding IDs must use exact ASCII K3-203-NNN form")
        raise EvidenceError("source roster contains no K3-203 finding IDs")

    expected = top.get("expectedFindingIds")
    if (
        not isinstance(expected, list)
        or len(expected) > MAX_FINDINGS
        or not all(
            isinstance(item, str) and FINDING_ID_RE.fullmatch(item) is not None
            for item in expected
        )
    ):
        raise EvidenceError(
            f"expectedFindingIds must contain at most {MAX_FINDINGS} exact ASCII K3-203-NNN IDs"
        )
    if len(expected) != len(set(expected)):
        raise EvidenceError("expectedFindingIds contains duplicates")
    if set(expected) != roster_ids:
        raise EvidenceError(
            "expectedFindingIds does not equal the IDs extracted from the preserved source roster"
        )

    records = top.get("findings")
    if not isinstance(records, list) or len(records) > MAX_FINDINGS:
        raise EvidenceError(f"findings must be an array of at most {MAX_FINDINGS} records")
    record_ids: list[str] = []
    for index, record in enumerate(records):
        label = f"findings[{index}]"
        value = _exact_keys(
            record,
            {
                "id",
                "title",
                "sourceLocations",
                "fixture",
                "capture",
                "semanticBinding",
                "discriminator",
                "disposition",
            },
            label,
        )
        finding_id = value.get("id")
        if not isinstance(finding_id, str) or FINDING_ID_RE.fullmatch(finding_id) is None:
            raise EvidenceError(f"{label}.id must be an exact ASCII K3-203-NNN ID")
        if finding_id not in roster_ids:
            raise EvidenceError(f"{label}.id is not present in the source roster")
        record_ids.append(finding_id)
        _require_nonempty(value.get("title"), f"{label}.title")

        locations = value.get("sourceLocations")
        if (
            not isinstance(locations, list)
            or not locations
            or len(locations) > MAX_SOURCE_LOCATIONS
        ):
            raise EvidenceError(
                f"{label}.sourceLocations must contain 1-{MAX_SOURCE_LOCATIONS} entries"
            )
        for location_index, location in enumerate(locations):
            _validate_location(
                repo,
                location,
                release_revision,
                f"{label}.sourceLocations[{location_index}]",
            )

        fixture_bytes, fixture_digest = _resolve_fixture(
            root, value.get("fixture"), bundle, f"{label}.fixture"
        )
        capture_bytes, bound_fixture_digest = _resolve_capture(
            root, value.get("capture"), bundle, f"{label}.capture"
        )
        if bound_fixture_digest != fixture_digest:
            raise EvidenceError(
                f"{label}.capture.fixtureSha256 does not bind the named fixture bytes"
            )
        _validate_semantic_binding(
            value.get("semanticBinding"),
            fixture_bytes,
            capture_bytes,
            f"{label}.semanticBinding",
        )

        discriminator = _exact_keys(
            value.get("discriminator"),
            {"description", "passed"},
            f"{label}.discriminator",
        )
        _require_nonempty(
            discriminator.get("description"), f"{label}.discriminator.description"
        )
        if not isinstance(discriminator.get("passed"), bool):
            raise EvidenceError(f"{label}.discriminator.passed must be boolean")

        disposition = _exact_keys(
            value.get("disposition"),
            {"status", "rationale"},
            f"{label}.disposition",
        )
        status = disposition.get("status")
        if status not in STATUSES:
            raise EvidenceError(f"{label}.disposition.status is unsupported: {status!r}")
        _require_nonempty(
            disposition.get("rationale"), f"{label}.disposition.rationale"
        )
        if status in {"confirmed", "fixed", "held"} and discriminator.get("passed") is not True:
            raise EvidenceError(
                f"{label} cannot claim {status!r} without a passing discriminator"
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
        package_path = args.package.absolute()
        payload = _load_object(package_path)
        records, roster = validate_package(payload, package_path, args.repo.resolve(strict=True))
    except (EvidenceError, OSError) as exc:
        print(f"EVIDENCE INVALID: {exc}", file=sys.stderr)
        return 1
    print(f"EVIDENCE VALID records={records} roster={roster} schema={SCHEMA}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
