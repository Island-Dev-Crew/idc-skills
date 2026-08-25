#!/usr/bin/env python3
"""Verify external exact-head cross-family and Kimi release receipts."""

from __future__ import annotations

import argparse
import base64
import binascii
import datetime as dt
import hashlib
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Mapping, Sequence


SCHEMA = "idc-release-reviews/v2"
RECEIPT_SCHEMA = "idc-independent-review-receipt/v2"
RECEIPT_NAMESPACE = "idc-independent-review-receipt-v2"
KINDS = ("cross-family", "kimi-k3")
REQUIRED_LANES = tuple(f"K3-204-{index}" for index in range(11))
REQUIRED_RECONCILIATIONS = tuple(
    f"K3-203-{index:03d}" for index in range(1, 32)
)
RECONCILIATION_DISPOSITIONS = {
    "accepted-residual",
    "false-positive",
    "fixed",
    "not-reproduced",
}
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
SHA256 = re.compile(r"sha256:[0-9a-f]{64}\Z")
MAX_RECORD = 256 * 1024
MAX_RECEIPT = 32 * 1024 * 1024
MAX_PACKET_FILES = 256
MAX_PACKET_UNCOMPRESSED = 64 * 1024 * 1024


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


def validate_tool(
    path: Path,
    expected_sha256: str,
    repo: Path,
    label: str,
) -> Path:
    if not path.is_absolute() or path.is_symlink():
        raise ReviewError(f"{label} must be an absolute non-symlink executable")
    resolved = path.resolve(strict=True)
    outside(resolved, repo, label)
    metadata = resolved.stat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        raise ReviewError(f"{label} must be a regular executable")
    if os.name != "nt" and metadata.st_nlink != 1 and metadata.st_uid != 0:
        raise ReviewError(
            f"{label} must be single-link unless it is a root-owned system executable"
        )
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise ReviewError(
            f"{label} must be owner-controlled and not group/world writable"
        )
    data = snapshot(resolved, label, 128 * 1024 * 1024)
    if not SHA256.fullmatch(expected_sha256) or digest(data) != expected_sha256:
        raise ReviewError(f"{label} executable digest differs")
    return resolved


