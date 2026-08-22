#!/usr/bin/env python3
"""Verify a canonical, detached-signed egress-waiver policy.

The trusted fingerprint and allowed-signers file are caller-owned inputs.  They
must be obtained independently of the artifact or repository being scanned.
Verified policy bytes are written to stdout so the scanner can consume the
same snapshot that was authenticated instead of reopening a mutable path.
"""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "idc-egress-waiver-policy/v1"
IDENTITY = "idc-egress-waiver"
NAMESPACE = "idc-egress-waiver"
MAX_POLICY_BYTES = 4 * 1024 * 1024
MAX_SIGNATURE_BYTES = 1024 * 1024
MAX_ANCHOR_BYTES = 64 * 1024
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
REVISION_RE = re.compile(r"[0-9a-f]{40}\Z")
FINGERPRINT_RE = re.compile(r"SHA256:[A-Za-z0-9+/]{43}\Z")


class PolicyError(RuntimeError):
    """A deterministic policy, anchor, or signature failure."""


def _snapshot(path: Path, label: str, limit: int) -> bytes:
    try:
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_size > limit:
            raise PolicyError(f"{label} must be a regular file no larger than {limit} bytes")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or (before.st_dev, before.st_ino) != (
                opened.st_dev,
                opened.st_ino,
            ):
                raise PolicyError(f"{label} identity changed before open")
            blocks: list[bytes] = []
            remaining = limit + 1
            while remaining:
                block = os.read(descriptor, min(128 * 1024, remaining))
                if not block:
                    break
                blocks.append(block)
                remaining -= len(block)
            after = os.fstat(descriptor)
        finally:
            os.close(descriptor)
    except OSError as exc:
        raise PolicyError(f"cannot read {label}: {exc}") from exc
    if (
        opened.st_size > limit
        or sum(map(len, blocks)) != opened.st_size
        or (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns, opened.st_ctime_ns)
        != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns)
    ):
        raise PolicyError(f"{label} changed while it was read or exceeds its byte ceiling")
    return b"".join(blocks)


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise PolicyError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def _timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise PolicyError(f"{label} must be an RFC 3339 UTC timestamp ending in Z")
    try:
        parsed = dt.datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise PolicyError(f"{label} is not a valid timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise PolicyError(f"{label} must be UTC")
    return parsed


def _safe_path(value: Any) -> str:
    if not isinstance(value, str) or not value or value != unicodedata.normalize("NFC", value):
        raise PolicyError("waiver path must be a non-empty NFC string")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "." in path.parts or "\\" in value:
        raise PolicyError(f"waiver path is not a canonical relative POSIX path: {value!r}")
    if path.as_posix() != value:
        raise PolicyError(f"waiver path is not canonical: {value!r}")
    return value


def load_policy(data: bytes, revision: str, now: dt.datetime) -> dict[str, Any]:
    try:
        value = json.loads(data.decode("utf-8"), object_pairs_hook=_pairs)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PolicyError("policy is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or set(value) != {
        "schema",
        "revision",
        "issuedAt",
        "expiresAt",
        "waivers",
    }:
        raise PolicyError("policy top-level keys differ from the v1 schema")
    if data != canonical_bytes(value):
        raise PolicyError("policy JSON is not canonical")
    if value["schema"] != SCHEMA:
        raise PolicyError(f"unsupported policy schema: {value['schema']!r}")
    if not isinstance(value["revision"], str) or REVISION_RE.fullmatch(value["revision"]) is None:
        raise PolicyError("policy revision must be an exact lowercase 40-hex Git object id")
    if value["revision"] != revision:
        raise PolicyError(f"policy revision mismatch: expected {revision}, got {value['revision']}")
    issued = _timestamp(value["issuedAt"], "issuedAt")
    expires = _timestamp(value["expiresAt"], "expiresAt")
    if issued > now:
        raise PolicyError("policy is not yet valid")
    if expires <= now or expires <= issued:
        raise PolicyError("policy is expired or has a non-positive validity interval")
    if not isinstance(value["waivers"], list):
        raise PolicyError("waivers must be an array")
    seen: set[tuple[str, str]] = set()
    for index, waiver in enumerate(value["waivers"]):
        label = f"waivers[{index}]"
        if not isinstance(waiver, dict) or set(waiver) != {
            "path",
            "fileSha256",
            "findingFingerprint",
            "reviewer",
            "reason",
            "expiresAt",
        }:
            raise PolicyError(f"{label} keys differ from the v1 schema")
        waiver["path"] = _safe_path(waiver["path"])
        if not isinstance(waiver["fileSha256"], str) or SHA256_RE.fullmatch(waiver["fileSha256"]) is None:
            raise PolicyError(f"{label}.fileSha256 is invalid")
        if not isinstance(waiver["findingFingerprint"], str) or SHA256_RE.fullmatch(
            waiver["findingFingerprint"]
        ) is None:
            raise PolicyError(f"{label}.findingFingerprint is invalid")
        for field in ("reviewer", "reason"):
            text = waiver[field]
            if not isinstance(text, str) or not text.strip() or len(text) > 1024 or any(
                ord(char) < 0x20 for char in text
            ):
                raise PolicyError(f"{label}.{field} must be non-empty bounded printable text")
        waiver_expiry = _timestamp(waiver["expiresAt"], f"{label}.expiresAt")
        if waiver_expiry <= now or waiver_expiry > expires:
            raise PolicyError(f"{label} is expired or outlives the policy")
        identity = (waiver["path"], waiver["findingFingerprint"])
        if identity in seen:
            raise PolicyError(f"duplicate waiver identity: {identity[0]} {identity[1]}")
        seen.add(identity)
    return value


def _public_fingerprint(key_type: str, key_blob: str) -> str:
    try:
        raw = base64.b64decode(key_blob.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error) as exc:
        raise PolicyError("allowed-signers key is not valid base64") from exc
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    if not key_type.startswith("ssh-") and not key_type.startswith("ecdsa-"):
        raise PolicyError("allowed-signers key type is unsupported")
    return "SHA256:" + digest


def validate_allowed_signers(data: bytes, expected_fingerprint: str) -> None:
    if FINGERPRINT_RE.fullmatch(expected_fingerprint) is None:
        raise PolicyError("expected fingerprint is not canonical SHA256 OpenSSH form")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PolicyError("allowed-signers is not UTF-8") from exc
    lines = [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]
    if len(lines) != 1:
        raise PolicyError("allowed-signers must contain exactly one non-comment signer")
    fields = lines[0].split()
    if len(fields) < 3 or IDENTITY not in fields[0].split(","):
        raise PolicyError(f"allowed-signers must bind principal {IDENTITY!r}")
    observed = _public_fingerprint(fields[1], fields[2])
    if observed != expected_fingerprint:
        raise PolicyError(f"allowed-signers fingerprint mismatch: expected {expected_fingerprint}, got {observed}")


def verify_signature(policy: bytes, signature: bytes, allowed_signers: bytes) -> None:
    try:
        with tempfile.TemporaryDirectory(prefix="idc-egress-policy-") as temporary:
            root = Path(temporary)
            allowed = root / "allowed_signers"
            sig = root / "policy.sig"
            allowed.write_bytes(allowed_signers)
            sig.write_bytes(signature)
            os.chmod(allowed, 0o600)
            os.chmod(sig, 0o600)
            process = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed),
                    "-I",
                    IDENTITY,
                    "-n",
                    NAMESPACE,
                    "-s",
                    str(sig),
                ],
                input=policy,
                capture_output=True,
                check=False,
            )
    except FileNotFoundError as exc:
        raise PolicyError("ssh-keygen is required for waiver signature verification") from exc
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).decode("utf-8", errors="replace").strip()
        raise PolicyError(f"waiver signature invalid: {detail}")


