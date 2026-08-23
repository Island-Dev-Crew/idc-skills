#!/usr/bin/env python3
"""Verify external exact-head cross-family and Kimi release receipts."""

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


SCHEMA = "idc-release-reviews/v1"
RECEIPT_SCHEMA = "idc-independent-review-receipt/v1"
KINDS = ("cross-family", "kimi-k3")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_RECORD = 256 * 1024
MAX_RECEIPT = 32 * 1024 * 1024


class ReviewError(RuntimeError):
    pass


def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ReviewError(f"duplicate JSON key: {key}")
        value[key] = item
    return value


def exact(value: Any, keys: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict) or set(value) != keys:
        raise ReviewError(f"{label} fields differ")
    return value


def snapshot(path: Path, label: str, ceiling: int) -> bytes:
    if not path.is_absolute() or path.is_symlink():
        raise ReviewError(f"{label} must be an absolute non-symlink file")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > ceiling:
        raise ReviewError(f"{label} must be a bounded regular file")
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
        raise ReviewError(f"{label} changed during capture")
    return data


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def outside(path: Path, repo: Path, label: str) -> None:
    try:
        path.resolve(strict=True).relative_to(repo)
    except ValueError:
        return
    raise ReviewError(f"{label} must remain outside the candidate repository")


def git_run(git: Path, repo: Path, *arguments: str, expected: tuple[int, ...] = (0,)) -> str:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "LC_ALL": "C",
        "PATH": str(git.parent),
    }
    process = subprocess.run(
        [str(git), "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null", *arguments],
        text=True,
        capture_output=True,
        check=False,
        env=environment,
    )
    if process.returncode not in expected:
        raise ReviewError(f"Git command failed: {' '.join(arguments)}")
    return process.stdout.strip()


def timestamp(value: Any, label: str) -> None:
    if not isinstance(value, str):
        raise ReviewError(f"{label} must be a timestamp")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ReviewError(f"{label} must be a timestamp") from exc
    if parsed.tzinfo is None:
        raise ReviewError(f"{label} must include a timezone")


