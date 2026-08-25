#!/usr/bin/env python3
"""Dependency-free IDC threshold-root and release-statement verification.

The cryptographic primitive is OpenSSH sshsig. The trust model follows the TUF
root-update rules: an initial root arrives out of band; every next root is exactly
version N+1 and is authorized by both the old and new root thresholds.
"""

from __future__ import annotations

import datetime as dt
import base64
import binascii
import hashlib
import json
import os
import re
import stat
import subprocess
import tarfile
import tempfile
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT_SCHEMA = "idc-skills-root/v1"
RELEASE_SCHEMA = "idc-skills-release-statement/v1"
MANIFEST_SCHEMA = "idc-skill-integrity/v3"
INSTALL_INVENTORY_SCHEMA = "idc-skills-install-inventory/v1"
RELEASE_INDEX_SCHEMA = "idc-skills-release-index/v1"
ROOT_NAMESPACE = "idc-skills-root-v1"
RELEASE_NAMESPACE = "idc-skills-release-statement-v1"
MAX_METADATA_BYTES = 512 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_RELEASE_INDEX_BYTES = 4 * 1024 * 1024
MAX_RELEASE_ARCHIVE_BYTES = 256 * 1024 * 1024
MAX_SIGNATURES = 64
MAX_KEYS = 64
MAX_ROOT_UPDATES = 32
ROOT_CHECKPOINT_SCHEMA = "idc-skills-root-checkpoint/v3"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")
FINGERPRINT_RE = re.compile(r"^SHA256:[A-Za-z0-9+/]{43}$")
INSTALL_ROOT_LABELS = ("agents", "claude", "pi", "hermes")
MAX_SEQUENCE = (1 << 53) - 1
MAX_CLOCK_SKEW_SECONDS = 300
MAX_RELEASE_INDEX_LIFETIME_SECONDS = 31 * 24 * 60 * 60


class TrustError(RuntimeError):
    """A trust or exact-object requirement failed."""


@dataclass(frozen=True)
class ParsedEnvelope:
    value: Mapping[str, Any]
    signed: Mapping[str, Any]
    signed_bytes: bytes
    digest: str


def canonical_json(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"metadata is not canonical-JSON compatible: {exc}") from exc
    return (text + "\n").encode("utf-8")


def canonical_manifest(value: Any) -> bytes:
    """Match the integrity verifier's established manifest wire encoding."""
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"manifest is not canonical-JSON compatible: {exc}") from exc
    return (text + "\n").encode("utf-8")


def canonical_registry(value: Any) -> bytes:
    """Match the registry producer's stable semantic/source-order encoding."""
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"registry is not canonical-JSON compatible: {exc}") from exc
    return (text + "\n").encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def git_blob_oid(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data, usedforsecurity=False).hexdigest()


