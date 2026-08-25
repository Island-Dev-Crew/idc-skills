#!/usr/bin/env python3
"""Verify externally captured GitHub, site, and second-channel release facts."""

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
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))

from trust_root import (
    RELEASE_NAMESPACE,
    TrustError,
    load_trusted_root,
    parse_envelope_bytes,
    parse_release,
    update_root_chain,
    verify_role_threshold,
)


SCHEMA = "idc-public-release-evidence/v2"
OBSERVER_AUTHORITY_SCHEMA = "idc-publication-observer-authority/v1"
OBSERVATION_SCHEMA = "idc-publication-observation/v1"
OBSERVER_NAMESPACE = "idc-publication-observation-v1"
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_RECORD = 512 * 1024
MAX_ARTIFACT = 64 * 1024 * 1024


class PublicationError(RuntimeError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise PublicationError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def exact(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise PublicationError(f"{label} fields differ")
    return value


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def snapshot(path: Path, label: str, ceiling: int = MAX_ARTIFACT) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise PublicationError(f"{label} must be an absolute non-symlink file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > ceiling:
        raise PublicationError(f"{label} must be a bounded regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        data = os.read(descriptor, ceiling + 1)
    finally:
        os.close(descriptor)
    after = path.stat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns)
    if identity(before) != identity(opened) or identity(opened) != identity(after) or len(data) != opened.st_size:
        raise PublicationError(f"{label} changed during capture")
    return data


def outside(path: Path, repo: Path, label: str) -> None:
    try:
        path.resolve(strict=True).relative_to(repo)
    except ValueError:
        return
    raise PublicationError(f"{label} must remain outside the candidate repository")


def validate_tool(
    path: Path,
    expected_sha256: str,
    repo: Path,
    label: str,
) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise PublicationError(f"{label} must be an absolute non-symlink executable")
    resolved = path.resolve(strict=True)
    outside(resolved, repo, label)
    metadata = resolved.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        raise PublicationError(f"{label} must be a regular executable")
    if os.name != "nt" and metadata.st_nlink != 1 and metadata.st_uid != 0:
        raise PublicationError(
            f"{label} must be single-link unless it is a root-owned system executable"
        )
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise PublicationError(
            f"{label} must be owner-controlled and not group/world writable"
        )
    data = snapshot(resolved, label, 128 * 1024 * 1024)
    if not SHA256.fullmatch(expected_sha256) or digest(data) != expected_sha256:
        raise PublicationError(f"{label} executable digest differs")
    return resolved


def controlled_external_bytes(
    path: Path,
    repo: Path,
    label: str,
    ceiling: int,
) -> bytes:
    outside(path, repo, label)
    data = snapshot(path, label, ceiling)
    metadata = path.stat()
    if metadata.st_nlink != 1:
        raise PublicationError(f"{label} must be a single-link regular file")
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise PublicationError(
            f"{label} must be owner-controlled and not group/world writable"
        )
    return data


def receipt(value: Any, repo: Path, label: str) -> bytes:
    record = exact(value, {"path", "sha256", "size"}, label)
    path = Path(record["path"])
    outside(path, repo, label)
    data = snapshot(path, label)
    if record["sha256"] != digest(data) or record["size"] != len(data):
        raise PublicationError(f"{label} bytes differ")
    return data


def structured_receipt(
    value: Any,
    repo: Path,
    label: str,
    schema: str,
    keys: set[str],
) -> Mapping[str, Any]:
    data = receipt(value, repo, label)
    payload = json.loads(data, object_pairs_hook=reject_duplicates)
    exact(payload, keys | {"schema"}, f"{label} payload")
    if payload["schema"] != schema:
        raise PublicationError(f"{label} schema differs")
    return payload


def observation_payload(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return the exact public-observation facts an external witness signs."""
    threshold = record["threshold"]
    github = record["github"]
    site = record["site"]
    second = record["secondChannel"]
    return {
        "candidate": record["candidate"],
        "channels": {
            "github": {
                "releaseURL": github["releaseURL"],
                "repository": github["repository"],
            },
            "second": {
                "kind": second["kind"],
                "locator": second["locator"],
            },
            "site": {
                "landingURL": site["landingURL"],
                "rootDigestURL": site["rootDigestURL"],
            },
        },
        "receipts": {
            "githubRelease": github["releaseReceipt"]["sha256"],
            "githubTag": github["tagVerificationReceipt"]["sha256"],
            "secondChannel": second["receipt"]["sha256"],
            "siteAdministration": site["administrationReceipt"]["sha256"],
            "siteLanding": site["landingReceipt"]["sha256"],
            "siteRootDigest": site["rootDigestReceipt"]["sha256"],
            "thresholdVerification": threshold["verificationReceipt"]["sha256"],
        },
        "releaseStatementSHA256": threshold["releaseStatement"]["sha256"],
        "root": record["root"],
        "schema": OBSERVATION_SCHEMA,
    }


def _ssh_key_blob_id(public: str, label: str) -> str:
    parts = public.split()
    if len(parts) != 2 or parts[0] != "ssh-ed25519":
        raise PublicationError(f"{label} must be one comment-free ssh-ed25519 key")
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PublicationError(f"{label} key body is not canonical base64") from exc
    if not blob or base64.b64encode(blob).decode("ascii") != parts[1]:
        raise PublicationError(f"{label} key body is not canonical base64")
    return hashlib.sha256(blob).hexdigest()


def _ssh_fingerprint_blob_id(fingerprint: str, label: str) -> str:
    if not isinstance(fingerprint, str) or not fingerprint.startswith("SHA256:"):
        raise PublicationError(f"{label} must be a canonical SHA256 fingerprint")
    encoded = fingerprint.removeprefix("SHA256:")
    try:
        fingerprint_bytes = base64.b64decode(encoded + "=", validate=True)
    except (binascii.Error, ValueError) as exc:
        raise PublicationError(
            f"{label} must be a canonical SHA256 fingerprint"
        ) from exc
    canonical = base64.b64encode(fingerprint_bytes).decode("ascii").rstrip("=")
    if len(fingerprint_bytes) != hashlib.sha256().digest_size or canonical != encoded:
        raise PublicationError(f"{label} must be a canonical SHA256 fingerprint")
    return fingerprint_bytes.hex()


def load_observer_authority(
    path: Path,
    expected_sha256: str,
    repo: Path,
) -> Mapping[str, Any]:
    data = controlled_external_bytes(path, repo, "publication observer authority", MAX_RECORD)
    if not SHA256.fullmatch(expected_sha256) or digest(data) != expected_sha256:
        raise PublicationError("publication observer authority digest differs from the external pin")
    value = json.loads(data, object_pairs_hook=reject_duplicates)
    exact(
        value,
        {"allowedSigners", "family", "independent", "principal", "schema"},
        "publication observer authority",
    )
    if value["schema"] != OBSERVER_AUTHORITY_SCHEMA or value["independent"] is not True:
        raise PublicationError("publication observer authority schema or independence differs")
    principal = value["principal"]
    family = value["family"]
    if (
        not isinstance(principal, str)
        or not principal.strip()
        or not isinstance(family, str)
        or not family.strip()
        or family.strip().casefold()
        in {"idc", "island dev crew", "island-dev-crew", "openai"}
    ):
        raise PublicationError("publication observer must be an independent named authority")
    allowed = exact(
        value["allowedSigners"],
        {"path", "sha256", "size"},
        "publication observer allowed_signers",
    )
    allowed_path = Path(allowed["path"])
    allowed_data = controlled_external_bytes(
        allowed_path,
        repo,
        "publication observer allowed_signers",
        64 * 1024,
    )
    if allowed["sha256"] != digest(allowed_data) or allowed["size"] != len(allowed_data):
        raise PublicationError("publication observer allowed_signers bytes differ")
    try:
        lines = [line for line in allowed_data.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise PublicationError("publication observer allowed_signers must be ASCII") from exc
    if len(lines) != 1:
        raise PublicationError("publication observer allowed_signers must contain exactly one key")
    parts = lines[0].split()
    if len(parts) != 3 or parts[0] != principal or parts[1] != "ssh-ed25519":
        raise PublicationError(
            "publication observer allowed_signers must be '<principal> ssh-ed25519 <key>'"
        )
    key_id = _ssh_key_blob_id(" ".join(parts[1:]), "publication observer")
    return {
        "allowedSigners": allowed_data,
        "family": family.strip().casefold(),
        "keyId": key_id,
        "principal": principal,
    }


def verify_observer_attestation(
    record: Mapping[str, Any],
    repo: Path,
    authority: Mapping[str, Any],
    ssh_keygen: Path,
) -> None:
    attestation = exact(
        record["observerAttestation"],
        {"path", "sha256", "signature", "size"},
        "publication observer attestation",
    )
    data = receipt(
        {key: attestation[key] for key in ("path", "sha256", "size")},
        repo,
        "publication observer attestation",
    )
    payload = json.loads(data, object_pairs_hook=reject_duplicates)
    expected = observation_payload(record)
    if payload != expected or data != (json.dumps(
        expected,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ) + "\n").encode("utf-8"):
        raise PublicationError("publication observer attestation facts differ")
    signature_record = exact(
        attestation["signature"],
        {"path", "sha256", "size"},
        "publication observer signature",
    )
    signature_data = receipt(
        signature_record, repo, "publication observer signature"
    )
    with tempfile.TemporaryDirectory(prefix="idc-publication-observer-") as temporary:
        temporary_root = Path(temporary)
        allowed_path = temporary_root / "allowed_signers"
        signature_path = temporary_root / "observation.sig"
        allowed_path.write_bytes(authority["allowedSigners"])
        signature_path.write_bytes(signature_data)
        try:
            process = subprocess.run(
                [
                    str(ssh_keygen),
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_path),
                    "-I",
                    authority["principal"],
                    "-n",
                    OBSERVER_NAMESPACE,
                    "-s",
                    str(signature_path),
                ],
                input=data,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
                env={"PATH": str(ssh_keygen.parent), "LC_ALL": "C"},
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise PublicationError(f"publication observer signature could not be verified: {exc}") from exc
    if process.returncode != 0:
        raise PublicationError("publication observer signature is invalid")


def timestamp(value: Any, label: str) -> dt.datetime:
    if not isinstance(value, str):
        raise PublicationError(f"{label} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError(f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None:
        raise PublicationError(f"{label} must include a timezone")
    return parsed.astimezone(dt.timezone.utc)


def recent_timestamp(value: Any, label: str, now: dt.datetime) -> dt.datetime:
    parsed = timestamp(value, label)
    if parsed > now + dt.timedelta(minutes=5) or parsed < now - dt.timedelta(hours=24):
        raise PublicationError(f"{label} is outside the 24-hour release evidence window")
    return parsed


def https(value: Any, label: str, expected_host: str | None = None) -> str:
    if not isinstance(value, str):
        raise PublicationError(f"{label} must be HTTPS")
    parsed = urlparse(value)
    try:
        port = parsed.port
    except ValueError as exc:
        raise PublicationError(f"{label} must be credential-free HTTPS") from exc
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
        or parsed.params
        or parsed.fragment
    ):
        raise PublicationError(f"{label} must be credential-free HTTPS")
    if expected_host and parsed.hostname.lower() != expected_host.lower():
        raise PublicationError(f"{label} host differs")
    return parsed.hostname.lower()


def git_run(git: Path, repo: Path, *arguments: str) -> str:
    try:
        process = subprocess.run(
            [str(git), "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null", *arguments],
            text=True,
            capture_output=True,
            check=False,
            env={
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_NO_REPLACE_OBJECTS": "1",
                "LC_ALL": "C",
                "PATH": str(git.parent),
            },
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError(f"Git command could not run: {exc}") from exc
    if process.returncode != 0:
        raise PublicationError(f"Git command failed: {' '.join(arguments)}")
    return process.stdout.strip()


def release_payload(data: bytes) -> Mapping[str, Any]:
    envelope = json.loads(data, object_pairs_hook=reject_duplicates)
    exact(envelope, {"signatures", "signed"}, "release statement envelope")
    signed = exact(
        envelope["signed"],
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
        "release statement",
    )
    if signed["schema"] != "idc-skills-release-statement/v1" or signed["_type"] != "release":
        raise PublicationError("release statement schema differs")
    return signed


def verify(
    record_path: Path,
    repo: Path,
    git: Path,
    git_sha256: str,
    canonical_repository: str,
    site_host: str,
    *,
    trusted_root: Path,
    trusted_root_sha256: str,
    ssh_keygen: Path,
    ssh_keygen_sha256: str,
    observer_authority: Path,
    observer_authority_sha256: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    current_time = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    repo = repo.resolve(strict=True)
    outside(record_path, repo, "publication record")
    git = validate_tool(git, git_sha256, repo, "Git")
    ssh_keygen = validate_tool(
        ssh_keygen, ssh_keygen_sha256, repo, "ssh-keygen"
    )
    observer = load_observer_authority(
        observer_authority,
        observer_authority_sha256,
        repo,
    )
    record = json.loads(snapshot(record_path, "publication record", MAX_RECORD), object_pairs_hook=reject_duplicates)
    exact(
        record,
        {
            "candidate",
            "github",
            "observerAttestation",
            "root",
            "schema",
            "secondChannel",
            "site",
            "threshold",
        },
        "publication record",
    )
    if record["schema"] != SCHEMA:
        raise PublicationError("publication record schema differs")
    candidate = exact(record["candidate"], {"commit", "tag", "tree"}, "candidate")
    if not all(isinstance(candidate[field], str) and HEX40.fullmatch(candidate[field]) for field in ("commit", "tree")):
        raise PublicationError("candidate commit or tree differs")
    if candidate["tag"] != "2.0.4":
        raise PublicationError("candidate tag must be 2.0.4")
    local_tag = git_run(git, repo, "rev-parse", "--verify", candidate["tag"])
    if git_run(git, repo, "cat-file", "-t", candidate["tag"]) != "tag":
        raise PublicationError("release tag must be an annotated tag object")
    local_commit = git_run(git, repo, "rev-parse", "--verify", f"{candidate['tag']}^{{commit}}")
    local_tree = git_run(git, repo, "rev-parse", "--verify", f"{candidate['tag']}^{{tree}}")
    if local_commit != candidate["commit"] or local_tree != candidate["tree"]:
        raise PublicationError("local tag does not resolve to the published candidate")
    if git_run(git, repo, "rev-parse", "--verify", "HEAD^{commit}") != candidate["commit"]:
        raise PublicationError("candidate checkout does not match the release tag")
    if git_run(git, repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise PublicationError("candidate repository is dirty")
    if git_run(git, repo, "ls-files", "--others", "--ignored", "--exclude-standard"):
        raise PublicationError("candidate repository contains an ignored payload")

    root = exact(record["root"], {"sha256", "version"}, "root")
    if type(root["version"]) is not int or root["version"] < 1 or not SHA256.fullmatch(root["sha256"]):
        raise PublicationError("root record differs")
    threshold = exact(record["threshold"], {"releaseStatement", "verificationReceipt"}, "threshold")
    statement_data = receipt(threshold["releaseStatement"], repo, "release statement")
    signed = release_payload(statement_data)
    if signed["release"] != candidate["tag"] or signed["rootVersion"] != root["version"] or signed["git"] != candidate:
        raise PublicationError("threshold release statement candidate differs")
    try:
        root_envelope, root_value = load_trusted_root(
            trusted_root,
            repo_root=repo,
            ssh_keygen=ssh_keygen,
            pinned_digest=trusted_root_sha256,
        )
        root_envelope, root_value = update_root_chain(
            root_envelope,
            root_value,
            [],
            ssh_keygen=ssh_keygen,
            now=current_time,
        )
        if root_envelope.digest != root["sha256"] or root_value["version"] != root["version"]:
            raise PublicationError("trusted root differs from the publication record")
        separation_key_ids = {
            _ssh_key_blob_id(key["keyval"]["public"], "trusted root key")
            for key in root_value["keys"].values()
        }
        statement_envelope = parse_envelope_bytes(statement_data, "release statement")
        parsed_release = parse_release(statement_envelope)
        verify_role_threshold(
            statement_envelope,
            root_value,
            "release",
            RELEASE_NAMESPACE,
            ssh_keygen,
            "release signature threshold",
        )
        separation_key_ids.add(
            _ssh_fingerprint_blob_id(
                parsed_release["contentSigning"]["fingerprint"],
                "release content-signing fingerprint",
            )
        )
        if observer["keyId"] in separation_key_ids:
            raise PublicationError(
                "publication observer signing key must be disjoint from root, release, "
                "and content-signing keys"
            )
    except TrustError as exc:
        raise PublicationError(str(exc)) from exc
    if parsed_release != signed:
        raise PublicationError("release statement parser disagreement")
    verify_observer_attestation(record, repo, observer, ssh_keygen)
    release_expiry = dt.datetime.strptime(
        parsed_release["expires"], "%Y-%m-%dT%H:%M:%SZ"
    ).replace(tzinfo=dt.timezone.utc)
    if release_expiry <= current_time:
        raise PublicationError("release statement is expired")
    threshold_receipt = structured_receipt(
        threshold["verificationReceipt"],
        repo,
        "threshold verification receipt",
        "idc-threshold-verification-receipt/v1",
        {"candidate", "externalTrustVerified", "root", "statementSHA256", "verifiedAt"},
    )
    recent_timestamp(
        threshold_receipt["verifiedAt"],
        "threshold verification receipt verifiedAt",
        current_time,
    )
    if (
        threshold_receipt["candidate"] != candidate
        or threshold_receipt["root"] != root
        or threshold_receipt["statementSHA256"] != digest(statement_data)
        or threshold_receipt["externalTrustVerified"] is not True
    ):
        raise PublicationError("threshold verification receipt facts differ")

    github = exact(record["github"], {"assets", "releaseURL", "repository", "releaseReceipt", "tagVerificationReceipt"}, "github")
    if github["repository"] != canonical_repository:
        raise PublicationError("canonical GitHub repository differs")
    https(github["releaseURL"], "GitHub release URL", "github.com")
    release_url = urlparse(github["releaseURL"])
    if release_url.path.rstrip("/") != f"/{canonical_repository}/releases/tag/{candidate['tag']}" or release_url.query:
        raise PublicationError("GitHub release URL does not name the exact tag")
    assets = github["assets"]
    signed_assets = signed["artifacts"]
    if not isinstance(assets, list) or not assets:
        raise PublicationError("GitHub asset inventory is empty")
    observed_assets: dict[str, Mapping[str, Any]] = {}
    for item in assets:
        asset = exact(item, {"name", "sha256", "size"}, "GitHub asset")
        name = asset["name"]
        if (
            not isinstance(name, str)
            or not name
            or name in observed_assets
            or not isinstance(asset["sha256"], str)
            or not SHA256.fullmatch(asset["sha256"])
            or type(asset["size"]) is not int
            or asset["size"] < 0
        ):
            raise PublicationError("GitHub asset inventory differs")
        observed_assets[name] = {"sha256": asset["sha256"], "size": asset["size"]}
    if observed_assets != signed_assets:
        raise PublicationError("GitHub assets differ from the threshold release statement")
    release_receipt = structured_receipt(
        github["releaseReceipt"],
        repo,
        "GitHub release receipt",
        "idc-github-release-receipt/v1",
        {"assets", "candidate", "observedAt", "releaseURL", "repository"},
    )
    recent_timestamp(
        release_receipt["observedAt"], "GitHub release receipt observedAt", current_time
    )
    if (
        release_receipt["repository"] != canonical_repository
        or release_receipt["releaseURL"] != github["releaseURL"]
        or release_receipt["candidate"] != candidate
        or release_receipt["assets"] != assets
    ):
        raise PublicationError("GitHub release receipt facts differ")
    tag_receipt = structured_receipt(
        github["tagVerificationReceipt"],
        repo,
        "tag verification receipt",
        "idc-tag-verification-receipt/v1",
        {"candidate", "observedAt", "tagObject", "verified"},
    )
    recent_timestamp(
        tag_receipt["observedAt"], "tag verification receipt observedAt", current_time
    )
    if tag_receipt["candidate"] != candidate or tag_receipt["tagObject"] != local_tag or tag_receipt["verified"] is not True:
        raise PublicationError("tag verification receipt facts differ")

    site = exact(record["site"], {"administrationReceipt", "landingReceipt", "landingURL", "rootDigestReceipt", "rootDigestURL", "rootSHA256"}, "site")
    https(site["landingURL"], "site landing URL", site_host)
    https(site["rootDigestURL"], "site root digest URL", site_host)
    if site["rootSHA256"] != root["sha256"]:
        raise PublicationError("site root digest differs")
    administration = structured_receipt(
        site["administrationReceipt"],
        repo,
        "site administration receipt",
        "idc-site-administration-receipt/v1",
        {"attestedAt", "githubAdministration", "independent", "siteAdministration"},
    )
    recent_timestamp(
        administration["attestedAt"], "site administration receipt attestedAt", current_time
    )
    if (
        administration["independent"] is not True
        or not isinstance(administration["githubAdministration"], str)
        or not isinstance(administration["siteAdministration"], str)
        or not administration["githubAdministration"].strip()
        or not administration["siteAdministration"].strip()
        or administration["githubAdministration"].strip().casefold() == administration["siteAdministration"].strip().casefold()
    ):
        raise PublicationError("site administration separation differs")
    landing = structured_receipt(
        site["landingReceipt"],
        repo,
        "site landing receipt",
        "idc-site-landing-receipt/v2",
        {"candidate", "landingURL", "observedAt", "releaseURL", "root"},
    )
    recent_timestamp(
        landing["observedAt"], "site landing receipt observedAt", current_time
    )
    if (
        landing["candidate"] != candidate
        or landing["root"] != root
        or landing["releaseURL"] != github["releaseURL"]
        or landing["landingURL"] != site["landingURL"]
    ):
        raise PublicationError("site landing receipt release facts differ")
    root_data = receipt(site["rootDigestReceipt"], repo, "site root digest receipt")
    if root_data.decode("ascii", errors="strict").strip() != root["sha256"]:
        raise PublicationError("site root digest receipt differs")

    second = exact(record["secondChannel"], {"kind", "locator", "receipt", "rootSHA256"}, "second channel")
    if second["kind"] not in {"dnssec", "transparency"} or second["rootSHA256"] != root["sha256"]:
        raise PublicationError("second trust channel differs")
    if not isinstance(second["locator"], str) or not second["locator"].strip():
        raise PublicationError("second trust channel locator is absent")
    second_receipt = structured_receipt(
        second["receipt"],
        repo,
        "second trust channel receipt",
        "idc-second-channel-receipt/v1",
        {"kind", "locator", "observedAt", "rootSHA256", "verified"},
    )
    recent_timestamp(
        second_receipt["observedAt"], "second trust channel receipt observedAt", current_time
    )
    if (
        second_receipt["kind"] != second["kind"]
        or second_receipt["locator"] != second["locator"]
        or second_receipt["rootSHA256"] != root["sha256"]
        or second_receipt["verified"] is not True
    ):
        raise PublicationError("second trust channel receipt facts differ")
    return {
        "schema": "idc-public-release-verification/v1",
        "pass": True,
        "candidate": candidate,
        "tagObject": local_tag,
        "root": root,
        "assets": len(observed_assets),
        "channels": ["github", "company-site", second["kind"]],
        "authority": "externally-pinned-signed-publication-observation",
        "observerFamily": observer["family"],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--git-sha256", required=True)
    parser.add_argument("--canonical-repository", required=True)
    parser.add_argument("--site-host", required=True)
    parser.add_argument("--trusted-root", required=True, type=Path)
    parser.add_argument("--trusted-root-sha256", required=True)
    parser.add_argument("--ssh-keygen", required=True, type=Path)
    parser.add_argument("--ssh-keygen-sha256", required=True)
    parser.add_argument("--observer-authority", required=True, type=Path)
    parser.add_argument("--observer-authority-sha256", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(
            args.record,
            args.repo_root,
            args.git,
            args.git_sha256,
            args.canonical_repository,
            args.site_host,
            trusted_root=args.trusted_root,
            trusted_root_sha256=args.trusted_root_sha256,
            ssh_keygen=args.ssh_keygen,
            ssh_keygen_sha256=args.ssh_keygen_sha256,
            observer_authority=args.observer_authority,
            observer_authority_sha256=args.observer_authority_sha256,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, PublicationError) as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"PUBLIC RELEASE REFUSED - {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2) if args.json else "PUBLIC RELEASE OK - canonical assets and independent trust channels agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