def git_run(git: Path, repo: Path, *arguments: str, expected: tuple[int, ...] = (0,)) -> str:
    environment = {
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_NO_REPLACE_OBJECTS": "1",
        "LC_ALL": "C",
        "PATH": str(git.parent),
    }
    try:
        process = subprocess.run(
            [str(git), "-C", str(repo), "-c", "core.autocrlf=false", "-c", "core.hooksPath=/dev/null", *arguments],
            text=True,
            capture_output=True,
            check=False,
            env=environment,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ReviewError(f"Git command could not run: {exc}") from exc
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


def verify_evidence_packet(
    data: bytes, candidate: Mapping[str, Any]
) -> tuple[int, set[str]]:
    try:
        archive = zipfile.ZipFile(io.BytesIO(data), "r")
    except zipfile.BadZipFile as exc:
        raise ReviewError("evidence packet ZIP is invalid") from exc
    observed: dict[str, bytes] = {}
    total = 0
    with archive:
        infos = archive.infolist()
        if not 2 <= len(infos) <= MAX_PACKET_FILES:
            raise ReviewError("evidence packet ZIP file count differs")
        for info in infos:
            name = info.filename
            path = PurePosixPath(name)
            mode = (info.external_attr >> 16) & 0o170000
            if (
                not name
                or "\\" in name
                or path.is_absolute()
                or any(part in {"", ".", ".."} for part in path.parts)
                or info.is_dir()
                or mode == stat.S_IFLNK
                or name in observed
                or info.flag_bits & 0x1
            ):
                raise ReviewError("evidence packet ZIP contains an unsafe or duplicate entry")
            if info.file_size > MAX_RECEIPT:
                raise ReviewError("evidence packet ZIP entry exceeds its size ceiling")
            if info.file_size and (
                info.compress_size == 0 or info.file_size > info.compress_size * 100
            ):
                raise ReviewError("evidence packet ZIP compression ratio is unsafe")
            total += info.file_size
            if total > MAX_PACKET_UNCOMPRESSED:
                raise ReviewError("evidence packet ZIP expands beyond its total ceiling")
            try:
                content = archive.read(info)
            except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
                raise ReviewError("evidence packet ZIP entry could not be verified") from exc
            if len(content) != info.file_size:
                raise ReviewError("evidence packet ZIP entry size differs")
            observed[name] = content
    index_data = observed.pop("evidence-index.json", None)
    if index_data is None:
        raise ReviewError("evidence packet ZIP omits evidence-index.json")
    try:
        index = json.loads(index_data, object_pairs_hook=reject_duplicates)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ReviewError("evidence packet ZIP index is invalid JSON") from exc
    exact(
        index,
        {"artifacts", "candidate", "coverage", "generatedAt", "schema"},
        "evidence packet index",
    )
    if index["schema"] != "idc-review-evidence-packet/v2" or index["candidate"] != candidate:
        raise ReviewError("evidence packet ZIP index candidate differs")
    timestamp(index["generatedAt"], "evidence packet index generatedAt")
    packet_coverage = exact(
        index["coverage"],
        {"lanes", "reconciliations"},
        "evidence packet coverage",
    )
    if packet_coverage["lanes"] != list(REQUIRED_LANES):
        raise ReviewError("evidence packet must cover all 11 K3-204 lanes")
    if packet_coverage["reconciliations"] != list(REQUIRED_RECONCILIATIONS):
        raise ReviewError("evidence packet must reconcile all 31 K3-203 findings")
    artifacts = index["artifacts"]
    if not isinstance(artifacts, list) or not artifacts:
        raise ReviewError("evidence packet ZIP artifact index is empty")
    indexed: dict[str, tuple[str, int]] = {}
    for item in artifacts:
        record = exact(item, {"path", "sha256", "size"}, "evidence packet artifact")
        path = record["path"]
        if (
            not isinstance(path, str)
            or path == "evidence-index.json"
            or path in indexed
            or not isinstance(record["sha256"], str)
            or not SHA256.fullmatch(record["sha256"])
            or type(record["size"]) is not int
            or record["size"] < 0
        ):
            raise ReviewError("evidence packet artifact record differs")
        indexed[path] = (record["sha256"], record["size"])
    if set(indexed) != set(observed):
        raise ReviewError("evidence packet ZIP entries differ from its artifact index")
    for name, content in observed.items():
        if indexed[name] != (digest(content), len(content)):
            raise ReviewError(f"evidence packet artifact bytes differ: {name}")
    return len(observed), set(observed)


def verify_review_coverage(
    value: Any,
    packet_artifacts: set[str],
    label: str,
) -> Mapping[str, Any]:
    coverage = exact(value, {"lanes", "reconciliations"}, label)
    lanes = coverage["lanes"]
    if not isinstance(lanes, list) or len(lanes) != len(REQUIRED_LANES):
        raise ReviewError(f"{label} must cover all 11 K3-204 lanes")
    lane_ids: list[str] = []
    for index, item in enumerate(lanes):
        lane = exact(
            item,
            {"evidence", "id", "status"},
            f"{label}.lanes[{index}]",
        )
        lane_id = lane["id"]
        evidence = lane["evidence"]
        if lane["status"] != "complete":
            raise ReviewError(f"{label} lane {lane_id} is not complete")
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(path, str) or path not in packet_artifacts
                for path in evidence
            )
        ):
            raise ReviewError(f"{label} lane {lane_id} evidence is not indexed")
        lane_ids.append(lane_id)
    if lane_ids != list(REQUIRED_LANES):
        raise ReviewError(f"{label} must cover all 11 K3-204 lanes in order")

    reconciliations = coverage["reconciliations"]
    if (
        not isinstance(reconciliations, list)
        or len(reconciliations) != len(REQUIRED_RECONCILIATIONS)
    ):
        raise ReviewError(f"{label} must reconcile all 31 K3-203 findings")
    reconciliation_ids: list[str] = []
    for index, item in enumerate(reconciliations):
        reconciliation = exact(
            item,
            {"disposition", "evidence", "id", "rationale"},
            f"{label}.reconciliations[{index}]",
        )
        finding_id = reconciliation["id"]
        evidence = reconciliation["evidence"]
        if reconciliation["disposition"] not in RECONCILIATION_DISPOSITIONS:
            raise ReviewError(f"{label} finding {finding_id} disposition is not accepted")
        if (
            not isinstance(reconciliation["rationale"], str)
            or not reconciliation["rationale"].strip()
            or not isinstance(evidence, list)
            or not evidence
            or any(
                not isinstance(path, str) or path not in packet_artifacts
                for path in evidence
            )
        ):
            raise ReviewError(f"{label} finding {finding_id} evidence is not indexed")
        reconciliation_ids.append(finding_id)
    if reconciliation_ids != list(REQUIRED_RECONCILIATIONS):
        raise ReviewError(f"{label} must reconcile all 31 K3-203 findings in order")
    return coverage