def verify(
    policy_path: Path,
    signature_path: Path,
    allowed_signers_path: Path,
    expected_fingerprint: str,
    revision: str,
    now: dt.datetime | None = None,
) -> bytes:
    if REVISION_RE.fullmatch(revision) is None:
        raise PolicyError("--revision must be an exact lowercase 40-hex Git object id")
    policy = _snapshot(policy_path, "waiver policy", MAX_POLICY_BYTES)
    signature = _snapshot(signature_path, "waiver signature", MAX_SIGNATURE_BYTES)
    allowed_signers = _snapshot(allowed_signers_path, "waiver allowed-signers", MAX_ANCHOR_BYTES)
    validate_allowed_signers(allowed_signers, expected_fingerprint)
    verify_signature(policy, signature, allowed_signers)
    load_policy(policy, revision, now or dt.datetime.now(dt.timezone.utc))
    return policy


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--signature", required=True, type=Path)
    parser.add_argument("--allowed-signers", required=True, type=Path)
    parser.add_argument("--expected-fingerprint", required=True)
    parser.add_argument("--revision", required=True)
    args = parser.parse_args(argv)
    try:
        sys.stdout.buffer.write(
            verify(
                args.policy,
                args.signature,
                args.allowed_signers,
                args.expected_fingerprint,
                args.revision,
            )
        )
    except PolicyError as exc:
        print(f"verify-egress-policy: FAIL — {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
