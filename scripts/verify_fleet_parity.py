#!/usr/bin/env python3
"""Verify all four installed Forge roots against one authenticated manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

try:
    from . import skill_integrity, verify_provenance
except ImportError:
    import skill_integrity  # type: ignore[no-redef]
    import verify_provenance  # type: ignore[no-redef]


HANDOFF_ENV = "IDC_SKILLS_FRESHNESS_HANDOFF"
SSH_KEYGEN_ENV = "IDC_SKILLS_SSH_KEYGEN"
SSH_KEYGEN_SHA256_ENV = "IDC_SKILLS_SSH_KEYGEN_SHA256"
ROOT_LABELS = ("agents", "claude", "pi", "hermes")
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")
COMMIT_RE = re.compile(r"[0-9a-f]{40}\Z")
RELEASE_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?\Z")
PARITY_CONTEXT_ENV = {
    "gitCommit": "IDC_SKILLS_PARITY_GIT_COMMIT",
    "gitTag": "IDC_SKILLS_PARITY_GIT_TAG",
    "gitTree": "IDC_SKILLS_PARITY_GIT_TREE",
    "indexSHA256": "IDC_SKILLS_PARITY_INDEX_SHA256",
    "installInventorySHA256": "IDC_SKILLS_PARITY_INSTALL_INVENTORY_SHA256",
    "manifestSHA256": "IDC_SKILLS_PARITY_MANIFEST_SHA256",
    "release": "IDC_SKILLS_PARITY_RELEASE",
}


class FleetParityError(RuntimeError):
    pass


def default_roots() -> dict[str, Path]:
    home = Path.home()
    return {
        "agents": home / ".agents/skills",
        "claude": home / ".claude/skills",
        "pi": home / ".pi/agent/skills",
        "hermes": home / ".hermes/skills",
    }


def parse_roots(values: Sequence[str]) -> dict[str, Path]:
    if not values:
        return default_roots()
    roots: dict[str, Path] = {}
    for value in values:
        if "=" not in value:
            raise FleetParityError("--root must use label=/absolute/path")
        label, raw = value.split("=", 1)
        path = Path(raw)
        if label not in ROOT_LABELS or label in roots or not path.is_absolute():
            raise FleetParityError("roots must uniquely cover known labels with absolute paths")
        roots[label] = path
    if set(roots) != set(ROOT_LABELS):
        raise FleetParityError("roots must cover agents, claude, pi, and hermes")
    return roots


def parse_release_context(
    environment: Mapping[str, str], freshness_handoff: str
) -> dict[str, str]:
    context = {key: environment.get(variable, "") for key, variable in PARITY_CONTEXT_ENV.items()}
    if (
        COMMIT_RE.fullmatch(context["gitCommit"]) is None
        or COMMIT_RE.fullmatch(context["gitTree"]) is None
        or RELEASE_RE.fullmatch(context["release"]) is None
        or context["gitTag"] != context["release"]
        or any(
            SHA256_RE.fullmatch(context[field]) is None
            for field in (
                "indexSHA256",
                "installInventorySHA256",
                "manifestSHA256",
            )
        )
    ):
        raise FleetParityError("authenticated fleet-parity release context is invalid")
    if freshness_handoff != context["indexSHA256"]:
        raise FleetParityError("freshness handoff differs from the release-index digest")
    return context


def _file_identity(path: Path) -> tuple[int, int]:
    try:
        metadata = path.stat()
    except OSError as exc:
        raise FleetParityError(f"physical path identity is unavailable: {path}") from exc
    return metadata.st_dev, metadata.st_ino


def _physically_contains(container: Path, member: Path) -> bool:
    container_identity = _file_identity(container)
    current = member
    while True:
        if _file_identity(current) == container_identity:
            return True
        parent = current.parent
        if parent == current:
            return False
        current = parent


def validate_physical_roots(
    repo_root: Path, roots: Mapping[str, Path]
) -> dict[str, Path]:
    try:
        repository = repo_root.resolve(strict=True)
    except OSError as exc:
        raise FleetParityError("candidate repository root is unavailable") from exc
    resolved: dict[str, Path] = {}
    identities: dict[tuple[int, int], str] = {}
    for label in ROOT_LABELS:
        root = roots[label]
        if not root.is_absolute():
            raise FleetParityError(f"{label} root must be absolute")
        try:
            metadata = root.lstat()
            physical = root.resolve(strict=True)
            physical_metadata = physical.stat()
        except OSError as exc:
            raise FleetParityError(f"{label} root is unavailable: {root}") from exc
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
            raise FleetParityError(f"{label} root is absent or symlinked: {root}")
        if _physically_contains(repository, physical) or _physically_contains(
            physical, repository
        ):
            raise FleetParityError(
                f"{label} root must remain outside the candidate repository"
            )
        identity = (physical_metadata.st_dev, physical_metadata.st_ino)
        if identity in identities:
            raise FleetParityError(
                "fleet roots must be physically distinct: "
                f"{identities[identity]} and {label} resolve to {physical}"
            )
        identities[identity] = label
        resolved[label] = physical
    for index, first_label in enumerate(ROOT_LABELS):
        for second_label in ROOT_LABELS[index + 1 :]:
            first = resolved[first_label]
            second = resolved[second_label]
            if _physically_contains(first, second) or _physically_contains(second, first):
                raise FleetParityError(
                    "fleet roots must be physically distinct and non-overlapping: "
                    f"{first_label}={first} {second_label}={second}"
                )
    return resolved


def verify_roots(
    repo_root: Path,
    roots: Mapping[str, Path],
    authenticated_report: Mapping[str, Any],
    release_context: Mapping[str, str],
) -> dict[str, Any]:
    report = dict(authenticated_report)
    manifest = report.pop("_verifiedManifest", None)
    if not (
        report.get("contentReady") is True
        and report.get("profile") == "release"
        and report.get("score") == "5/5"
        and isinstance(manifest, dict)
    ):
        raise FleetParityError("authenticated release manifest is unavailable")
    skills = manifest.get("skills")
    names = manifest.get("skillNames")
    if not isinstance(skills, dict) or not isinstance(names, list) or len(names) != 50:
        raise FleetParityError("authenticated manifest does not cover exactly 50 skills")
    if names != sorted(skills) or len(set(names)) != 50:
        raise FleetParityError("authenticated skill inventory is not unique and canonical")
    if set(roots) != set(ROOT_LABELS):
        raise FleetParityError("four canonical root labels are required")
    physical_roots = validate_physical_roots(repo_root, roots)
    if (
        release_context.get("release") != manifest.get("release")
        or COMMIT_RE.fullmatch(release_context.get("gitCommit", "")) is None
        or COMMIT_RE.fullmatch(release_context.get("gitTree", "")) is None
        or release_context.get("gitTag") != manifest.get("release")
        or any(
            SHA256_RE.fullmatch(release_context.get(field, "")) is None
            for field in (
                "indexSHA256",
                "installInventorySHA256",
                "manifestSHA256",
            )
        )
    ):
        raise FleetParityError("fleet parity context differs from authenticated manifest")

    root_reports: list[dict[str, Any]] = []
    for label in ROOT_LABELS:
        root = physical_roots[label]
        observed: list[str] = []
        for path in root.iterdir():
            try:
                metadata = path.lstat()
            except OSError as exc:
                raise FleetParityError(f"{label} inventory could not be read: {path}") from exc
            if stat.S_ISLNK(metadata.st_mode):
                raise FleetParityError(f"{label} inventory contains a symlink entry: {path.name}")
            if not stat.S_ISDIR(metadata.st_mode):
                raise FleetParityError(
                    f"{label} inventory contains a non-directory entry: {path.name}"
                )
            observed.append(path.name)
        observed.sort()
        if observed != names:
            missing = sorted(set(names) - set(observed))
            extra = sorted(set(observed) - set(names))
            raise FleetParityError(f"{label} inventory differs: missing={missing} extra={extra}")
        for name in names:
            failures = skill_integrity.verify_skill_directory(
                root / name, skills[name].get("files", {})
            )
            if failures:
                raise FleetParityError(f"{label}/{name} parity failed: {'; '.join(failures)}")
        root_reports.append(
            {
                "label": label,
                "path": str(root.resolve()),
                "skills": len(names),
                "bytes": "exact",
                "posixMode": "physical" if os.name != "nt" else "authenticated-intent",
                "loaderSidecars": "included-in-signed-file-map",
            }
        )
    provenance_report = verify_provenance.verify()
    return {
        "schema": "idc-fleet-parity-report/v1",
        "pass": True,
        "authority": "observation-only",
        "readyToRun": False,
        "requiresExternalFreshnessReceipt": True,
        "release": manifest.get("release"),
        "manifestSequence": manifest.get("manifestSequence"),
        "candidate": {
            "commit": release_context["gitCommit"],
            "tag": release_context["gitTag"],
            "tree": release_context["gitTree"],
        },
        "indexSHA256": release_context["indexSHA256"],
        "installInventorySHA256": release_context["installInventorySHA256"],
        "manifestSHA256": release_context["manifestSHA256"],
        "skillsPerRoot": 50,
        "roots": root_reports,
        "provenance": provenance_report,
        "sameUidResidual": "installed user-owned roots require OS/admin isolation for hostile same-UID resistance",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--root", action="append", default=[], help="label=/absolute/path; repeat four times")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        handoff = os.environ.get(HANDOFF_ENV, "")
        if SHA256_RE.fullmatch(handoff) is None:
            raise FleetParityError("invoke fleet parity through the external freshness launcher")
        roots = parse_roots(args.root)
        release_context = parse_release_context(os.environ, handoff)
        integrity = skill_integrity.verify_repository(
            args.repo_root,
            ssh_keygen=os.environ.get(SSH_KEYGEN_ENV),
            ssh_keygen_sha256=os.environ.get(SSH_KEYGEN_SHA256_ENV),
            include_verified_manifest=True,
        )
        report = verify_roots(args.repo_root, roots, integrity, release_context)
    except (OSError, FleetParityError, verify_provenance.ProvenanceError) as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"FLEET PARITY REFUSED - {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(
            "FLEET PARITY OBSERVATION OK - "
            f"4 roots x {report['skillsPerRoot']} skills; "
            "capture through the external freshness authority"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