def verify(record_path: Path, repo: Path, git: Path, git_sha256: str) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    outside(record_path, repo, "review record")
    if not git.is_absolute() or not os.access(git, os.X_OK):
        raise ReviewError("Git must be an absolute executable")
    git_bytes = snapshot(git, "Git executable", 128 * 1024 * 1024)
    if not SHA256.fullmatch(git_sha256) or digest(git_bytes) != git_sha256:
        raise ReviewError("Git executable digest differs")
    record_data = snapshot(record_path, "review record", MAX_RECORD)
    record = json.loads(record_data, object_pairs_hook=reject_duplicates)
    exact(record, {"schema", "candidate", "evidencePacket", "reviews"}, "review record")
    if record["schema"] != SCHEMA:
        raise ReviewError("review record schema differs")
    candidate = exact(record["candidate"], {"base", "commit", "tree"}, "candidate")
    for field in ("base", "commit", "tree"):
        if not isinstance(candidate[field], str) or not HEX40.fullmatch(candidate[field]):
            raise ReviewError(f"candidate {field} differs")
    head = git_run(git, repo, "rev-parse", "--verify", "HEAD^{commit}")
    tree = git_run(git, repo, "rev-parse", "--verify", "HEAD^{tree}")
    if head != candidate["commit"] or tree != candidate["tree"]:
        raise ReviewError("candidate head or tree moved after review")
    if git_run(git, repo, "status", "--porcelain=v1", "--untracked-files=all"):
        raise ReviewError("candidate repository is dirty")
    base = git_run(git, repo, "rev-parse", "--verify", f"{candidate['base']}^{{commit}}")
    if base != candidate["base"]:
        raise ReviewError("review base does not resolve exactly")
    git_run(git, repo, "diff", "--quiet", f"{base}...{head}", expected=(1,))

    packet = exact(record["evidencePacket"], {"path", "sha256", "size"}, "evidence packet")
    packet_path = Path(packet["path"])
    outside(packet_path, repo, "evidence packet")
    packet_data = snapshot(packet_path, "evidence packet", MAX_RECEIPT)
    if packet["sha256"] != digest(packet_data) or packet["size"] != len(packet_data):
        raise ReviewError("evidence packet bytes differ")

    reviews = record["reviews"]
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise ReviewError("exactly two independent review records are required")
    observed: dict[str, Mapping[str, Any]] = {}
    receipts: set[tuple[str, str]] = set()
    reviewers: set[str] = set()
    families: set[str] = set()
    for index, item in enumerate(reviews):
        review = exact(
            item,
            {"candidate", "findings", "kind", "receipt", "reviewedAt", "reviewer", "verdict", "voidOnMove"},
            f"review[{index}]",
        )
        kind = review["kind"]
        if kind not in KINDS or kind in observed:
            raise ReviewError("review kinds must uniquely cover cross-family and kimi-k3")
        if review["candidate"] != candidate or review["verdict"] != "approve" or review["voidOnMove"] is not True:
            raise ReviewError(f"{kind} did not approve this exact movable head")
        timestamp(review["reviewedAt"], f"{kind}.reviewedAt")
        reviewer = exact(review["reviewer"], {"family", "model", "name"}, f"{kind}.reviewer")
        if not all(isinstance(reviewer[field], str) and reviewer[field].strip() for field in reviewer):
            raise ReviewError(f"{kind} reviewer identity is incomplete")
        if reviewer["family"].strip().lower() == "openai":
            raise ReviewError(f"{kind} reviewer is not cross-family from the OpenAI author seat")
        reviewer_name = reviewer["name"].strip().casefold()
        reviewer_family = reviewer["family"].strip().casefold()
        if reviewer_name in reviewers:
            raise ReviewError("reviewer seats must be distinct")
        if reviewer_family in families:
            raise ReviewError("reviewer families must be distinct")
        reviewers.add(reviewer_name)
        families.add(reviewer_family)
        findings = exact(review["findings"], {"blockers", "critical", "high", "low", "medium"}, f"{kind}.findings")
        if any(type(findings[field]) is not int or findings[field] < 0 for field in findings):
            raise ReviewError(f"{kind} finding counts are invalid")
        if findings["blockers"] != 0 or findings["critical"] != 0 or findings["high"] != 0:
            raise ReviewError(f"{kind} has unresolved release blockers")
        receipt = exact(review["receipt"], {"path", "sha256", "size"}, f"{kind}.receipt")
        path = Path(receipt["path"])
        outside(path, repo, f"{kind} receipt")
        data = snapshot(path, f"{kind} receipt", MAX_RECEIPT)
        if receipt["sha256"] != digest(data) or receipt["size"] != len(data):
            raise ReviewError(f"{kind} receipt bytes differ")
        receipt_payload = json.loads(data, object_pairs_hook=reject_duplicates)
        exact(
            receipt_payload,
            {
                "candidate",
                "evidencePacketSHA256",
                "findings",
                "kind",
                "limitations",
                "reviewedAt",
                "reviewer",
                "schema",
                "verdict",
                "voidOnMove",
            },
            f"{kind} receipt payload",
        )
        if receipt_payload["schema"] != RECEIPT_SCHEMA:
            raise ReviewError(f"{kind} receipt schema differs")
        limitations = receipt_payload["limitations"]
        if not isinstance(limitations, list) or any(not isinstance(item, str) or not item.strip() for item in limitations):
            raise ReviewError(f"{kind} receipt limitations differ")
        expected_payload = {
            "candidate": candidate,
            "evidencePacketSHA256": packet["sha256"],
            "findings": findings,
            "kind": kind,
            "reviewedAt": review["reviewedAt"],
            "reviewer": reviewer,
            "verdict": review["verdict"],
            "voidOnMove": review["voidOnMove"],
        }
        for field, expected in expected_payload.items():
            if receipt_payload[field] != expected:
                raise ReviewError(f"{kind} receipt {field} differs")
        identity = (str(path.resolve()), receipt["sha256"])
        if identity in receipts:
            raise ReviewError("review receipts must be distinct")
        receipts.add(identity)
        observed[kind] = review
    if set(observed) != set(KINDS):
        raise ReviewError("review kinds are incomplete")
    return {
        "schema": "idc-release-review-verification/v1",
        "pass": True,
        "candidate": candidate,
        "reviews": sorted(observed),
        "evidencePacket": packet["sha256"],
        "receipts": len(receipts),
        "authority": "external-review-receipts",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--git-sha256", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(args.record, args.repo_root, args.git, args.git_sha256)
    except (OSError, UnicodeError, json.JSONDecodeError, ReviewError) as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"RELEASE REVIEWS REFUSED - {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, indent=2) if args.json else "RELEASE REVIEWS OK - 2 external exact-head approvals")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
