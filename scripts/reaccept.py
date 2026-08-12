#!/usr/bin/env python3
"""Fresh-clone acceptance gate for the Forge tooling and all fifty skills."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"

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
    before = tree_manifest(REPO_ROOT / "skills").sha256

    _python("verify_harness_support.py")
    _python("verify_gauntlet_records.py")
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

        _python("install.py", "install", *target_args, "--json")
        _python("install.py", "install", *target_args, "--verify-only", "--json")

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
        "REACCEPTED skills=50/50 tests=green nativeTargets=4x50 "
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
