#!/usr/bin/env python3
"""Dependency-free IDC threshold-root and release-statement verification.

The cryptographic primitive is OpenSSH sshsig. The trust model follows the TUF
root-update rules: an initial root arrives out of band; every next root is exactly
version N+1 and is authorized by both the old and new root thresholds.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT_SCHEMA = "idc-skills-root/v1"
RELEASE_SCHEMA = "idc-skills-release-statement/v1"
ROOT_NAMESPACE = "idc-skills-root-v1"
RELEASE_NAMESPACE = "idc-skills-release-statement-v1"
MAX_METADATA_BYTES = 512 * 1024
MAX_SIGNATURES = 64
MAX_KEYS = 64
MAX_ROOT_UPDATES = 32
ROOT_CHECKPOINT_SCHEMA = "idc-skills-root-checkpoint/v1"
SHA256_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
HEX40_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASE_RE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


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


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


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
    if type(value) is not int or value < 1:
        raise TrustError(f"{label} must be a positive integer")
    return value


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


def load_envelope(path: Path, label: str) -> ParsedEnvelope:
    raw = _regular_bytes(path, label)
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


def update_root_chain(
    initial_envelope: ParsedEnvelope,
    initial_root: Mapping[str, Any],
    updates: Sequence[Path],
    *,
    ssh_keygen: Path,
    now: dt.datetime | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any]]:
    if len(updates) > MAX_ROOT_UPDATES:
        raise TrustError(f"root update chain exceeds {MAX_ROOT_UPDATES} versions")
    current_envelope, current_root = initial_envelope, initial_root
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
    if _expiry(current_root["expires"], "final root expires") <= _now(now):
        raise TrustError(f"final trusted root version {current_root['version']} is expired")
    return current_envelope, current_root


def root_checkpoint(envelope: ParsedEnvelope, root: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "rootSHA256": envelope.digest,
        "schema": ROOT_CHECKPOINT_SCHEMA,
        "version": root["version"],
    }


def validate_root_checkpoint(
    checkpoint_data: bytes | None,
    final_envelope: ParsedEnvelope,
    final_root: Mapping[str, Any],
) -> dict[str, Any]:
    next_checkpoint = root_checkpoint(final_envelope, final_root)
    if checkpoint_data is None:
        return next_checkpoint
    try:
        value = json.loads(checkpoint_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"root checkpoint is not strict UTF-8 JSON: {exc}") from exc
    if checkpoint_data != canonical_json(value):
        raise TrustError("root checkpoint is not canonical JSON")
    checkpoint = _exact_keys(value, {"rootSHA256", "schema", "version"}, "root checkpoint")
    if checkpoint["schema"] != ROOT_CHECKPOINT_SCHEMA:
        raise TrustError("root checkpoint schema is unsupported")
    version = _positive_int(checkpoint["version"], "root checkpoint version")
    digest = checkpoint["rootSHA256"]
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        raise TrustError("root checkpoint digest is invalid")
    if final_root["version"] < version:
        raise TrustError(
            f"root rollback against external checkpoint: final version {final_root['version']} is below {version}"
        )
    if final_root["version"] == version and final_envelope.digest != digest:
        raise TrustError(f"root equivocation against external checkpoint at version {version}")
    return next_checkpoint


def parse_release(envelope: ParsedEnvelope) -> Mapping[str, Any]:
    release = _exact_keys(
        envelope.signed,
        {"_type", "artifacts", "expires", "git", "release", "releaseSequence", "rootVersion", "schema"},
        "release statement.signed",
    )
    if release["_type"] != "release" or release["schema"] != RELEASE_SCHEMA:
        raise TrustError("release statement has unsupported type or schema")
    if not isinstance(release["release"], str) or not RELEASE_RE.fullmatch(release["release"]):
        raise TrustError("release statement release must be semantic-version shaped")
    _positive_int(release["releaseSequence"], "release statement releaseSequence")
    _positive_int(release["rootVersion"], "release statement rootVersion")
    _expiry(release["expires"], "release statement expires")
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


def _git(git: Path, repo: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            [str(git), "-C", str(repo), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
            env={"LC_ALL": "C", "LANG": "C"},
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TrustError(f"Git identity check could not run: {exc}") from exc
    if completed.returncode != 0:
        raise TrustError(f"Git identity check failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def verify_release_statement(
    statement_path: Path,
    trusted_root: Mapping[str, Any],
    *,
    ssh_keygen: Path,
    git: Path,
    repo: Path,
    artifacts: Mapping[str, Path],
    now: dt.datetime | None = None,
) -> tuple[ParsedEnvelope, Mapping[str, Any]]:
    statement = load_envelope(statement_path, "release statement")
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
    for name in sorted(required):
        path = artifacts[name]
        size, digest = _regular_digest(
            path, f"{name} artifact", maximum=2 * 1024 * 1024 * 1024
        )
        expected = release["artifacts"][name]
        if size != expected["size"] or digest != expected["sha256"]:
            raise TrustError(f"{name} artifact differs from the threshold-signed release statement")
    git_record = release["git"]
    head = _git(git, repo, "rev-parse", "HEAD")
    tag_commit = _git(git, repo, "rev-parse", f"refs/tags/{git_record['tag']}^{{commit}}")
    tag_tree = _git(git, repo, "rev-parse", f"refs/tags/{git_record['tag']}^{{tree}}")
    if head != git_record["commit"] or tag_commit != git_record["commit"]:
        raise TrustError("release tag, repository HEAD, and signed commit do not agree")
    if tag_tree != git_record["tree"]:
        raise TrustError("release tag tree differs from the signed tree")
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
    final_envelope, final_root = update_root_chain(
        initial_envelope,
        initial_root,
        root_updates,
        ssh_keygen=ssh_keygen,
        now=now,
    )
    next_root_checkpoint = validate_root_checkpoint(
        root_checkpoint_data, final_envelope, final_root
    )
    statement, release = verify_release_statement(
        statement_path,
        final_root,
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
        "statementSHA256": statement.digest,
        "git": release["git"],
        "artifacts": release["artifacts"],
    }