def allowed_signer_key_id(data: bytes, principal: str, label: str) -> str:
    try:
        lines = [line for line in data.decode("ascii").splitlines() if line.strip()]
    except UnicodeDecodeError as exc:
        raise ReviewError(f"{label} must be canonical ASCII") from exc
    if len(lines) != 1:
        raise ReviewError(f"{label} must contain exactly one signing key")
    parts = lines[0].split()
    if len(parts) != 3 or parts[0] != principal or parts[1] != "ssh-ed25519":
        raise ReviewError(
            f"{label} must be '<principal> ssh-ed25519 <key>' with no options or comment"
        )
    try:
        key_blob = base64.b64decode(parts[2], validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ReviewError(f"{label} key body is not canonical base64") from exc
    if not key_blob or base64.b64encode(key_blob).decode("ascii") != parts[2]:
        raise ReviewError(f"{label} key body is not canonical base64")
    return hashlib.sha256(key_blob).hexdigest()


def load_review_authorities(
    path: Path,
    expected_sha256: str,
    repo: Path,
) -> dict[str, Mapping[str, Any]]:
    outside(path, repo, "review authorities")
    data = snapshot(path, "review authorities", MAX_RECORD)
    if not SHA256.fullmatch(expected_sha256) or digest(data) != expected_sha256:
        raise ReviewError("review authorities digest differs from the external pin")
    value = json.loads(data, object_pairs_hook=reject_duplicates)
    exact(value, {"authorities", "schema"}, "review authorities")
    if value["schema"] != "idc-review-authorities/v1":
        raise ReviewError("review authorities schema differs")
    authorities = value["authorities"]
    if not isinstance(authorities, dict) or set(authorities) != set(KINDS):
        raise ReviewError("review authorities must cover cross-family and kimi-k3")
    parsed: dict[str, Mapping[str, Any]] = {}
    principals: set[str] = set()
    families: set[str] = set()
    signing_keys: set[str] = set()
    for kind in KINDS:
        authority = exact(
            authorities[kind],
            {"allowedSigners", "family", "principal"},
            f"review authority {kind}",
        )
        principal = authority["principal"]
        family = authority["family"]
        if (
            not isinstance(principal, str)
            or not principal.strip()
            or not isinstance(family, str)
            or not family.strip()
            or family.strip().casefold() == "openai"
            or principal in principals
            or family.strip().casefold() in families
        ):
            raise ReviewError("review authority principals and families must be distinct non-OpenAI values")
        allowed = exact(
            authority["allowedSigners"],
            {"path", "sha256", "size"},
            f"review authority {kind} allowed_signers",
        )
        allowed_path = Path(allowed["path"])
        outside(allowed_path, repo, f"review authority {kind} allowed_signers")
        allowed_data = snapshot(
            allowed_path, f"review authority {kind} allowed_signers", MAX_RECEIPT
        )
        if allowed["sha256"] != digest(allowed_data) or allowed["size"] != len(allowed_data):
            raise ReviewError(f"review authority {kind} allowed_signers bytes differ")
        signing_key = allowed_signer_key_id(
            allowed_data,
            principal,
            f"review authority {kind} allowed_signers",
        )
        if signing_key in signing_keys:
            raise ReviewError("review authority signing keys must be disjoint")
        principals.add(principal)
        families.add(family.strip().casefold())
        signing_keys.add(signing_key)
        parsed[kind] = {
            "allowedSigners": allowed_data,
            "family": family.strip().casefold(),
            "principal": principal,
            "signingKeySHA256": signing_key,
        }
    return parsed


def verify_authority_signature(
    data: bytes,
    signature: bytes,
    authority: Mapping[str, Any],
    ssh_keygen: Path,
    kind: str,
) -> None:
    with tempfile.TemporaryDirectory(prefix="idc-review-signature-") as temporary:
        root = Path(temporary)
        allowed_path = root / "allowed_signers"
        signature_path = root / "receipt.sig"
        allowed_path.write_bytes(authority["allowedSigners"])
        signature_path.write_bytes(signature)
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
                RECEIPT_NAMESPACE,
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
    if process.returncode != 0:
        raise ReviewError(f"{kind} receipt authority signature is invalid")


def verify(
    record_path: Path,
    repo: Path,
    git: Path,
    git_sha256: str,
    *,
    authorities_path: Path,
    authorities_sha256: str,
    ssh_keygen: Path,
    ssh_keygen_sha256: str,
) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    outside(record_path, repo, "review record")
    git = validate_tool(git, git_sha256, repo, "Git")
    ssh_keygen = validate_tool(
        ssh_keygen, ssh_keygen_sha256, repo, "ssh-keygen"
    )
    authorities = load_review_authorities(authorities_path, authorities_sha256, repo)
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
    if git_run(git, repo, "ls-files", "--others", "--ignored", "--exclude-standard"):
        raise ReviewError("candidate repository contains an ignored payload")
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
    packet_artifact_count, packet_artifact_paths = verify_evidence_packet(
        packet_data, candidate
    )

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
            {
                "candidate",
                "coverage",
                "findings",
                "kind",
                "receipt",
                "reviewedAt",
                "reviewer",
                "verdict",
                "voidOnMove",
            },
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
        if reviewer["family"].strip().casefold() != authorities[kind]["family"]:
            raise ReviewError(f"{kind} reviewer family differs from the externally pinned authority")
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
        coverage = verify_review_coverage(
            review["coverage"],
            packet_artifact_paths,
            f"{kind} coverage",
        )
        receipt = exact(
            review["receipt"],
            {"path", "sha256", "signature", "size"},
            f"{kind}.receipt",
        )
        path = Path(receipt["path"])
        outside(path, repo, f"{kind} receipt")
        data = snapshot(path, f"{kind} receipt", MAX_RECEIPT)
        if receipt["sha256"] != digest(data) or receipt["size"] != len(data):
            raise ReviewError(f"{kind} receipt bytes differ")
        signature_record = exact(
            receipt["signature"], {"path", "sha256", "size"}, f"{kind}.receipt.signature"
        )
        signature_path = Path(signature_record["path"])
        outside(signature_path, repo, f"{kind} receipt signature")
        signature_data = snapshot(
            signature_path, f"{kind} receipt signature", MAX_RECEIPT
        )
        if (
            signature_record["sha256"] != digest(signature_data)
            or signature_record["size"] != len(signature_data)
        ):
            raise ReviewError(f"{kind} receipt signature bytes differ")
        verify_authority_signature(data, signature_data, authorities[kind], ssh_keygen, kind)
        receipt_payload = json.loads(data, object_pairs_hook=reject_duplicates)
        exact(
            receipt_payload,
            {
                "candidate",
                "coverage",
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
            "coverage": coverage,
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
        "schema": "idc-release-review-verification/v2",
        "pass": True,
        "candidate": candidate,
        "reviews": sorted(observed),
        "evidencePacket": packet["sha256"],
        "evidenceArtifacts": packet_artifact_count,
        "lanes": len(REQUIRED_LANES),
        "reconciliations": len(REQUIRED_RECONCILIATIONS),
        "receipts": len(receipts),
        "authority": "externally-pinned-signed-review-receipts",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("record", type=Path)
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--git", type=Path, required=True)
    parser.add_argument("--git-sha256", required=True)
    parser.add_argument("--review-authorities", required=True, type=Path)
    parser.add_argument("--review-authorities-sha256", required=True)
    parser.add_argument("--ssh-keygen", required=True, type=Path)
    parser.add_argument("--ssh-keygen-sha256", required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify(
            args.record,
            args.repo_root,
            args.git,
            args.git_sha256,
            authorities_path=args.review_authorities,
            authorities_sha256=args.review_authorities_sha256,
            ssh_keygen=args.ssh_keygen,
            ssh_keygen_sha256=args.ssh_keygen_sha256,
        )
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