def content_signing_record(public_key_path: Path, allowed_signers_path: Path) -> dict[str, str]:
    """Bind the exact content-signing anchor authorized by a release threshold."""
    public_data = _regular_bytes(public_key_path, "content public key", 64 * 1024)
    allowed_data = _regular_bytes(allowed_signers_path, "content allowed_signers", 64 * 1024)
    try:
        public_text = public_data.decode("utf-8")
        allowed_text = allowed_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise TrustError("content-signing anchor files must be UTF-8") from exc
    public_parts = public_text.split()
    allowed_lines = allowed_text.splitlines()
    if len(public_parts) < 2 or public_parts[0] != "ssh-ed25519":
        raise TrustError("content public key must be one ssh-ed25519 public key")
    if len(allowed_lines) != 1 or allowed_lines[0].split() != [
        "idc-skills",
        public_parts[0],
        public_parts[1],
    ]:
        raise TrustError("content allowed_signers must authorize only idc-skills with the public key")
    try:
        key_blob = base64.b64decode(public_parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise TrustError("content public key body is not canonical base64") from exc
    fingerprint = base64.b64encode(hashlib.sha256(key_blob).digest()).decode("ascii").rstrip("=")
    return {
        "allowedSignersSHA256": sha256_bytes(allowed_data),
        "fingerprint": "SHA256:" + fingerprint,
        "publicKeySHA256": sha256_bytes(public_data),
    }


def _exact_keys(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise TrustError(f"{label} must be an object")
    actual = set(value)
    if actual != keys:
        raise TrustError(
            f"{label} keys differ: missing={sorted(keys - actual)} extra={sorted(actual - keys)}"
        )
    return value


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise TrustError(f"{label} must be an integer between 1 and {MAX_SEQUENCE}")
    return value


def parse_manifest_identity(raw: bytes, label: str = "integrity manifest") -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_manifest(value) != raw:
        raise TrustError(f"{label} must be one canonical JSON object")
    if value.get("schema") != MANIFEST_SCHEMA or value.get("profile") != "release":
        raise TrustError(f"{label} must be a release-profile {MANIFEST_SCHEMA} object")
    release = value.get("release")
    if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
        raise TrustError(f"{label}.release must be semantic-version shaped")
    sequence = _positive_int(value.get("manifestSequence"), f"{label}.manifestSequence")
    count = value.get("skillCount")
    names = value.get("skillNames")
    if (
        type(count) is not int
        or count != 50
        or not isinstance(names, list)
        or len(names) != count
        or not all(isinstance(name, str) and name for name in names)
        or names != sorted(names)
        or len(set(names)) != count
    ):
        raise TrustError(f"{label} must bind exactly 50 sorted unique skill names")
    repository_files = value.get("repositoryFiles")
    if not isinstance(repository_files, dict) or not repository_files:
        raise TrustError(f"{label}.repositoryFiles must be a non-empty object")
    return {
        "manifestSequence": sequence,
        "release": release,
        "repositoryFiles": repository_files,
        "skillCount": count,
        "skillNames": list(names),
    }


def manifest_file_record(
    manifest_identity: Mapping[str, Any], relative: str
) -> Mapping[str, Any]:
    files = manifest_identity.get("repositoryFiles")
    record = files.get(relative) if isinstance(files, dict) else None
    record = _exact_keys(
        record,
        {"posixMode", "sha256", "size"},
        f"integrity manifest repositoryFiles[{relative!r}]",
    )
    if not isinstance(record["sha256"], str) or not SHA256_RE.fullmatch(record["sha256"]):
        raise TrustError(f"integrity manifest record {relative} has an invalid digest")
    if type(record["size"]) is not int or not 0 <= record["size"] <= 64 * 1024 * 1024:
        raise TrustError(f"integrity manifest record {relative} has an invalid size")
    if type(record["posixMode"]) is not int or not 0 <= record["posixMode"] <= 0o777:
        raise TrustError(f"integrity manifest record {relative} has an invalid POSIX mode")
    return record


def build_install_inventory(manifest_data: bytes) -> dict[str, Any]:
    manifest = parse_manifest_identity(manifest_data)
    manifest_digest = sha256_bytes(manifest_data)
    return {
        "authority": "pre-install-expectation-only",
        "manifest": {
            "manifestSequence": manifest["manifestSequence"],
            "sha256": manifest_digest,
            "size": len(manifest_data),
        },
        "release": manifest["release"],
        "schema": INSTALL_INVENTORY_SCHEMA,
        "skills": {
            "count": manifest["skillCount"],
            "names": manifest["skillNames"],
        },
        "targets": [
            {"label": label, "releaseParity": "required"}
            for label in INSTALL_ROOT_LABELS
        ],
    }


def parse_install_inventory(raw: bytes, manifest_data: bytes) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"install inventory is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_json(value) != raw:
        raise TrustError("install inventory must be one canonical JSON object")
    _exact_keys(
        value,
        {"authority", "manifest", "release", "schema", "skills", "targets"},
        "install inventory",
    )
    expected = build_install_inventory(manifest_data)
    if value != expected:
        raise TrustError("install inventory differs from the signed manifest expectation")
    return value


def parse_registry(
    raw: bytes, manifest_identity: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"skills registry is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_registry(value) != raw:
        raise TrustError("skills registry must be one canonical JSON object")
    registry = _exact_keys(
        value,
        {
            "anchor",
            "buildOrder",
            "bundleName",
            "dualHarness",
            "harnessContract",
            "manifestSequence",
            "name",
            "promotesTo",
            "release",
            "skills",
            "staging",
            "version",
        },
        "skills registry",
    )
    if registry["version"] != 1:
        raise TrustError("skills registry version must be 1")
    release = registry["release"]
    if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
        raise TrustError("skills registry release is invalid")
    sequence = _index_sequence(
        registry["manifestSequence"], "skills registry manifestSequence"
    )
    build_order = registry["buildOrder"]
    skills = registry["skills"]
    if (
        not isinstance(build_order, list)
        or len(build_order) != 50
        or not all(isinstance(name, str) and name for name in build_order)
        or len(set(build_order)) != 50
        or not isinstance(skills, list)
        or len(skills) != 50
    ):
        raise TrustError("skills registry must contain 50 unique ordered skills")
    observed: list[str] = []
    for position, raw_skill in enumerate(skills):
        skill = _exact_keys(
            raw_skill,
            {"invocation", "name", "path", "provenance", "summary", "triggers"},
            f"skills registry skills[{position}]",
        )
        name = skill["name"]
        if (
            not isinstance(name, str)
            or not name
            or skill["path"] != name
            or skill["invocation"] not in {"model", "user"}
            or not isinstance(skill["provenance"], str)
            or not skill["provenance"]
            or not isinstance(skill["summary"], str)
            or not skill["summary"]
            or not isinstance(skill["triggers"], list)
            or not skill["triggers"]
            or not all(isinstance(trigger, str) and trigger for trigger in skill["triggers"])
        ):
            raise TrustError(f"skills registry skill record is invalid at position {position}")
        observed.append(name)
    if observed != build_order:
        raise TrustError("skills registry buildOrder differs from skill record order")
    if manifest_identity is not None:
        if release != manifest_identity["release"]:
            raise TrustError("skills registry release differs from integrity manifest")
        if sequence != manifest_identity["manifestSequence"]:
            raise TrustError("skills registry manifest sequence differs from integrity manifest")
        if sorted(observed) != manifest_identity["skillNames"]:
            raise TrustError("skills registry skill names differ from integrity manifest")
    return registry


def canonical_release_index(value: Any) -> bytes:
    try:
        text = json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            indent=2,
        )
    except (TypeError, ValueError) as exc:
        raise TrustError(f"release index is not canonical-JSON compatible: {exc}") from exc
    return (text + "\n").encode("utf-8")


def _index_sequence(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise TrustError(f"{label} must be an integer between 1 and {MAX_SEQUENCE}")
    return value


def _index_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        raise TrustError(f"release index {label} must be canonical UTC RFC3339 seconds")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise TrustError(f"release index {label} is not a real timestamp") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def parse_release_index(raw: bytes, *, now: dt.datetime | None = None) -> Mapping[str, Any]:
    if len(raw) > MAX_RELEASE_INDEX_BYTES:
        raise TrustError(f"release index exceeds {MAX_RELEASE_INDEX_BYTES} bytes")
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"release index is not strict UTF-8 JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical_release_index(value) != raw:
        raise TrustError("release index must be one canonical JSON object")
    index = _exact_keys(
        value,
        {"generatedAt", "indexSequence", "releases", "schema", "validUntil"},
        "release index",
    )
    if index["schema"] != RELEASE_INDEX_SCHEMA:
        raise TrustError("release index schema is unsupported")
    _index_sequence(index["indexSequence"], "release index indexSequence")
    generated = _index_utc(index["generatedAt"], "generatedAt")
    valid_until = _index_utc(index["validUntil"], "validUntil")
    current = _now(now)
    if generated > current + dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise TrustError("release index was generated implausibly far in the future")
    if valid_until <= current:
        raise TrustError("release index is expired")
    if valid_until <= generated:
        raise TrustError("release index validUntil must be later than generatedAt")
    if (valid_until - generated).total_seconds() > MAX_RELEASE_INDEX_LIFETIME_SECONDS:
        raise TrustError("release index validity window exceeds 31 days")
    raw_releases = index["releases"]
    if not isinstance(raw_releases, list) or not raw_releases:
        raise TrustError("release index releases must be a non-empty array")
    releases: list[dict[str, Any]] = []
    for position, raw_entry in enumerate(raw_releases):
        entry = _exact_keys(
            raw_entry,
            {
                "gitCommit",
                "launcherSHA256",
                "manifestSHA256",
                "manifestSequence",
                "release",
                "verifierSHA256",
            },
            f"release index releases[{position}]",
        )
        release = entry["release"]
        if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
            raise TrustError(f"release index releases[{position}].release is invalid")
        manifest_sequence = _index_sequence(
            entry["manifestSequence"],
            f"release index releases[{position}].manifestSequence",
        )
        for field in ("launcherSHA256", "manifestSHA256", "verifierSHA256"):
            if not isinstance(entry[field], str) or not SHA256_RE.fullmatch(entry[field]):
                raise TrustError(f"release index releases[{position}].{field} is invalid")
        if not isinstance(entry["gitCommit"], str) or not HEX40_RE.fullmatch(
            entry["gitCommit"]
        ):
            raise TrustError(f"release index releases[{position}].gitCommit is invalid")
        releases.append(
            {
                "gitCommit": entry["gitCommit"],
                "launcherSHA256": entry["launcherSHA256"],
                "manifestSHA256": entry["manifestSHA256"],
                "manifestSequence": manifest_sequence,
                "release": release,
                "verifierSHA256": entry["verifierSHA256"],
            }
        )
    sequences = [entry["manifestSequence"] for entry in releases]
    names = [entry["release"] for entry in releases]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise TrustError("release index entries must have strictly increasing unique sequences")
    if len(names) != len(set(names)):
        raise TrustError("release index entries must have unique release names")
    return {
        "generatedAt": index["generatedAt"],
        "indexSequence": index["indexSequence"],
        "releases": releases,
        "schema": index["schema"],
        "validUntil": index["validUntil"],
    }


def _expiry(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        raise TrustError(f"{label} must be canonical UTC RFC3339 seconds")
    try:
        parsed = dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as exc:
        raise TrustError(f"{label} is not a real timestamp") from exc
    return parsed.replace(tzinfo=dt.timezone.utc)


def _now(value: dt.datetime | None) -> dt.datetime:
    current = value or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise TrustError("verification time must be timezone-aware")
    return current.astimezone(dt.timezone.utc)


def _open_regular(path: Path, label: str, maximum: int) -> tuple[int, os.stat_result]:
    if path.is_symlink():
        raise TrustError(f"{label} must not be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TrustError(f"cannot open {label}: {path}: {exc}") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise TrustError(f"{label} must be a regular file")
    if metadata.st_size > maximum:
        os.close(descriptor)
        raise TrustError(f"{label} exceeds {maximum} bytes")
    return descriptor, metadata


def _same_snapshot(before: os.stat_result, after: os.stat_result) -> bool:
    return (
        before.st_dev,
        before.st_ino,
        before.st_size,
        before.st_mtime_ns,
        before.st_ctime_ns,
    ) == (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
        after.st_ctime_ns,
    )


def _regular_bytes(path: Path, label: str, maximum: int = MAX_METADATA_BYTES) -> bytes:
    descriptor, before = _open_regular(path, label, maximum)
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(maximum + 1)
        after = os.fstat(descriptor)
        if len(data) > maximum:
            raise TrustError(f"{label} exceeds {maximum} bytes")
        if len(data) != before.st_size or not _same_snapshot(before, after):
            raise TrustError(f"{label} changed while it was captured")
        return data
    except OSError as exc:
        raise TrustError(f"cannot read {label}: {path}: {exc}") from exc
    finally:
        os.close(descriptor)


def _regular_digest(path: Path, label: str, maximum: int) -> tuple[int, str]:
    descriptor, before = _open_regular(path, label, maximum)
    digest = hashlib.sha256()
    observed = 0
    try:
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                observed += len(block)
                if observed > maximum:
                    raise TrustError(f"{label} exceeds {maximum} bytes")
                digest.update(block)
        after = os.fstat(descriptor)
        if observed != before.st_size or not _same_snapshot(before, after):
            raise TrustError(f"{label} changed while it was hashed")
        return observed, "sha256:" + digest.hexdigest()
    except OSError as exc:
        raise TrustError(f"cannot hash {label}: {path}: {exc}") from exc
    finally:
        os.close(descriptor)


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve(strict=True).relative_to(parent.resolve(strict=True))
        return True
    except (OSError, ValueError):
        return False


def _validate_tool(path: Path, digest_pin: str, label: str, repo: Path) -> Path:
    if not path.is_absolute():
        raise TrustError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TrustError(f"cannot resolve {label}: {exc}") from exc
    if _is_within(resolved, repo):
        raise TrustError(f"{label} must be outside the candidate repository")
    if not SHA256_RE.fullmatch(digest_pin):
        raise TrustError(f"{label} digest pin must be sha256:<64 lowercase hex>")
    metadata = resolved.stat()
    if not stat.S_ISREG(metadata.st_mode) or not os.access(resolved, os.X_OK):
        raise TrustError(f"{label} must be a regular executable")
    if os.name != "nt" and (metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022):
        raise TrustError(f"{label} must be owner-controlled and not group/world writable")
    _, observed_digest = _regular_digest(resolved, label, 128 * 1024 * 1024)
    if observed_digest != digest_pin:
        raise TrustError(f"{label} bytes differ from the external digest pin")
    return resolved


def parse_envelope_bytes(raw: bytes, label: str) -> ParsedEnvelope:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"{label} is not strict UTF-8 JSON: {exc}") from exc
    _exact_keys(value, {"signatures", "signed"}, label)
    if raw != canonical_json(value):
        raise TrustError(f"{label} is not canonical JSON")
    signatures = value["signatures"]
    if not isinstance(signatures, list) or not 1 <= len(signatures) <= MAX_SIGNATURES:
        raise TrustError(f"{label}.signatures must contain 1 to {MAX_SIGNATURES} entries")
    seen: set[str] = set()
    for index, signature in enumerate(signatures):
        _exact_keys(signature, {"keyid", "sig"}, f"{label}.signatures[{index}]")
        keyid = signature["keyid"]
        sig = signature["sig"]
        if not isinstance(keyid, str) or not re.fullmatch(r"[0-9a-f]{64}", keyid):
            raise TrustError(f"{label}.signatures[{index}].keyid is invalid")
        if keyid in seen:
            raise TrustError(f"{label} has duplicate signature keyid {keyid}")
        seen.add(keyid)
        if (
            not isinstance(sig, str)
            or len(sig.encode("utf-8")) > 32 * 1024
            or not sig.startswith("-----BEGIN SSH SIGNATURE-----\n")
            or not sig.endswith("-----END SSH SIGNATURE-----\n")
        ):
            raise TrustError(f"{label}.signatures[{index}].sig is not a bounded sshsig")
    signed = value["signed"]
    if not isinstance(signed, dict):
        raise TrustError(f"{label}.signed must be an object")
    signed_bytes = canonical_json(signed)
    return ParsedEnvelope(value=value, signed=signed, signed_bytes=signed_bytes, digest=sha256_bytes(raw))


def load_envelope(path: Path, label: str) -> ParsedEnvelope:
    return parse_envelope_bytes(_regular_bytes(path, label), label)


def keyid_for(key: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(key)).hexdigest()


def _validate_key(keyid: str, value: Any, label: str) -> Mapping[str, Any]:
    key = _exact_keys(value, {"keytype", "scheme", "keyval"}, label)
    if key["keytype"] != "ed25519" or key["scheme"] != "ssh-ed25519":
        raise TrustError(f"{label} must be ssh-ed25519")
    keyval = _exact_keys(key["keyval"], {"public"}, f"{label}.keyval")
    public = keyval["public"]
    if not isinstance(public, str) or not re.fullmatch(r"ssh-ed25519 [A-Za-z0-9+/]+={0,2}", public):
        raise TrustError(f"{label}.keyval.public must be a comment-free ssh-ed25519 public key")
    if keyid_for(key) != keyid:
        raise TrustError(f"{label} does not match map keyid")
    return key


def parse_root(envelope: ParsedEnvelope, label: str = "root metadata") -> Mapping[str, Any]:
    root = _exact_keys(
        envelope.signed,
        {"_type", "consistentSnapshot", "expires", "keys", "roles", "schema", "specVersion", "version"},
        f"{label}.signed",
    )
    if root["_type"] != "root" or root["schema"] != ROOT_SCHEMA or root["specVersion"] != "1.0":
        raise TrustError(f"{label} has unsupported type, schema, or specVersion")
    if root["consistentSnapshot"] is not True:
        raise TrustError(f"{label}.consistentSnapshot must be true")
    _positive_int(root["version"], f"{label}.version")
    _expiry(root["expires"], f"{label}.expires")
    keys = root["keys"]
    if not isinstance(keys, dict) or not 1 <= len(keys) <= MAX_KEYS:
        raise TrustError(f"{label}.keys must contain 1 to {MAX_KEYS} keys")
    for keyid, key in keys.items():
        if not isinstance(keyid, str) or not re.fullmatch(r"[0-9a-f]{64}", keyid):
            raise TrustError(f"{label} has an invalid keyid")
        _validate_key(keyid, key, f"{label}.keys[{keyid}]")
    roles = _exact_keys(root["roles"], {"release", "root"}, f"{label}.roles")
    for role_name, role_value in roles.items():
        role = _exact_keys(role_value, {"keyids", "threshold"}, f"{label}.roles.{role_name}")
        keyids = role["keyids"]
        if (
            not isinstance(keyids, list)
            or not keyids
            or not all(isinstance(item, str) for item in keyids)
            or len(keyids) != len(set(keyids))
            or any(item not in keys for item in keyids)
        ):
            raise TrustError(f"{label}.roles.{role_name}.keyids must be unique known keys")
        threshold = _positive_int(role["threshold"], f"{label}.roles.{role_name}.threshold")
        if threshold > len(keyids):
            raise TrustError(f"{label}.roles.{role_name}.threshold exceeds its key count")
    return root


def _verify_one_signature(
    signed_bytes: bytes,
    signature: str,
    keyid: str,
    key: Mapping[str, Any],
    namespace: str,
    ssh_keygen: Path,
) -> bool:
    principal = f"idc-{keyid}"
    public = key["keyval"]["public"]
    with tempfile.TemporaryDirectory(prefix="idc-trust-sig-") as temporary:
        root = Path(temporary)
        allowed = root / "allowed_signers"
        signature_path = root / "signature"
        allowed.write_text(f"{principal} {public}\n", encoding="utf-8")
        signature_path.write_text(signature, encoding="utf-8")
        try:
            completed = subprocess.run(
                [
                    str(ssh_keygen),
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed),
                    "-I",
                    principal,
                    "-n",
                    namespace,
                    "-s",
                    str(signature_path),
                ],
                input=signed_bytes,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TrustError(f"ssh-keygen verification could not run: {exc}") from exc
    return completed.returncode == 0


def verify_role_threshold(
    envelope: ParsedEnvelope,
    root: Mapping[str, Any],
    role_name: str,
    namespace: str,
    ssh_keygen: Path,
    label: str,
) -> set[str]:
    role = root["roles"][role_name]
    authorized = set(role["keyids"])
    valid: set[str] = set()
    for signature in envelope.value["signatures"]:
        keyid = signature["keyid"]
        if keyid in authorized and _verify_one_signature(
            envelope.signed_bytes,
            signature["sig"],
            keyid,
            root["keys"][keyid],
            namespace,
            ssh_keygen,
        ):
            valid.add(keyid)
    if len(valid) < role["threshold"]:
        raise TrustError(
            f"{label} has {len(valid)} valid {role_name} signature(s); threshold is {role['threshold']}"
        )
    return valid


def load_trusted_root(
    path: Path,
    *,
    repo_root: Path,
    ssh_keygen: Path,
    pinned_digest: str | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any]]:
    if _is_within(path, repo_root):
        raise TrustError("initial trusted root must be outside the candidate repository")
    metadata = path.stat()
    if metadata.st_nlink != 1:
        raise TrustError("initial trusted root must be a single-link regular file")
    if os.name != "nt" and (metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022):
        raise TrustError("initial trusted root must be owner-controlled and not group/world writable")
    envelope = load_envelope(path, "initial trusted root")
    if pinned_digest is not None:
        if not SHA256_RE.fullmatch(pinned_digest):
            raise TrustError("trusted-root digest pin must be sha256:<64 lowercase hex>")
        if envelope.digest != pinned_digest:
            raise TrustError("initial trusted-root digest differs from the external pin")
    root = parse_root(envelope, "initial trusted root")
    verify_role_threshold(envelope, root, "root", ROOT_NAMESPACE, ssh_keygen, "initial trusted root")
    return envelope, root


def _verify_root_chain(
    initial_envelope: ParsedEnvelope,
    initial_root: Mapping[str, Any],
    updates: Sequence[Path],
    *,
    ssh_keygen: Path,
    now: dt.datetime | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any], dict[int, ParsedEnvelope]]:
    if len(updates) > MAX_ROOT_UPDATES:
        raise TrustError(f"root update chain exceeds {MAX_ROOT_UPDATES} versions")
    current_envelope, current_root = initial_envelope, initial_root
    verified_envelopes = {initial_root["version"]: initial_envelope}
    for index, path in enumerate(updates):
        candidate_envelope = load_envelope(path, f"root update[{index}]")
        candidate_root = parse_root(candidate_envelope, f"root update[{index}]")
        old_version = current_root["version"]
        new_version = candidate_root["version"]
        if new_version < old_version:
            raise TrustError(f"root rollback: received version {new_version} after {old_version}")
        if new_version == old_version:
            if candidate_envelope.digest != current_envelope.digest:
                raise TrustError(f"root equivocation at version {new_version}")
            raise TrustError(f"duplicate root version {new_version} is not a rotation")
        if new_version != old_version + 1:
            raise TrustError(f"skipped root rotation: expected {old_version + 1}, got {new_version}")
        verify_role_threshold(
            candidate_envelope,
            current_root,
            "root",
            ROOT_NAMESPACE,
            ssh_keygen,
            f"root update {new_version} under old root",
        )
        verify_role_threshold(
            candidate_envelope,
            candidate_root,
            "root",
            ROOT_NAMESPACE,
            ssh_keygen,
            f"root update {new_version} under new root",
        )
        current_envelope, current_root = candidate_envelope, candidate_root
        verified_envelopes[new_version] = candidate_envelope
    if _expiry(current_root["expires"], "final root expires") <= _now(now):
        raise TrustError(f"final trusted root version {current_root['version']} is expired")
    return current_envelope, current_root, verified_envelopes


def update_root_chain(
    initial_envelope: ParsedEnvelope,
    initial_root: Mapping[str, Any],
    updates: Sequence[Path],
    *,
    ssh_keygen: Path,
    now: dt.datetime | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any]]:
    final_envelope, final_root, _ = _verify_root_chain(
        initial_envelope,
        initial_root,
        updates,
        ssh_keygen=ssh_keygen,
        now=now,
    )
    return final_envelope, final_root


def root_checkpoint(
    envelope: ParsedEnvelope,
    root: Mapping[str, Any],
    *,
    release_sequence: int,
    signed_statement_digest: str,
) -> dict[str, Any]:
    _positive_int(release_sequence, "release checkpoint sequence")
    if not isinstance(signed_statement_digest, str) or not SHA256_RE.fullmatch(
        signed_statement_digest
    ):
        raise TrustError("release checkpoint signed-statement digest is invalid")
    return {
        "releaseSequence": release_sequence,
        "rootSHA256": envelope.digest,
        "schema": ROOT_CHECKPOINT_SCHEMA,
        "signedStatementSHA256": signed_statement_digest,
        "version": root["version"],
    }


def validate_root_checkpoint(
    checkpoint_data: bytes | None,
    final_envelope: ParsedEnvelope,
    final_root: Mapping[str, Any],
    *,
    release_sequence: int,
    signed_statement_digest: str,
    verified_root_envelopes: Mapping[int, ParsedEnvelope] | None = None,
) -> dict[str, Any]:
    next_checkpoint = root_checkpoint(
        final_envelope,
        final_root,
        release_sequence=release_sequence,
        signed_statement_digest=signed_statement_digest,
    )
    if checkpoint_data is None:
        return next_checkpoint
    try:
        value = json.loads(checkpoint_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"root checkpoint is not strict UTF-8 JSON: {exc}") from exc
    if checkpoint_data != canonical_json(value):
        raise TrustError("root checkpoint is not canonical JSON")
    checkpoint = _exact_keys(
        value,
        {
            "releaseSequence",
            "rootSHA256",
            "schema",
            "signedStatementSHA256",
            "version",
        },
        "root checkpoint",
    )
    if checkpoint["schema"] != ROOT_CHECKPOINT_SCHEMA:
        raise TrustError("root checkpoint schema is unsupported")
    version = _positive_int(checkpoint["version"], "root checkpoint version")
    digest = checkpoint["rootSHA256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise TrustError("root checkpoint digest is invalid")
    previous_sequence = _positive_int(
        checkpoint["releaseSequence"], "root checkpoint releaseSequence"
    )
    previous_statement = checkpoint["signedStatementSHA256"]
    if not isinstance(previous_statement, str) or not SHA256_RE.fullmatch(previous_statement):
        raise TrustError("root checkpoint statement digest is invalid")
    if final_root["version"] < version:
        raise TrustError(
            f"root rollback against external checkpoint: final version {final_root['version']} is below {version}"
        )
    checkpoint_envelope = (
        final_envelope
        if final_root["version"] == version
        else (verified_root_envelopes or {}).get(version)
    )
    if checkpoint_envelope is None:
        raise TrustError(f"root checkpoint version {version} is absent from verified root chain")
    if checkpoint_envelope.digest != digest:
        raise TrustError(f"root equivocation against external checkpoint at version {version}")
    if release_sequence < previous_sequence:
        raise TrustError(
            "release-sequence rollback against external checkpoint: "
            f"release sequence {release_sequence} is below {previous_sequence}"
        )
    if (
        release_sequence == previous_sequence
        and signed_statement_digest != previous_statement
    ):
        raise TrustError(
            f"release equivocation against external checkpoint at sequence {release_sequence}"
        )
    return next_checkpoint


def parse_release(envelope: ParsedEnvelope) -> Mapping[str, Any]:
    release = _exact_keys(
        envelope.signed,
        {
            "_type",
            "artifacts",
            "contentSigning",
            "expires",
            "git",
            "release",
            "releaseSequence",
            "rootVersion",
            "schema",
        },
        "release statement.signed",
    )
    if release["_type"] != "release" or release["schema"] != RELEASE_SCHEMA:
        raise TrustError("release statement has unsupported type or schema")
    if not isinstance(release["release"], str) or not RELEASE_RE.fullmatch(release["release"]):
        raise TrustError("release statement release must be semantic-version shaped")
    _positive_int(release["releaseSequence"], "release statement releaseSequence")
    _positive_int(release["rootVersion"], "release statement rootVersion")
    _expiry(release["expires"], "release statement expires")
    content_signing = _exact_keys(
        release["contentSigning"],
        {"allowedSignersSHA256", "fingerprint", "publicKeySHA256"},
        "release statement.contentSigning",
    )
    if not isinstance(content_signing["fingerprint"], str) or not FINGERPRINT_RE.fullmatch(
        content_signing["fingerprint"]
    ):
        raise TrustError("release statement content-signing fingerprint is invalid")
    for field in ("allowedSignersSHA256", "publicKeySHA256"):
        if not isinstance(content_signing[field], str) or not SHA256_RE.fullmatch(
            content_signing[field]
        ):
            raise TrustError(f"release statement contentSigning.{field} is invalid")
    git = _exact_keys(release["git"], {"commit", "tag", "tree"}, "release statement.git")
    if not isinstance(git["tag"], str) or git["tag"] != release["release"]:
        raise TrustError("release statement tag must exactly equal release")
    for field in ("commit", "tree"):
        if not isinstance(git[field], str) or not HEX40_RE.fullmatch(git[field]):
            raise TrustError(f"release statement git.{field} must be 40 lowercase hex")
    artifacts = _exact_keys(
        release["artifacts"],
        {"archive", "freshnessIndex", "installInventory", "manifest", "registry"},
        "release statement.artifacts",
    )
    for name, record_value in artifacts.items():
        record = _exact_keys(record_value, {"sha256", "size"}, f"release statement.artifacts.{name}")
        if not isinstance(record["sha256"], str) or not SHA256_RE.fullmatch(record["sha256"]):
            raise TrustError(f"release statement artifact {name} has an invalid digest")
        _positive_int(record["size"], f"release statement.artifacts.{name}.size")
    return release


def _git_bytes(git: Path, repo: Path, *arguments: str) -> bytes:
    git_directory = repo / ".git"
    try:
        metadata = os.lstat(git_directory)
    except OSError as exc:
        raise TrustError("Git identity check requires an ordinary in-tree .git directory") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise TrustError("Git identity check rejects linked, symlinked, or external Git metadata")
    try:
        with tempfile.TemporaryDirectory(prefix="idc-trust-git-") as temporary:
            isolation = Path(temporary)
            empty_config = isolation / "empty.gitconfig"
            empty_hooks = isolation / "hooks"
            empty_config.write_text("", encoding="utf-8")
            empty_hooks.mkdir()
            environment = {
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(empty_config),
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_SYSTEM": str(empty_config),
                "GIT_NO_LAZY_FETCH": "1",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "GIT_TERMINAL_PROMPT": "0",
                "LANG": "C",
                "LC_ALL": "C",
                "PATH": str(git.parent),
            }
            completed = subprocess.run(
                [
                    str(git),
                    f"--git-dir={git_directory}",
                    f"--work-tree={repo}",
                    "-c",
                    "core.fsmonitor=false",
                    "-c",
                    "core.untrackedCache=false",
                    "-c",
                    "core.filemode=true",
                    "-c",
                    f"core.worktree={repo}",
                    "-c",
                    f"core.hooksPath={empty_hooks}",
                    "-c",
                    "submodule.recurse=false",
                    *arguments,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=10,
                check=False,
                env=environment,
            )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TrustError(f"Git identity check could not run: {exc}") from exc
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise TrustError(f"Git identity check failed: {detail}")
    return completed.stdout


def _git(git: Path, repo: Path, *arguments: str) -> str:
    try:
        return _git_bytes(git, repo, *arguments).decode("utf-8").strip()
    except UnicodeDecodeError as exc:
        raise TrustError("Git identity output is not UTF-8") from exc


def git_tree_entries(
    git: Path, repo: Path, revision: str = "HEAD"
) -> dict[str, tuple[str, str]]:
    raw_tree = _git_bytes(
        git, repo, "ls-tree", "-r", "-z", "--full-tree", revision
    )
    tree: dict[str, tuple[str, str]] = {}
    for raw_entry in raw_tree.split(b"\0"):
        if not raw_entry:
            continue
        header, separator, raw_path = raw_entry.partition(b"\t")
        fields = header.split()
        if not separator or len(fields) != 3:
            raise TrustError("Git tree emitted an invalid entry")
        try:
            mode, kind, oid = (field.decode("ascii") for field in fields)
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrustError("Git tree entry is not UTF-8/ASCII") from exc
        if kind != "blob" or relative in tree:
            raise TrustError(f"release Git tree has unsupported entry: {relative}")
        tree[relative] = (mode, oid)
    return tree


def validate_release_archive(
    raw: bytes,
    manifest_identity: Mapping[str, Any],
    manifest_data: bytes,
    manifest_signature: bytes,
    release: str,
    *,
    git_tree: Mapping[str, tuple[str, str]] | None = None,
) -> None:
    if not raw or len(raw) > MAX_RELEASE_ARCHIVE_BYTES:
        raise TrustError(
            f"release archive must contain 1 to {MAX_RELEASE_ARCHIVE_BYTES} bytes"
        )
    if not isinstance(release, str) or not RELEASE_RE.fullmatch(release):
        raise TrustError("release archive release is invalid")
    prefix = f"idc-skills-{release}/"
    expected: dict[str, tuple[bytes | None, str, int, int]] = {}
    files = manifest_identity.get("repositoryFiles")
    if not isinstance(files, dict):
        raise TrustError("release archive manifest repositoryFiles is invalid")
    for relative in files:
        record = manifest_file_record(manifest_identity, relative)
        expected[relative] = (
            None,
            record["sha256"],
            record["size"],
            record["posixMode"],
        )
    expected["integrity/manifest.json"] = (
        manifest_data,
        sha256_bytes(manifest_data),
        len(manifest_data),
        0o644,
    )
    expected["integrity/manifest.json.sig"] = (
        manifest_signature,
        sha256_bytes(manifest_signature),
        len(manifest_signature),
        0o644,
    )
    if git_tree is not None and set(git_tree) != set(expected):
        raise TrustError(
            "release archive manifest differs from signed Git tree inventory"
        )
    observed: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) != len(expected):
                raise TrustError("release archive file inventory count differs")
            for member in members:
                if not member.isfile():
                    raise TrustError(f"release archive has a non-regular member: {member.name}")
                if not member.name.startswith(prefix):
                    raise TrustError(f"release archive member has the wrong root: {member.name}")
                relative = member.name[len(prefix) :]
                path = Path(relative)
                if (
                    not relative
                    or path.is_absolute()
                    or "\\" in relative
                    or any(part in {"", ".", ".."} for part in path.parts)
                    or relative in observed
                    or relative not in expected
                ):
                    raise TrustError(f"release archive has an unsafe or extra member: {member.name}")
                if (
                    member.uid != 0
                    or member.gid != 0
                    or member.uname not in {"", None}
                    or member.gname not in {"", None}
                    or member.mtime != 0
                    or set(member.pax_headers) - {"path"}
                ):
                    raise TrustError(f"release archive metadata is not deterministic: {member.name}")
                literal, expected_digest, expected_size, expected_mode = expected[relative]
                if member.size != expected_size or member.mode != expected_mode:
                    raise TrustError(f"release archive size or mode differs: {relative}")
                stream = archive.extractfile(member)
                if stream is None:
                    raise TrustError(f"release archive member cannot be read: {relative}")
                data = stream.read(expected_size + 1)
                if len(data) != expected_size or sha256_bytes(data) != expected_digest:
                    raise TrustError(f"release archive bytes differ: {relative}")
                if literal is not None and data != literal:
                    raise TrustError(f"release archive authority bytes differ: {relative}")
                if git_tree is not None:
                    git_mode = "100755" if expected_mode == 0o755 else "100644"
                    if git_tree[relative] != (git_mode, git_blob_oid(data)):
                        raise TrustError(f"release archive differs from Git tree: {relative}")
                observed.add(relative)
    except TrustError:
        raise
    except (tarfile.TarError, OSError, EOFError) as exc:
        raise TrustError(f"release archive is not a valid bounded tar.gz: {exc}") from exc
    if observed != set(expected):
        raise TrustError("release archive omitted signed repository files")


def verify_release_statement(
    statement_path: Path,
    trusted_root: Mapping[str, Any],
    *,
    statement: ParsedEnvelope | None = None,
    ssh_keygen: Path,
    git: Path,
    repo: Path,
    artifacts: Mapping[str, Path],
    now: dt.datetime | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any]]:
    statement = statement or load_envelope(statement_path, "release statement")
    release = parse_release(statement)
    if release["rootVersion"] != trusted_root["version"]:
        raise TrustError("release statement rootVersion differs from the final trusted root")
    if _expiry(release["expires"], "release statement expires") <= _now(now):
        raise TrustError("release statement is expired")
    verify_role_threshold(
        statement,
        trusted_root,
        "release",
        RELEASE_NAMESPACE,
        ssh_keygen,
        "release statement",
    )
    required = {"archive", "freshnessIndex", "installInventory", "manifest", "registry"}
    if set(artifacts) != required:
        raise TrustError(f"artifact arguments differ: missing={sorted(required - set(artifacts))} extra={sorted(set(artifacts) - required)}")
    captured: dict[str, bytes] = {}
    for name in sorted(required):
        path = artifacts[name]
        if name == "archive":
            data = _regular_bytes(path, "archive artifact", MAX_RELEASE_ARCHIVE_BYTES)
            captured[name] = data
            size, digest = len(data), sha256_bytes(data)
        elif name == "manifest":
            data = _regular_bytes(path, "manifest artifact", MAX_MANIFEST_BYTES)
            captured[name] = data
            size, digest = len(data), sha256_bytes(data)
        elif name == "freshnessIndex":
            data = _regular_bytes(path, "freshnessIndex artifact", MAX_RELEASE_INDEX_BYTES)
            captured[name] = data
            size, digest = len(data), sha256_bytes(data)
        elif name == "installInventory":
            data = _regular_bytes(path, "installInventory artifact", MAX_METADATA_BYTES)
            captured[name] = data
            size, digest = len(data), sha256_bytes(data)
        elif name == "registry":
            data = _regular_bytes(path, "registry artifact", MAX_MANIFEST_BYTES)
            captured[name] = data
            size, digest = len(data), sha256_bytes(data)
        else:
            size, digest = _regular_digest(
                path, f"{name} artifact", maximum=2 * 1024 * 1024 * 1024
            )
        expected = release["artifacts"][name]
        if size != expected["size"] or digest != expected["sha256"]:
            raise TrustError(f"{name} artifact differs from the threshold-signed release statement")
    manifest_identity = parse_manifest_identity(captured["manifest"])
    if manifest_identity["release"] != release["release"]:
        raise TrustError("integrity manifest release differs from the release statement")
    parse_install_inventory(captured["installInventory"], captured["manifest"])
    git_record = release["git"]
    release_index = parse_release_index(captured["freshnessIndex"], now=now)
    newest = release_index["releases"][-1]
    if newest["release"] != release["release"]:
        raise TrustError("release index newest release differs from the release statement")
    if newest["manifestSequence"] != manifest_identity["manifestSequence"]:
        raise TrustError("release index newest manifest sequence differs from the manifest")
    if newest["manifestSHA256"] != sha256_bytes(captured["manifest"]):
        raise TrustError("release index newest manifest digest differs from the manifest")
    if newest["gitCommit"] != git_record["commit"]:
        raise TrustError("release index newest Git commit differs from the release statement")
    launcher_record = manifest_file_record(
        manifest_identity, "bootstrap/idc_verify_fresh.py"
    )
    verifier_record = manifest_file_record(
        manifest_identity, "scripts/skill_integrity.py"
    )
    if newest["launcherSHA256"] != launcher_record["sha256"]:
        raise TrustError("release index launcher digest differs from the manifest")
    if newest["verifierSHA256"] != verifier_record["sha256"]:
        raise TrustError("release index verifier digest differs from the manifest")
    registry_record = manifest_file_record(manifest_identity, "skills/registry.json")
    if (
        registry_record["sha256"] != sha256_bytes(captured["registry"])
        or registry_record["size"] != len(captured["registry"])
    ):
        raise TrustError("registry artifact differs from the integrity manifest")
    parse_registry(captured["registry"], manifest_identity)
    public_key_record = manifest_file_record(
        manifest_identity, "keys/idc-skills-signing.pub"
    )
    allowed_signers_record = manifest_file_record(
        manifest_identity, "keys/allowed_signers"
    )
    if release["contentSigning"]["publicKeySHA256"] != public_key_record["sha256"]:
        raise TrustError("content-signing public key differs from the integrity manifest")
    if (
        release["contentSigning"]["allowedSignersSHA256"]
        != allowed_signers_record["sha256"]
    ):
        raise TrustError("content-signing allowed_signers differs from the integrity manifest")
    head = _git(git, repo, "rev-parse", "HEAD")
    tag_type = _git(git, repo, "cat-file", "-t", f"refs/tags/{git_record['tag']}")
    if tag_type != "tag":
        raise TrustError("release tag must be an annotated tag object")
    tag_commit = _git(git, repo, "rev-parse", f"refs/tags/{git_record['tag']}^{{commit}}")
    tag_tree = _git(git, repo, "rev-parse", f"refs/tags/{git_record['tag']}^{{tree}}")
    if head != git_record["commit"] or tag_commit != git_record["commit"]:
        raise TrustError("release tag, repository HEAD, and signed commit do not agree")
    if tag_tree != git_record["tree"]:
        raise TrustError("release tag tree differs from the signed tree")
    for relative, name in (
        ("integrity/manifest.json", "manifest"),
        ("skills/registry.json", "registry"),
    ):
        blob = _git(git, repo, "rev-parse", f"{git_record['commit']}:{relative}")
        if blob != git_blob_oid(captured[name]):
            raise TrustError(f"{name} artifact differs from the signed Git tree blob")
    manifest_signature = _regular_bytes(
        repo / "integrity/manifest.json.sig",
        "committed manifest signature",
        MAX_METADATA_BYTES,
    )
    signature_blob = _git(
        git,
        repo,
        "rev-parse",
        f"{git_record['commit']}:integrity/manifest.json.sig",
    )
    if signature_blob != git_blob_oid(manifest_signature):
        raise TrustError("manifest signature differs from the signed Git tree blob")
    validate_release_archive(
        captured["archive"],
        manifest_identity,
        captured["manifest"],
        manifest_signature,
        release["release"],
        git_tree=git_tree_entries(git, repo, git_record["commit"]),
    )
    return statement, release


def verify_external_release(
    *,
    repo: Path,
    trusted_root_path: Path,
    trusted_root_digest: str | None,
    root_updates: Sequence[Path],
    statement_path: Path,
    artifacts: Mapping[str, Path],
    ssh_keygen: Path,
    ssh_keygen_digest: str,
    git: Path,
    git_digest: str,
    root_checkpoint_data: bytes | None = None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    ssh_keygen = _validate_tool(ssh_keygen, ssh_keygen_digest, "ssh-keygen", repo)
    git = _validate_tool(git, git_digest, "Git", repo)
    initial_envelope, initial_root = load_trusted_root(
        trusted_root_path,
        repo_root=repo,
        ssh_keygen=ssh_keygen,
        pinned_digest=trusted_root_digest,
    )
    final_envelope, final_root, verified_root_envelopes = _verify_root_chain(
        initial_envelope,
        initial_root,
        root_updates,
        ssh_keygen=ssh_keygen,
        now=now,
    )
    statement_preview = load_envelope(statement_path, "release statement")
    release_preview = parse_release(statement_preview)
    next_root_checkpoint = validate_root_checkpoint(
        root_checkpoint_data,
        final_envelope,
        final_root,
        release_sequence=release_preview["releaseSequence"],
        signed_statement_digest=sha256_bytes(statement_preview.signed_bytes),
        verified_root_envelopes=verified_root_envelopes,
    )
    statement, release = verify_release_statement(
        statement_path,
        final_root,
        statement=statement_preview,
        ssh_keygen=ssh_keygen,
        git=git,
        repo=repo,
        artifacts=artifacts,
        now=now,
    )
    return {
        "schema": "idc-skills-external-verification/v1",
        "externalTrustVerified": True,
        "eligibleForContentVerification": True,
        "readyToInstall": False,
        "initialRoot": {"version": initial_root["version"], "sha256": initial_envelope.digest},
        "finalRoot": {"version": final_root["version"], "sha256": final_envelope.digest},
        "rootCheckpoint": next_root_checkpoint,
        "release": release["release"],
        "releaseSequence": release["releaseSequence"],
        "signedStatementSHA256": sha256_bytes(statement.signed_bytes),
        "statementSHA256": statement.digest,
        "git": release["git"],
        "artifacts": release["artifacts"],
        "contentSigning": release["contentSigning"],
    }
