#!/usr/bin/env python3
"""Verify externally captured GitHub, site, and second-channel release facts."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence
from urllib.parse import urlparse


SCHEMA = "idc-public-release-evidence/v1"
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


def timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise PublicationError(f"{label} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PublicationError(f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None:
        raise PublicationError(f"{label} must include a timezone")


def https(value: Any, label: str, expected_host: str | None = None) -> str:
    if not isinstance(value, str):
        raise PublicationError(f"{label} must be HTTPS")
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.params
        or parsed.fragment
    ):
        raise PublicationError(f"{label} must be credential-free HTTPS")
    if expected_host and parsed.hostname.lower() != expected_host.lower():
        raise PublicationError(f"{label} host differs")
    return parsed.hostname.lower()


def git_run(git: Path, repo: Path, *arguments: str) -> str:
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
    )
    if process.returncode != 0:
        raise PublicationError(f"Git command failed: {' '.join(arguments)}")
    return process.stdout.strip()


def release_payload(data: bytes) -> Mapping[str, Any]:
    envelope = json.loads(data, object_pairs_hook=reject_duplicates)
    exact(envelope, {"signatures", "signed"}, "release statement envelope")
    signed = exact(envelope["signed"], {"_type", "artifacts", "expires", "git", "release", "releaseSequence", "rootVersion", "schema"}, "release statement")
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
) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    outside(record_path, repo, "publication record")
    if not git.is_absolute() or not os.access(git, os.X_OK):
        raise PublicationError("Git must be an absolute executable")
    if not SHA256.fullmatch(git_sha256) or digest(snapshot(git, "Git executable", 128 * 1024 * 1024)) != git_sha256:
        raise PublicationError("Git executable digest differs")
    record = json.loads(snapshot(record_path, "publication record", MAX_RECORD), object_pairs_hook=reject_duplicates)
    exact(record, {"candidate", "github", "root", "schema", "secondChannel", "site", "threshold"}, "publication record")
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

    root = exact(record["root"], {"sha256", "version"}, "root")
    if type(root["version"]) is not int or root["version"] < 1 or not SHA256.fullmatch(root["sha256"]):
        raise PublicationError("root record differs")
    threshold = exact(record["threshold"], {"releaseStatement", "verificationReceipt"}, "threshold")
    statement_data = receipt(threshold["releaseStatement"], repo, "release statement")
    signed = release_payload(statement_data)
    if signed["release"] != candidate["tag"] or signed["rootVersion"] != root["version"] or signed["git"] != candidate:
        raise PublicationError("threshold release statement candidate differs")
    threshold_receipt = structured_receipt(
        threshold["verificationReceipt"],
        repo,
        "threshold verification receipt",
        "idc-threshold-verification-receipt/v1",
        {"candidate", "externalTrustVerified", "root", "statementSHA256", "verifiedAt"},
    )
    timestamp(threshold_receipt["verifiedAt"], "threshold verification receipt verifiedAt")
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
    timestamp(release_receipt["observedAt"], "GitHub release receipt observedAt")
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
    timestamp(tag_receipt["observedAt"], "tag verification receipt observedAt")
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
    timestamp(administration["attestedAt"], "site administration receipt attestedAt")
    if (
        administration["independent"] is not True
        or not isinstance(administration["githubAdministration"], str)
        or not isinstance(administration["siteAdministration"], str)
        or not administration["githubAdministration"].strip()
        or not administration["siteAdministration"].strip()
        or administration["githubAdministration"].strip().casefold() == administration["siteAdministration"].strip().casefold()
    ):
        raise PublicationError("site administration separation differs")
    landing_data = receipt(site["landingReceipt"], repo, "site landing receipt")
    try:
        landing_text = landing_data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PublicationError("site landing receipt is not UTF-8") from exc
    required_landing_facts = (candidate["tag"], candidate["commit"], candidate["tree"], root["sha256"], github["releaseURL"])
    if any(fact not in landing_text for fact in required_landing_facts):
        raise PublicationError("site landing receipt omits an exact release fact")
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
    timestamp(second_receipt["observedAt"], "second trust channel receipt observedAt")
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
        "authority": "captured-external-publication-evidence",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--git-sha256", required=True)
    parser.add_argument("--canonical-repository", required=True)
    parser.add_argument("--site-host", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(args.record, args.repo_root, args.git, args.git_sha256, args.canonical_repository, args.site_host)
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
