#!/usr/bin/env python3
"""Externally deployed freshness authority for IDC Skills releases.

The copy tracked in the repository is source and test material only. A release
operator installs this file outside every checkout, pins an external canonical
configuration, and invokes that independent copy. The launcher authenticates a
separately signed, expiring release index before it executes a captured snapshot
of the tree's content verifier. Only this launcher emits ``readyToRun=true``.

The boundary is intentionally narrow: it detects repository rollback and
point-in-time byte drift. It is not protection from an attacker who can replace
the external launcher, its protected configuration, its checkpoint, or the
OS-pinned Python runtime named by that configuration.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Sequence


CONFIG_SCHEMA = "idc-skills-freshness-config/v1"
INDEX_SCHEMA = "idc-skills-release-index/v1"
CHECKPOINT_SCHEMA = "idc-skills-freshness-checkpoint/v1"
REPORT_SCHEMA = "idc-skills-freshness-report/v1"
MANIFEST_SCHEMA = "idc-skill-integrity/v3"
INDEX_NAMESPACE = "idc-skills-release-index-v1"
MANIFEST_NAMESPACE = "file"
SIGN_IDENTITY = "idc-skills"
EXPECTED_SIGNING_FINGERPRINT = "SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA"
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_CONFIG_BYTES = 128 * 1024
MAX_CHECKPOINT_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_SIGNATURE_BYTES = 1024 * 1024
MAX_ANCHOR_BYTES = 64 * 1024
MAX_VERIFIER_BYTES = 4 * 1024 * 1024
MAX_REPOSITORY_FILE_BYTES = 64 * 1024 * 1024
MAX_EXECUTABLE_BYTES = 256 * 1024 * 1024
MAX_SEQUENCE = (1 << 53) - 1
MAX_CLOCK_SKEW_SECONDS = 300
MAX_INDEX_LIFETIME_SECONDS = 31 * 24 * 60 * 60
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?\Z")


class FreshnessError(RuntimeError):
    """A deterministic failure at the external freshness boundary."""


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode(
        "utf-8"
    )


def _reject_constant(value: str) -> None:
    raise FreshnessError(f"non-finite JSON number is forbidden: {value}")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise FreshnessError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def load_canonical_json(data: bytes, label: str, maximum: int) -> dict[str, Any]:
    if len(data) > maximum:
        raise FreshnessError(f"{label} exceeds {maximum} bytes")
    try:
        value = json.loads(
            data.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except FreshnessError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FreshnessError(f"invalid {label}: {exc}") from exc
    if not isinstance(value, dict):
        raise FreshnessError(f"{label} must be a JSON object")
    if data != canonical_bytes(value):
        raise FreshnessError(f"{label} is not canonical JSON")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        unknown = sorted(actual - expected)
        raise FreshnessError(f"{label} keys differ: missing={missing} unknown={unknown}")


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or not 1 <= value <= MAX_SEQUENCE:
        raise FreshnessError(f"{label} must be an integer between 1 and {MAX_SEQUENCE}")
    return value


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or SHA256_RE.fullmatch(value) is None:
        raise FreshnessError(f"{label} must be a lowercase sha256 digest")
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _path_is_within(candidate: Path, root: Path) -> bool:
    """Use lexical and filesystem identity checks, including future paths."""

    root = root.resolve(strict=True)
    resolved = candidate.resolve(strict=False)
    if _is_relative_to(resolved, root):
        return True
    cursor = candidate.absolute()
    while not cursor.exists() and not cursor.is_symlink():
        parent = cursor.parent
        if parent == cursor:
            break
        cursor = parent
    while True:
        try:
            if os.path.samefile(cursor, root):
                return True
        except OSError:
            pass
        parent = cursor.parent
        if parent == cursor:
            return False
        cursor = parent


def _read_regular_snapshot(
    path: Path,
    label: str,
    maximum: int,
    *,
    require_single_link: bool = False,
) -> bytes:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise FreshnessError(f"cannot inspect {label}: {path}: {exc}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise FreshnessError(f"refusing symlinked {label}: {path}")
    if not stat.S_ISREG(before.st_mode):
        raise FreshnessError(f"{label} must be a regular file: {path}")
    if require_single_link and before.st_nlink != 1:
        raise FreshnessError(f"{label} must not be hard-linked: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise FreshnessError(f"cannot open {label}: {path}: {exc}") from exc
    try:
        after = os.fstat(descriptor)
        if not stat.S_ISREG(after.st_mode):
            raise FreshnessError(f"{label} must be a regular file: {path}")
        if require_single_link and after.st_nlink != 1:
            raise FreshnessError(f"{label} must not be hard-linked: {path}")
        if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
            raise FreshnessError(f"{label} path changed before capture: {path}")
        data = bytearray()
        while len(data) <= maximum:
            chunk = os.read(descriptor, min(128 * 1024, maximum + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
    finally:
        os.close(descriptor)
    if len(data) > maximum:
        raise FreshnessError(f"{label} exceeds {maximum} bytes: {path}")
    return bytes(data)


def _trusted_executable(name: str) -> str:
    candidate = shutil.which(name, path=os.defpath)
    if candidate is None:
        raise FreshnessError(f"trusted system executable is unavailable: {name}")
    resolved = Path(candidate).resolve(strict=True)
    if not resolved.is_file():
        raise FreshnessError(f"trusted executable is not a regular file: {resolved}")
    return str(resolved)


def _verification_environment(
    executable_directories: Sequence[Path] = (),
) -> dict[str, str]:
    """Return a minimal environment with no caller-controlled code-loading knobs."""

    search_path = os.pathsep.join(str(path) for path in executable_directories)
    environment = {"PATH": search_path, "LANG": "C", "LC_ALL": "C", "TZ": "UTC"}
    for key in ("SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT"):
        if os.name == "nt" and key in os.environ:
            environment[key] = os.environ[key]
    return environment


def _fingerprint_public_key(key_data: str, ssh_keygen: str | None = None) -> str:
    executable = ssh_keygen or _trusted_executable("ssh-keygen")
    try:
        with tempfile.TemporaryDirectory(prefix="idc-fingerprint-") as temporary:
            public_key = Path(temporary) / "signing.pub"
            public_key.write_text(key_data, encoding="utf-8", newline="")
            os.chmod(public_key, 0o600)
            process = subprocess.run(
                [executable, "-lf", str(public_key)],
                text=True,
                capture_output=True,
                check=False,
                env=_verification_environment(
                    (Path(ssh_keygen).parent,) if ssh_keygen is not None else ()
                ),
            )
    except FileNotFoundError as exc:
        raise FreshnessError("ssh-keygen is required") from exc
    if process.returncode != 0:
        raise FreshnessError(
            f"ssh-keygen rejected public key: {(process.stderr or process.stdout).strip()}"
        )
    fields = process.stdout.split()
    if len(fields) < 2:
        raise FreshnessError("ssh-keygen returned no public-key fingerprint")
    return fields[1]


def validate_anchor(
    public_key_data: bytes,
    allowed_signers_data: bytes,
    expected_fingerprint: str,
    ssh_keygen: str | None = None,
) -> None:
    try:
        public_fields = public_key_data.decode("utf-8").strip().split()
        allowed_text = allowed_signers_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FreshnessError("signing anchor must be UTF-8") from exc
    if len(public_fields) < 2:
        raise FreshnessError("invalid public signing key")
    public_material = " ".join(public_fields[:2]) + "\n"
    fingerprint = _fingerprint_public_key(public_material, ssh_keygen)
    if fingerprint != expected_fingerprint:
        raise FreshnessError(
            f"public-key fingerprint mismatch: expected {expected_fingerprint}, got {fingerprint}"
        )
    lines = [
        line.strip()
        for line in allowed_text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) != 1:
        raise FreshnessError("allowed_signers must contain exactly one signer")
    fields = lines[0].split()
    if len(fields) < 3 or SIGN_IDENTITY not in fields[0].split(","):
        raise FreshnessError(f"allowed_signers must bind {SIGN_IDENTITY!r}")
    allowed_material = " ".join(fields[1:3]) + "\n"
    if allowed_material != public_material:
        raise FreshnessError("allowed_signers key differs from the pinned public key")


def verify_signature(
    payload: bytes,
    signature: bytes,
    allowed_signers: bytes,
    namespace: str,
    ssh_keygen: str | None = None,
) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="idc-fresh-signature-") as temporary:
            root = Path(temporary)
            os.chmod(root, 0o700)
            allowed_path = root / "allowed_signers"
            signature_path = root / "payload.sig"
            allowed_path.write_bytes(allowed_signers)
            signature_path.write_bytes(signature)
            os.chmod(allowed_path, 0o600)
            os.chmod(signature_path, 0o600)
            process = subprocess.run(
                [
                    ssh_keygen or _trusted_executable("ssh-keygen"),
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_path),
                    "-I",
                    SIGN_IDENTITY,
                    "-n",
                    namespace,
                    "-s",
                    str(signature_path),
                ],
                input=payload,
                capture_output=True,
                check=False,
                env=_verification_environment(
                    (Path(ssh_keygen).parent,) if ssh_keygen is not None else ()
                ),
            )
    except FileNotFoundError as exc:
        raise FreshnessError("ssh-keygen is required") from exc
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).decode("utf-8", errors="replace").strip()
        raise FreshnessError(f"signature invalid for namespace {namespace!r}: {detail}")


def _parse_utc(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise FreshnessError(f"{label} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise FreshnessError(f"invalid {label}: {value!r}") from exc
    if parsed.tzinfo != dt.timezone.utc or parsed.microsecond != 0:
        raise FreshnessError(f"{label} must use whole-second UTC precision")
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise FreshnessError(f"{label} is not canonical RFC3339 UTC")
    return parsed


ENTRY_KEYS = {
    "release",
    "manifestSequence",
    "manifestSHA256",
    "verifierSHA256",
    "launcherSHA256",
    "gitCommit",
}


def _validate_entry(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FreshnessError(f"{label} must be an object")
    _exact_keys(value, ENTRY_KEYS, label)
    release = value["release"]
    if not isinstance(release, str) or RELEASE_RE.fullmatch(release) is None:
        raise FreshnessError(f"{label}.release must be a release identifier")
    sequence = _positive_int(value["manifestSequence"], f"{label}.manifestSequence")
    manifest_digest = _digest(value["manifestSHA256"], f"{label}.manifestSHA256")
    verifier_digest = _digest(value["verifierSHA256"], f"{label}.verifierSHA256")
    launcher_digest = _digest(value["launcherSHA256"], f"{label}.launcherSHA256")
    commit = value["gitCommit"]
    if not isinstance(commit, str) or COMMIT_RE.fullmatch(commit) is None:
        raise FreshnessError(f"{label}.gitCommit must be 40 lowercase hexadecimal characters")
    return {
        "release": release,
        "manifestSequence": sequence,
        "manifestSHA256": manifest_digest,
        "verifierSHA256": verifier_digest,
        "launcherSHA256": launcher_digest,
        "gitCommit": commit,
    }


def parse_index(data: bytes, *, now: dt.datetime | None = None) -> dict[str, Any]:
    value = load_canonical_json(data, "release index", MAX_INDEX_BYTES)
    _exact_keys(
        value,
        {"schema", "indexSequence", "generatedAt", "validUntil", "releases"},
        "release index",
    )
    if value["schema"] != INDEX_SCHEMA:
        raise FreshnessError(f"release index schema must be {INDEX_SCHEMA!r}")
    index_sequence = _positive_int(value["indexSequence"], "indexSequence")
    generated = _parse_utc(value["generatedAt"], "generatedAt")
    expires = _parse_utc(value["validUntil"], "validUntil")
    current = now or dt.datetime.now(dt.timezone.utc)
    if current.tzinfo is None:
        raise FreshnessError("current time must be timezone-aware")
    current = current.astimezone(dt.timezone.utc)
    if generated > current + dt.timedelta(seconds=MAX_CLOCK_SKEW_SECONDS):
        raise FreshnessError("release index was generated implausibly far in the future")
    if expires <= current:
        raise FreshnessError("release index is expired")
    if expires <= generated:
        raise FreshnessError("validUntil must be later than generatedAt")
    if (expires - generated).total_seconds() > MAX_INDEX_LIFETIME_SECONDS:
        raise FreshnessError("release index validity window exceeds 31 days")
    raw_releases = value["releases"]
    if not isinstance(raw_releases, list) or not raw_releases:
        raise FreshnessError("release index releases must be a non-empty array")
    releases = [
        _validate_entry(entry, f"releases[{index}]")
        for index, entry in enumerate(raw_releases)
    ]
    sequences = [entry["manifestSequence"] for entry in releases]
    names = [entry["release"] for entry in releases]
    if sequences != sorted(sequences) or len(sequences) != len(set(sequences)):
        raise FreshnessError("release entries must have strictly increasing unique sequences")
    if len(names) != len(set(names)):
        raise FreshnessError("release entries must have unique release names")
    return {
        "schema": INDEX_SCHEMA,
        "indexSequence": index_sequence,
        "generatedAt": value["generatedAt"],
        "validUntil": value["validUntil"],
        "releases": releases,
    }


def parse_manifest(data: bytes) -> dict[str, Any]:
    value = load_canonical_json(data, "integrity manifest", MAX_MANIFEST_BYTES)
    if value.get("schema") != MANIFEST_SCHEMA:
        raise FreshnessError(f"integrity manifest schema must be {MANIFEST_SCHEMA!r}")
    release = value.get("release")
    if not isinstance(release, str) or RELEASE_RE.fullmatch(release) is None:
        raise FreshnessError("integrity manifest release is invalid")
    sequence = _positive_int(value.get("manifestSequence"), "manifestSequence")
    if value.get("profile") != "release":
        raise FreshnessError("only a release-profile manifest can become ready to run")
    if value.get("skillCount") != 50:
        raise FreshnessError("release manifest must bind exactly 50 skills")
    if not isinstance(value.get("repositoryFiles"), dict) or not value["repositoryFiles"]:
        raise FreshnessError("release manifest must bind the repository execution closure")
    return value


def _manifest_file_record(value: Any, label: str) -> tuple[str, int, int]:
    if not isinstance(value, dict):
        raise FreshnessError(f"{label} must be an object")
    _exact_keys(value, {"sha256", "size", "posixMode"}, label)
    digest = _digest(value["sha256"], f"{label}.sha256")
    size = value["size"]
    if type(size) is not int or not 0 <= size <= MAX_REPOSITORY_FILE_BYTES:
        raise FreshnessError(
            f"{label}.size must be an integer between 0 and {MAX_REPOSITORY_FILE_BYTES}"
        )
    posix_mode = value["posixMode"]
    if type(posix_mode) is not int or not 0 <= posix_mode <= 0o777:
        raise FreshnessError(f"{label}.posixMode must be an integer between 0 and 511")
    return digest, size, posix_mode


def _require_captured_repository_file(
    manifest: Mapping[str, Any], relative: str, data: bytes, label: str
) -> None:
    """Bind an already captured authority input to the signed source record."""

    files = manifest["repositoryFiles"]
    if relative not in files:
        raise FreshnessError(f"signed repository closure is missing {relative!r}")
    expected_digest, expected_size, _expected_mode = _manifest_file_record(
        files[relative], f"repositoryFiles[{relative!r}]"
    )
    if len(data) != expected_size or sha256_bytes(data) != expected_digest:
        raise FreshnessError(
            f"captured {label} differs from signed repository source {relative}"
        )


@contextlib.contextmanager
def _staged_repository(
    repo_root: Path,
    manifest: Mapping[str, Any],
    manifest_data: bytes,
    manifest_signature: bytes,
) -> Iterator[Path]:
    files = manifest["repositoryFiles"]
    with tempfile.TemporaryDirectory(prefix="idc-fresh-release-") as temporary:
        staged = Path(temporary) / "repo"
        staged.mkdir(mode=0o700)
        for relative, record in sorted(files.items()):
            if not isinstance(relative, str):
                raise FreshnessError("repositoryFiles paths must be strings")
            relative_path = Path(relative)
            if (
                relative_path.is_absolute()
                or not relative_path.parts
                or any(part in {"", ".", ".."} for part in relative_path.parts)
                or relative in {
                    ".git",
                    "integrity/manifest.json",
                    "integrity/manifest.json.sig",
                }
            ):
                raise FreshnessError(f"unsafe repositoryFiles path: {relative!r}")
            expected_digest, expected_size, expected_mode = _manifest_file_record(
                record, f"repositoryFiles[{relative!r}]"
            )
            source = repo_root / relative_path
            try:
                resolved = source.resolve(strict=True)
            except OSError as exc:
                raise FreshnessError(f"missing signed repository file: {relative}") from exc
            if not _path_is_within(source, repo_root) or resolved != source.absolute():
                raise FreshnessError(f"signed repository path crosses a symlink: {relative}")
            data = _read_regular_snapshot(
                source,
                f"signed repository file {relative}",
                MAX_REPOSITORY_FILE_BYTES,
            )
            if len(data) != expected_size or sha256_bytes(data) != expected_digest:
                raise FreshnessError(f"signed repository file drifted: {relative}")
            destination = staged / relative_path
            destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            destination.write_bytes(data)
            os.chmod(destination, expected_mode)
        snapshot_manifest = staged / "integrity" / "manifest.json"
        snapshot_manifest.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        snapshot_manifest.write_bytes(manifest_data)
        Path(str(snapshot_manifest) + ".sig").write_bytes(manifest_signature)
        os.chmod(snapshot_manifest, 0o600)
        os.chmod(Path(str(snapshot_manifest) + ".sig"), 0o600)
        yield staged


def _validate_executable_record(value: Any, label: str, repo_root: Path) -> str:
    if not isinstance(value, dict):
        raise FreshnessError(f"{label} must be an executable record")
    _exact_keys(value, {"path", "sha256"}, label)
    if not isinstance(value["path"], str):
        raise FreshnessError(f"{label}.path must be an absolute path string")
    expected_digest = _digest(value["sha256"], f"{label}.sha256")
    path = Path(value["path"])
    if not path.is_absolute():
        raise FreshnessError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise FreshnessError(f"cannot inspect {label}: {path}: {exc}") from exc
    if _path_is_within(resolved, repo_root) or not stat.S_ISREG(metadata.st_mode):
        raise FreshnessError(f"{label} must be a regular executable outside the repository")
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise FreshnessError(f"{label} must be owner-controlled and not group/world writable")
    if not os.access(resolved, os.X_OK):
        raise FreshnessError(f"{label} is not executable")
    data = _read_regular_snapshot(resolved, label, MAX_EXECUTABLE_BYTES)
    if sha256_bytes(data) != expected_digest:
        raise FreshnessError(f"{label} digest differs from protected configuration")
    return str(resolved)


def _validate_executable_directory(value: Any, label: str, repo_root: Path) -> str:
    if not isinstance(value, str):
        raise FreshnessError(f"{label} must be an absolute directory path")
    path = Path(value)
    if not path.is_absolute():
        raise FreshnessError(f"{label} must be absolute")
    try:
        resolved = path.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise FreshnessError(f"cannot inspect {label}: {path}: {exc}") from exc
    if _path_is_within(resolved, repo_root) or not stat.S_ISDIR(metadata.st_mode):
        raise FreshnessError(f"{label} must be a directory outside the repository")
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise FreshnessError(f"{label} must be owner-controlled and not group/world writable")
    return str(resolved)


def parse_config(data: bytes, *, repo_root: Path, config_path: Path) -> dict[str, Any]:
    value = load_canonical_json(data, "freshness configuration", MAX_CONFIG_BYTES)
    _exact_keys(
        value,
        {
            "schema",
            "source",
            "checkpointPath",
            "bootstrapIndexSHA256",
            "minimumIndexSequence",
            "minimumManifestSequence",
            "requireGitCommit",
            "executables",
            "consumerPath",
            "consumerHome",
        },
        "freshness configuration",
    )
    if value["schema"] != CONFIG_SCHEMA:
        raise FreshnessError(f"freshness configuration schema must be {CONFIG_SCHEMA!r}")
    if value["requireGitCommit"] is not True:
        raise FreshnessError("requireGitCommit must be true for release authority")
    executables = value["executables"]
    if not isinstance(executables, dict):
        raise FreshnessError("executables must be an object")
    _exact_keys(executables, {"python", "git", "sshKeygen"}, "executables")
    value["executables"] = {
        "python": _validate_executable_record(
            executables["python"], "executables.python", repo_root
        ),
        "git": _validate_executable_record(
            executables["git"], "executables.git", repo_root
        ),
        "sshKeygen": _validate_executable_record(
            executables["sshKeygen"], "executables.sshKeygen", repo_root
        ),
    }
    try:
        if not os.path.samefile(sys.executable, value["executables"]["python"]):
            raise FreshnessError(
                "launcher is not running under the protected configured Python runtime"
            )
    except OSError as exc:
        raise FreshnessError("configured Python runtime identity could not be established") from exc
    consumer_path = value["consumerPath"]
    if (
        not isinstance(consumer_path, list)
        or not consumer_path
        or len(consumer_path) > 32
    ):
        raise FreshnessError("consumerPath must contain 1 to 32 protected directories")
    normalized_path = [
        _validate_executable_directory(item, f"consumerPath[{index}]", repo_root)
        for index, item in enumerate(consumer_path)
    ]
    if len(normalized_path) != len(set(normalized_path)):
        raise FreshnessError("consumerPath must not contain duplicate directories")
    value["consumerPath"] = normalized_path
    value["consumerHome"] = _validate_executable_directory(
        value["consumerHome"], "consumerHome", repo_root
    )
    source = value["source"]
    if not isinstance(source, dict) or source.get("type") not in {"file", "https"}:
        raise FreshnessError("source must be a file or https source object")
    if source["type"] == "file":
        _exact_keys(source, {"type", "indexPath", "signaturePath"}, "file source")
        if not isinstance(source["indexPath"], str) or not isinstance(
            source["signaturePath"], str
        ):
            raise FreshnessError("file source paths must be strings")
        index_path = Path(source["indexPath"])
        signature_path = Path(source["signaturePath"])
        for path, label in ((index_path, "indexPath"), (signature_path, "signaturePath")):
            if not path.is_absolute():
                raise FreshnessError(f"{label} must be absolute")
            if _path_is_within(path, repo_root):
                raise FreshnessError(f"{label} must be outside the repository")
    else:
        _exact_keys(
            source,
            {"type", "indexURL", "signatureURL", "allowedHosts", "maxRedirects"},
            "https source",
        )
        hosts = source["allowedHosts"]
        if (
            not isinstance(hosts, list)
            or not hosts
            or not all(isinstance(host, str) and host and host == host.lower() for host in hosts)
            or len(hosts) != len(set(hosts))
        ):
            raise FreshnessError("allowedHosts must be a non-empty unique lowercase string array")
        redirects = source["maxRedirects"]
        if type(redirects) is not int or not 0 <= redirects <= 3:
            raise FreshnessError("maxRedirects must be an integer between 0 and 3")
        for field in ("indexURL", "signatureURL"):
            if not isinstance(source[field], str):
                raise FreshnessError(f"{field} must be a string")
            parsed = urllib.parse.urlsplit(source[field])
            if (
                parsed.scheme != "https"
                or parsed.hostname not in hosts
                or parsed.username is not None
                or parsed.password is not None
                or parsed.fragment
                or (parsed.port is not None and parsed.port != 443)
            ):
                raise FreshnessError(f"{field} must be HTTPS on an allowed host")
    if not isinstance(value["checkpointPath"], str):
        raise FreshnessError("checkpointPath must be a string")
    checkpoint = Path(value["checkpointPath"])
    if not checkpoint.is_absolute():
        raise FreshnessError("checkpointPath must be absolute")
    if _path_is_within(checkpoint, repo_root):
        raise FreshnessError("checkpointPath must be outside the repository")
    if _path_is_within(config_path, repo_root):
        raise FreshnessError("freshness configuration must be outside the repository")
    _digest(value["bootstrapIndexSHA256"], "bootstrapIndexSHA256")
    _positive_int(value["minimumIndexSequence"], "minimumIndexSequence")
    _positive_int(value["minimumManifestSequence"], "minimumManifestSequence")
    return value


class _PinnedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allowed_hosts: set[str], maximum: int) -> None:
        super().__init__()
        self.allowed_hosts = allowed_hosts
        self.maximum = maximum
        self.count = 0

    def redirect_request(  # type: ignore[override]
        self,
        request: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Mapping[str, str],
        newurl: str,
    ) -> urllib.request.Request | None:
        self.count += 1
        parsed = urllib.parse.urlsplit(newurl)
        if (
            self.count > self.maximum
            or parsed.scheme != "https"
            or parsed.hostname not in self.allowed_hosts
            or parsed.username is not None
            or parsed.password is not None
            or (parsed.port is not None and parsed.port != 443)
        ):
            raise FreshnessError("release-index redirect left the configured HTTPS origin policy")
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def _fetch_https(url: str, allowed_hosts: set[str], redirects: int, maximum: int) -> bytes:
    handler = _PinnedRedirectHandler(allowed_hosts, redirects)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), handler)
    request = urllib.request.Request(url, headers={"User-Agent": "idc-verify-fresh/1"})
    try:
        with opener.open(request, timeout=20) as response:
            final = urllib.parse.urlsplit(response.geturl())
            if (
                final.scheme != "https"
                or final.hostname not in allowed_hosts
                or final.username is not None
                or final.password is not None
                or (final.port is not None and final.port != 443)
            ):
                raise FreshnessError("release-index response left the configured HTTPS origin policy")
            data = response.read(maximum + 1)
    except FreshnessError:
        raise
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise FreshnessError(f"release-index fetch failed: {exc}") from exc
    if len(data) > maximum:
        raise FreshnessError(f"release-index response exceeds {maximum} bytes")
    return data


def capture_index_source(config: Mapping[str, Any]) -> tuple[bytes, bytes]:
    source = config["source"]
    if source["type"] == "file":
        return (
            _read_regular_snapshot(
                Path(source["indexPath"]),
                "release index",
                MAX_INDEX_BYTES,
                require_single_link=True,
            ),
            _read_regular_snapshot(
                Path(source["signaturePath"]),
                "release index signature",
                MAX_SIGNATURE_BYTES,
                require_single_link=True,
            ),
        )
    hosts = set(source["allowedHosts"])
    redirects = source["maxRedirects"]
    return (
        _fetch_https(source["indexURL"], hosts, redirects, MAX_INDEX_BYTES),
        _fetch_https(source["signatureURL"], hosts, redirects, MAX_SIGNATURE_BYTES),
    )


def _checkpoint_value(index: Mapping[str, Any], digest: str) -> dict[str, Any]:
    return {
        "schema": CHECKPOINT_SCHEMA,
        "indexSequence": index["indexSequence"],
        "indexSHA256": digest,
        "releases": index["releases"],
    }


def _parse_checkpoint(data: bytes) -> dict[str, Any]:
    value = load_canonical_json(data, "freshness checkpoint", MAX_CHECKPOINT_BYTES)
    _exact_keys(
        value,
        {"schema", "indexSequence", "indexSHA256", "releases"},
        "freshness checkpoint",
    )
    if value["schema"] != CHECKPOINT_SCHEMA:
        raise FreshnessError(f"checkpoint schema must be {CHECKPOINT_SCHEMA!r}")
    sequence = _positive_int(value["indexSequence"], "checkpoint indexSequence")
    digest = _digest(value["indexSHA256"], "checkpoint indexSHA256")
    releases = value["releases"]
    if not isinstance(releases, list) or not releases:
        raise FreshnessError("checkpoint releases must be non-empty")
    parsed = [_validate_entry(entry, f"checkpoint releases[{i}]") for i, entry in enumerate(releases)]
    return {
        "schema": CHECKPOINT_SCHEMA,
        "indexSequence": sequence,
        "indexSHA256": digest,
        "releases": parsed,
    }


def validate_checkpoint(
    checkpoint_data: bytes | None,
    index: Mapping[str, Any],
    index_digest: str,
    bootstrap_digest: str,
) -> None:
    if checkpoint_data is None:
        if index_digest != bootstrap_digest:
            raise FreshnessError("first-run index does not match the externally pinned bootstrap digest")
        return
    previous = _parse_checkpoint(checkpoint_data)
    old_sequence = previous["indexSequence"]
    new_sequence = index["indexSequence"]
    if new_sequence < old_sequence:
        raise FreshnessError("release index replayed a lower indexSequence")
    if new_sequence == old_sequence and index_digest != previous["indexSHA256"]:
        raise FreshnessError("release index equivocation at the same indexSequence")
    current_by_sequence = {
        entry["manifestSequence"]: entry for entry in index["releases"]
    }
    for old_entry in previous["releases"]:
        if current_by_sequence.get(old_entry["manifestSequence"]) != old_entry:
            raise FreshnessError("release index rewrote or removed accepted history")


@contextlib.contextmanager
def _checkpoint_lock(path: Path) -> Iterator[None]:
    directory = path.parent
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    if directory.is_symlink() or not directory.is_dir():
        raise FreshnessError(f"checkpoint parent must be a real directory: {directory}")
    if os.name != "nt" and directory.stat().st_mode & 0o022:
        raise FreshnessError(f"checkpoint parent must not be group/world writable: {directory}")
    if os.name != "nt" and directory.stat().st_uid not in {0, os.geteuid()}:
        raise FreshnessError(f"checkpoint parent has an unexpected owner: {directory}")
    lock_path = path.with_name(path.name + ".lock")
    if lock_path.is_symlink():
        raise FreshnessError("checkpoint lock may not be a symlink")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(lock_path, flags, 0o600)
    try:
        lock_stat = os.fstat(descriptor)
        if not stat.S_ISREG(lock_stat.st_mode) or lock_stat.st_nlink != 1:
            raise FreshnessError("checkpoint lock must be a single-link regular file")
        if lock_stat.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(descriptor, msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)


def _load_checkpoint(path: Path) -> bytes | None:
    if not path.exists():
        if path.is_symlink():
            raise FreshnessError("checkpoint may not be a dangling symlink")
        return None
    return _read_regular_snapshot(
        path,
        "freshness checkpoint",
        MAX_CHECKPOINT_BYTES,
        require_single_link=True,
    )


def _write_checkpoint(path: Path, value: Mapping[str, Any]) -> None:
    data = canonical_bytes(value)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink():
            raise FreshnessError("refusing symlinked checkpoint")
        os.replace(temporary, path)
        if hasattr(os, "O_DIRECTORY"):
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
    finally:
        if temporary.exists():
            temporary.unlink()


def _git_commit(
    repo_root: Path,
    git_executable: str,
    manifest: Mapping[str, Any],
    manifest_data: bytes,
    manifest_signature: bytes,
) -> str:
    git_directory = repo_root / ".git"
    try:
        git_metadata = os.lstat(git_directory)
    except OSError as exc:
        raise FreshnessError("release authority requires an ordinary in-tree .git directory") from exc
    if stat.S_ISLNK(git_metadata.st_mode) or not stat.S_ISDIR(git_metadata.st_mode):
        raise FreshnessError("release authority rejects linked, symlinked, or external Git metadata")
    with tempfile.TemporaryDirectory(prefix="idc-fresh-git-") as temporary:
        trust_root = Path(temporary)
        empty_config = trust_root / "empty.gitconfig"
        empty_hooks = trust_root / "hooks"
        empty_config.write_text("", encoding="utf-8")
        empty_hooks.mkdir()
        environment = _verification_environment((Path(git_executable).parent,))
        environment.update(
            {
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": str(empty_config),
                "GIT_CONFIG_SYSTEM": str(empty_config),
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_NO_LAZY_FETCH": "1",
            }
        )
        hardened = [
            git_executable,
            f"--git-dir={git_directory}",
            f"--work-tree={repo_root}",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "core.untrackedCache=false",
            "-c",
            "core.filemode=true",
            "-c",
            f"core.worktree={repo_root}",
            "-c",
            f"core.hooksPath={empty_hooks}",
            "-c",
            "submodule.recurse=false",
        ]
        try:
            process = subprocess.run(
                [*hardened, "rev-parse", "--verify", "HEAD^{commit}"],
                text=True,
                capture_output=True,
                check=False,
                env=environment,
            )
        except FileNotFoundError as exc:
            raise FreshnessError("git is required when requireGitCommit is true") from exc
        commit = process.stdout.strip()
        if process.returncode != 0 or COMMIT_RE.fullmatch(commit) is None:
            raise FreshnessError("repository has no verifiable Git HEAD")
        top_level = subprocess.run(
            [*hardened, "rev-parse", "--show-toplevel"],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
        )
        try:
            same_worktree = top_level.returncode == 0 and os.path.samefile(
                top_level.stdout.strip(), repo_root
            )
        except OSError:
            same_worktree = False
        if not same_worktree:
            raise FreshnessError("Git worktree identity differs from the verified repository")
        tree = subprocess.run(
            [*hardened, "ls-tree", "-r", "-z", "--full-tree", commit],
            capture_output=True,
            check=False,
            env=environment,
        )
    if tree.returncode != 0:
        raise FreshnessError("repository Git tree could not be established")
    tree_entries: dict[str, tuple[str, str]] = {}
    try:
        for raw_entry in tree.stdout.split(b"\0"):
            if not raw_entry:
                continue
            metadata, raw_path = raw_entry.split(b"\t", 1)
            mode, kind, object_id = metadata.decode("ascii").split()
            relative = raw_path.decode("utf-8")
            if kind != "blob" or mode not in {"100644", "100755"}:
                raise FreshnessError(f"unsupported Git tree entry: {relative}")
            if relative in tree_entries:
                raise FreshnessError(f"duplicate Git tree path: {relative}")
            tree_entries[relative] = (mode, object_id)
    except (UnicodeDecodeError, ValueError) as exc:
        raise FreshnessError("repository Git tree has malformed or non-UTF-8 entries") from exc

    signed_files = manifest["repositoryFiles"]
    expected_paths = set(signed_files) | {
        "integrity/manifest.json",
        "integrity/manifest.json.sig",
    }
    if set(tree_entries) != expected_paths:
        raise FreshnessError(
            "signed repository closure differs from the indexed Git tree: "
            f"missing={sorted(expected_paths - set(tree_entries))} "
            f"unexpected={sorted(set(tree_entries) - expected_paths)}"
        )
    special_bytes = {
        "integrity/manifest.json": manifest_data,
        "integrity/manifest.json.sig": manifest_signature,
    }
    for relative in sorted(expected_paths):
        mode, object_id = tree_entries[relative]
        if relative in special_bytes:
            data = special_bytes[relative]
            expected_mode = 0o644
        else:
            expected_digest, expected_size, expected_mode = _manifest_file_record(
                signed_files[relative], f"repositoryFiles[{relative!r}]"
            )
            data = _read_regular_snapshot(
                repo_root / relative,
                f"signed repository file {relative}",
                MAX_REPOSITORY_FILE_BYTES,
            )
            if len(data) != expected_size or sha256_bytes(data) != expected_digest:
                raise FreshnessError(f"signed repository file drifted: {relative}")
        canonical_mode = 0o755 if mode == "100755" else 0o644
        if expected_mode != canonical_mode:
            raise FreshnessError(f"signed POSIX mode differs from Git tree: {relative}")
        header = f"blob {len(data)}\0".encode("ascii")
        git_object_id = hashlib.sha1(header + data, usedforsecurity=False).hexdigest()
        if git_object_id != object_id:
            raise FreshnessError(f"signed bytes differ from Git tree object: {relative}")
    return commit


def _run_content_verifier(
    verifier_data: bytes,
    manifest_data: bytes,
    manifest_signature: bytes,
    public_key_data: bytes,
    allowed_signers_data: bytes,
    repo_root: Path,
    python_executable: str,
    ssh_keygen: str,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="idc-fresh-verifier-") as temporary:
        root = Path(temporary)
        os.chmod(root, 0o700)
        verifier = root / "skill_integrity.py"
        manifest = root / "manifest.json"
        public_key = root / "signing.pub"
        allowed = root / "allowed_signers"
        verifier.write_bytes(verifier_data)
        manifest.write_bytes(manifest_data)
        Path(str(manifest) + ".sig").write_bytes(manifest_signature)
        public_key.write_bytes(public_key_data)
        allowed.write_bytes(allowed_signers_data)
        for path in root.iterdir():
            os.chmod(path, 0o600)
        process = subprocess.run(
            [
                python_executable,
                "-I",
                "-B",
                str(verifier),
                "--repo-root",
                str(repo_root),
                "verify",
                "--manifest",
                str(manifest),
                "--public-key",
                str(public_key),
                "--allowed-signers",
                str(allowed),
                "--json",
            ],
            text=True,
            capture_output=True,
            check=False,
            env=_verification_environment((Path(ssh_keygen).parent,)),
        )
    if process.returncode != 0:
        raise FreshnessError(
            "captured content verifier failed: "
            + (process.stderr or process.stdout).strip()
        )
    try:
        report = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise FreshnessError("captured content verifier returned invalid JSON") from exc
    if not isinstance(report, dict):
        raise FreshnessError("captured content verifier report must be an object")
    return report


ContentRunner = Callable[
    [bytes, bytes, bytes, bytes, bytes, Path, str, str], dict[str, Any]
]
ConsumerRunner = Callable[[Path, str, Mapping[str, Any]], int]


def _require_content_ready(
    content_report: Mapping[str, Any], manifest: Mapping[str, Any]
) -> None:
    if content_report.get("readyToRun") is not None:
        raise FreshnessError("in-tree verifier improperly emitted whole-tree readiness")
    if not (
        content_report.get("schema") == "idc-skill-integrity-report/v2"
        and content_report.get("contentReady") is True
        and content_report.get("score") == "5/5"
        and content_report.get("profile") == "release"
        and content_report.get("skillsChecked") == 50
        and content_report.get("authority") == "content-only"
        and content_report.get("release") == manifest["release"]
        and content_report.get("manifestSequence") == manifest["manifestSequence"]
    ):
        raise FreshnessError(
            "captured content verifier did not return release contentReady at 5/5"
        )


def verify_release(
    repo_root: Path,
    config_path: Path,
    *,
    launcher_path: Path | None = None,
    expected_fingerprint: str = EXPECTED_SIGNING_FINGERPRINT,
    mode: str = "release",
    now: dt.datetime | None = None,
    clock: Callable[[], dt.datetime] | None = None,
    content_runner: ContentRunner = _run_content_verifier,
    consumer_runner: ConsumerRunner | None = None,
) -> dict[str, Any]:
    if mode not in {"release", "ci", "operator", "offline"}:
        raise FreshnessError(f"unsupported freshness mode: {mode!r}")
    repo_root = repo_root.resolve(strict=True)
    config_path = config_path.absolute()
    launcher_path = (launcher_path or Path(__file__)).absolute()
    if _path_is_within(launcher_path, repo_root):
        raise FreshnessError(
            "the authoritative freshness launcher must be installed outside the repository"
        )
    launcher_data = _read_regular_snapshot(
        launcher_path,
        "freshness launcher",
        MAX_VERIFIER_BYTES,
        require_single_link=True,
    )
    config_data = _read_regular_snapshot(
        config_path,
        "freshness configuration",
        MAX_CONFIG_BYTES,
        require_single_link=True,
    )
    if os.name != "nt":
        for path, label in (
            (launcher_path, "freshness launcher"),
            (config_path, "freshness configuration"),
        ):
            metadata = path.stat()
            if metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022:
                raise FreshnessError(
                    f"{label} must be owner-controlled and not group/world writable"
                )
    config = parse_config(config_data, repo_root=repo_root, config_path=config_path)
    python_executable = config["executables"]["python"]
    git_executable = config["executables"]["git"]
    ssh_keygen = config["executables"]["sshKeygen"]

    public_path = repo_root / "keys" / "idc-skills-signing.pub"
    allowed_path = repo_root / "keys" / "allowed_signers"
    manifest_path = repo_root / "integrity" / "manifest.json"
    verifier_path = repo_root / "scripts" / "skill_integrity.py"
    public_data = _read_regular_snapshot(public_path, "public signing key", MAX_ANCHOR_BYTES)
    allowed_data = _read_regular_snapshot(allowed_path, "allowed_signers", MAX_ANCHOR_BYTES)
    validate_anchor(public_data, allowed_data, expected_fingerprint, ssh_keygen)
    manifest_data = _read_regular_snapshot(manifest_path, "integrity manifest", MAX_MANIFEST_BYTES)
    manifest_signature = _read_regular_snapshot(
        Path(str(manifest_path) + ".sig"), "integrity manifest signature", MAX_SIGNATURE_BYTES
    )
    verifier_data = _read_regular_snapshot(verifier_path, "content verifier", MAX_VERIFIER_BYTES)
    verify_signature(
        manifest_data,
        manifest_signature,
        allowed_data,
        MANIFEST_NAMESPACE,
        ssh_keygen,
    )
    manifest = parse_manifest(manifest_data)
    for relative, data, label in (
        ("bootstrap/idc_verify_fresh.py", launcher_data, "freshness launcher"),
        ("scripts/skill_integrity.py", verifier_data, "content verifier"),
        ("keys/idc-skills-signing.pub", public_data, "public signing key"),
        ("keys/allowed_signers", allowed_data, "allowed_signers"),
    ):
        _require_captured_repository_file(manifest, relative, data, label)
    if manifest["manifestSequence"] < config["minimumManifestSequence"]:
        raise FreshnessError("integrity manifest is below the configured manifest floor")

    if mode == "offline":
        with _staged_repository(
            repo_root, manifest, manifest_data, manifest_signature
        ) as staged_repo:
            content_report = content_runner(
                verifier_data,
                manifest_data,
                manifest_signature,
                public_data,
                allowed_data,
                staged_repo,
                python_executable,
                ssh_keygen,
            )
            _require_content_ready(content_report, manifest)
            if _read_regular_snapshot(
                manifest_path, "integrity manifest", MAX_MANIFEST_BYTES
            ) != manifest_data:
                raise FreshnessError(
                    "integrity manifest changed during offline content verification"
                )
            if _read_regular_snapshot(
                verifier_path, "content verifier", MAX_VERIFIER_BYTES
            ) != verifier_data:
                raise FreshnessError(
                    "content verifier changed during offline content verification"
                )
        return {
            "schema": REPORT_SCHEMA,
            "pass": False,
            "readyToRun": False,
            "contentReady": True,
            "freshnessVerified": False,
            "freshness": "UNVERIFIED",
            "score": "5/5+freshness-unverified",
            "release": manifest["release"],
            "manifestSequence": manifest["manifestSequence"],
            "expectedSigningFingerprint": expected_fingerprint,
            "authority": "external-content-only",
        }

    index_data, index_signature = capture_index_source(config)
    index_digest = sha256_bytes(index_data)
    verify_signature(
        index_data,
        index_signature,
        allowed_data,
        INDEX_NAMESPACE,
        ssh_keygen,
    )
    current_time = (
        now
        if now is not None
        else (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
    )
    index = parse_index(index_data, now=current_time)
    if index["indexSequence"] < config["minimumIndexSequence"]:
        raise FreshnessError("release index is below the configured index floor")

    entry = index["releases"][-1]
    expected_entry = {
        "release": manifest["release"],
        "manifestSequence": manifest["manifestSequence"],
        "manifestSHA256": sha256_bytes(manifest_data),
        "verifierSHA256": sha256_bytes(verifier_data),
        "launcherSHA256": sha256_bytes(launcher_data),
        "gitCommit": entry["gitCommit"],
    }
    if config["requireGitCommit"]:
        expected_entry["gitCommit"] = _git_commit(
            repo_root,
            git_executable,
            manifest,
            manifest_data,
            manifest_signature,
        )
    if entry != expected_entry:
        raise FreshnessError("repository release tuple does not equal the newest signed index entry")

    checkpoint_path = Path(config["checkpointPath"])
    with _checkpoint_lock(checkpoint_path):
        validate_checkpoint(
            _load_checkpoint(checkpoint_path),
            index,
            index_digest,
            config["bootstrapIndexSHA256"],
        )

    consumer_exit_code: int | None = None
    with _staged_repository(
        repo_root,
        manifest,
        manifest_data,
        manifest_signature,
    ) as staged_repo:
        content_report = content_runner(
            verifier_data,
            manifest_data,
            manifest_signature,
            public_data,
            allowed_data,
            staged_repo,
            python_executable,
            ssh_keygen,
        )
        _require_content_ready(content_report, manifest)

        if _read_regular_snapshot(
            manifest_path, "integrity manifest", MAX_MANIFEST_BYTES
        ) != manifest_data:
            raise FreshnessError("integrity manifest changed during freshness verification")
        if _read_regular_snapshot(
            verifier_path, "content verifier", MAX_VERIFIER_BYTES
        ) != verifier_data:
            raise FreshnessError("content verifier changed during freshness verification")
        if _read_regular_snapshot(
            launcher_path,
            "freshness launcher",
            MAX_VERIFIER_BYTES,
            require_single_link=True,
        ) != launcher_data:
            raise FreshnessError("freshness launcher changed during verification")
        if _read_regular_snapshot(
            config_path,
            "freshness configuration",
            MAX_CONFIG_BYTES,
            require_single_link=True,
        ) != config_data:
            raise FreshnessError("freshness configuration changed during verification")

        # Revalidate both the expiring signed index and the externally pinned
        # runtime immediately before the state transition and any child action.
        current_time = (
            now
            if now is not None
            else (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
        )
        parse_index(index_data, now=current_time)
        final_config = parse_config(
            config_data, repo_root=repo_root, config_path=config_path
        )

        checkpoint_value = _checkpoint_value(index, index_digest)
        with _checkpoint_lock(checkpoint_path):
            validate_checkpoint(
                _load_checkpoint(checkpoint_path),
                index,
                index_digest,
                config["bootstrapIndexSHA256"],
            )
            _write_checkpoint(checkpoint_path, checkpoint_value)

        if consumer_runner is not None:
            current_time = (
                now
                if now is not None
                else (clock or (lambda: dt.datetime.now(dt.timezone.utc)))()
            )
            parse_index(index_data, now=current_time)
            consumer_exit_code = consumer_runner(
                staged_repo, index_digest, final_config
            )

        report = {
            "schema": REPORT_SCHEMA,
            "pass": True,
            "readyToRun": True,
            "contentReady": True,
            "freshnessVerified": True,
            "score": "5/5+freshness",
            "release": manifest["release"],
            "manifestSequence": manifest["manifestSequence"],
            "indexSequence": index["indexSequence"],
            "indexSHA256": index_digest,
            "gitCommit": entry["gitCommit"],
            "expectedSigningFingerprint": expected_fingerprint,
            "authority": "external-signed-index",
            "mode": mode,
        }
        if consumer_exit_code is not None:
            report["consumerExitCode"] = consumer_exit_code
        return report


def _print_report(report: Mapping[str, Any]) -> None:
    print(
        "READY 5/5+freshness — "
        f"release={report['release']} manifestSequence={report['manifestSequence']} "
        f"indexSequence={report['indexSequence']} commit={report['gitCommit']}"
    )


def _run_consumer(
    args: argparse.Namespace,
    staged_repo: Path,
    handoff: str,
    config: Mapping[str, Any],
) -> int:
    command_args = list(getattr(args, "consumer_args", []))
    if command_args and command_args[0] == "--":
        command_args.pop(0)
    if any(
        value.startswith("--repo-r")
        for value in command_args
    ):
        raise FreshnessError("consumer arguments may not override the verified repository root")
    installer_commands = {
        "install": "install",
        "export-claude-ai": "export-claude-ai",
        "export-claude-ai-snapshot": "export-claude-ai-snapshot",
    }
    if args.command in installer_commands:
        script = staged_repo / "scripts" / "install.py"
        child_args = [
            "--repo-root",
            str(staged_repo),
            installer_commands[args.command],
            *command_args,
        ]
    elif args.command == "hook":
        script = staged_repo / "scripts" / "pretooluse-skill-integrity.py"
        child_args = ["--repo-root", str(staged_repo), *command_args]
    else:
        if command_args:
            raise FreshnessError("reaccept does not accept forwarded arguments")
        script = staged_repo / "scripts" / "reaccept.py"
        child_args = []
    executable_directories = [
        Path(path).parent for path in config["executables"].values()
    ]
    executable_directories.extend(Path(path) for path in config["consumerPath"])
    executable_directories = list(dict.fromkeys(executable_directories))
    environment = _verification_environment(executable_directories)
    environment["HOME"] = config["consumerHome"]
    environment["USERPROFILE"] = config["consumerHome"]
    # This marker prevents accidental direct routing in current code. It is not
    # the trust boundary; the independently pinned launcher is.
    environment["IDC_SKILLS_FRESHNESS_HANDOFF"] = handoff
    bootstrap = (
        "import runpy,sys;"
        "scripts=sys.argv[1];script=sys.argv[2];argv=sys.argv[3:];"
        "sys.path.insert(0,scripts);sys.argv=[script,*argv];"
        "runpy.run_path(script,run_name='__main__')"
    )
    with tempfile.TemporaryDirectory(prefix="idc-fresh-consumer-") as temporary:
        environment.update({key: temporary for key in ("TMPDIR", "TMP", "TEMP")})
        process = subprocess.run(
            [
                config["executables"]["python"],
                "-I",
                "-B",
                "-c",
                bootstrap,
                str(staged_repo / "scripts"),
                str(script),
                *child_args,
            ],
            env=environment,
            cwd=staged_repo,
            check=False,
        )
    return process.returncode


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("release", "ci", "operator", "offline"),
        default="release",
    )
    parser.add_argument("--json", action="store_true")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("verify", allow_abbrev=False)
    for name in (
        "install",
        "export-claude-ai",
        "export-claude-ai-snapshot",
        "hook",
        "reaccept",
    ):
        child = subparsers.add_parser(name, allow_abbrev=False)
        child.add_argument("consumer_args", nargs=argparse.REMAINDER)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.mode == "offline" and args.command != "verify":
            raise FreshnessError("offline mode never authorizes a consumer")
        consumer_runner = None
        if args.command != "verify":
            consumer_runner = lambda staged, handoff, config: _run_consumer(
                args, staged, handoff, config
            )
        report = verify_release(
            args.repo_root,
            args.config,
            mode=args.mode,
            consumer_runner=consumer_runner,
        )
    except (FreshnessError, OSError, subprocess.SubprocessError) as exc:
        failure = {
            "schema": REPORT_SCHEMA,
            "pass": False,
            "readyToRun": False,
            "freshnessVerified": False,
            "error": str(exc),
        }
        if args.json:
            print(json.dumps(failure, sort_keys=True, indent=2))
        else:
            print(f"NOT READY — {exc}", file=sys.stderr)
        return 2
    if args.command != "verify":
        return int(report["consumerExitCode"])
    if report.get("readyToRun") is not True:
        if args.json:
            print(json.dumps(report, sort_keys=True, indent=2))
        else:
            print(
                "FRESHNESS UNVERIFIED — signed content is valid, but whole-tree "
                "rollback cannot be excluded offline",
                file=sys.stderr,
            )
        return 3
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        _print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
