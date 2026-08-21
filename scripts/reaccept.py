#!/usr/bin/env python3
"""Fresh-clone content acceptance gate for the Forge tooling and all fifty skills.

Whole-tree freshness is established by the independently installed launcher
that invokes this script. Its handoff marker is routing defense, not the trust
root.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
FRESHNESS_HANDOFF_ENV = "IDC_SKILLS_FRESHNESS_HANDOFF"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")

sys.path.insert(0, str(SCRIPTS))
from install import tree_manifest  # noqa: E402


def _run(args: list[str], *, expected: int = 0) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        args,
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.returncode != expected:
        detail = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(
            f"expected exit {expected}, got {process.returncode}: {' '.join(args)}\n{detail}"
        )
    return process


def _python(script: str, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, "-B", str(SCRIPTS / script), *args], expected=expected)


def main() -> int:
    if SHA256_RE.fullmatch(os.environ.get(FRESHNESS_HANDOFF_ENV, "")) is None:
        raise RuntimeError(
            "reacceptance must be invoked through the external idc-verify-fresh launcher"
        )
    before = tree_manifest(REPO_ROOT / "skills").sha256

    integrity = _python("skill_integrity.py", "verify", "--json")
    integrity_report = json.loads(integrity.stdout)
    if not (
        integrity_report.get("contentReady") is True
        and integrity_report.get("profile") == "release"
        and integrity_report.get("score") == "5/5"
    ):
        raise RuntimeError("signed content gate did not report contentReady=true at 5/5")
    if integrity_report.get("skillsChecked") != 50:
        raise RuntimeError("signed integrity gate did not bind all 50 skills")

    _python("verify_harness_support.py")
    _python("verify_gauntlet_records.py")
    _python("verify_validation_records.py")
    _run(
        [
            sys.executable,
            "-B",
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-p",
            "test_*.py",
        ]
    )

    canonical = _python("validate_skills.py", "--json")
    canonical_report = json.loads(canonical.stdout)
    canonical_summary = canonical_report.get("summary", {})
    if not canonical_report.get("valid"):
        raise RuntimeError("canonical validator did not report valid=true")
    if canonical_summary.get("skillsLoaded") != 50 or canonical_summary.get("errors") != 0:
        raise RuntimeError("canonical validator did not prove 50/50 with zero errors")

    with tempfile.TemporaryDirectory(prefix="idc-forge-reaccept-") as temporary:
        root = Path(temporary)
        targets = [root / name for name in ("agents", "claude", "pi", "hermes")]
        target_args: list[str] = []
        for name, target in zip(("agents", "claude", "pi", "hermes"), targets):
            target_args.extend(["--custom-target", f"probe-{name}={target}"])

        _python("install.py", "install", *target_args, "--verify-integrity", "--json")
        _python(
            "install.py",
            "install",
            *target_args,
            "--verify-integrity",
            "--verify-only",
            "--json",
        )

        snapshot = root / "claude-ai-snapshot"
        _python("install.py", "export-claude-ai-snapshot", "--output", str(snapshot), "--json")
        _python(
            "install.py",
            "export-claude-ai-snapshot",
            "--output",
            str(snapshot),
            "--verify-only",
            "--json",
        )
        archives = sorted(snapshot.glob("*.zip"))
        if len(archives) != 50:
            raise RuntimeError(f"historical snapshot exported {len(archives)} ZIPs, expected 50")

        current = root / "claude-ai-current"
        blocked = _python(
            "install.py",
            "export-claude-ai",
            "--output",
            str(current),
            "--dry-run",
            "--json",
            expected=2,
        )
        blocked_report = json.loads(blocked.stdout)
        blocker = " ".join(blocked_report.get("errors", []))
        if "descriptions over 200 characters (48)" not in blocker:
            raise RuntimeError("current claude.ai gate did not enumerate 48 long descriptions")
        if "user-only invocation cannot be preserved (13)" not in blocker:
            raise RuntimeError("current claude.ai gate did not enumerate 13 user-only skills")
        if current.exists():
            raise RuntimeError("current claude.ai fail-closed probe created output")

    after = tree_manifest(REPO_ROOT / "skills").sha256
    if after != before:
        raise RuntimeError(f"canonical tree drifted during acceptance: {before} -> {after}")

    print(
        "CONTENT-REACCEPTED integrity=5/5 skills=50/50 tests=green nativeTargets=4x50 "
        "snapshotZips=50 currentClaudeAi=blocked(48 descriptions,13 user-only) "
        f"canonicalSha256={after}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, json.JSONDecodeError) as exc:
        print(f"REACCEPTANCE FAILED: {exc}", file=sys.stderr)
        raise SystemExit(1)
