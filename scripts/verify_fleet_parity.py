#!/usr/bin/env python3
"""Verify all four installed Forge roots against one authenticated manifest."""

from __future__ import annotations

import argparse
import json
import os
import re
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


def verify_roots(
    repo_root: Path,
    roots: Mapping[str, Path],
    authenticated_report: Mapping[str, Any],
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

    root_reports: list[dict[str, Any]] = []
    for label in ROOT_LABELS:
        root = roots[label]
        if not root.is_dir() or root.is_symlink():
            raise FleetParityError(f"{label} root is absent or symlinked: {root}")
        observed = sorted(
            path.name for path in root.iterdir() if path.is_dir() and not path.is_symlink()
        )
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
        "release": manifest.get("release"),
        "manifestSequence": manifest.get("manifestSequence"),
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
        if SHA256_RE.fullmatch(os.environ.get(HANDOFF_ENV, "")) is None:
            raise FleetParityError("invoke fleet parity through the external freshness launcher")
        roots = parse_roots(args.root)
        integrity = skill_integrity.verify_repository(
            args.repo_root,
            ssh_keygen=os.environ.get(SSH_KEYGEN_ENV),
            ssh_keygen_sha256=os.environ.get(SSH_KEYGEN_SHA256_ENV),
            include_verified_manifest=True,
        )
        report = verify_roots(args.repo_root, roots, integrity)
    except (OSError, FleetParityError, verify_provenance.ProvenanceError) as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"FLEET PARITY REFUSED - {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print(f"FLEET PARITY OK - 4 roots x {report['skillsPerRoot']} skills")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
