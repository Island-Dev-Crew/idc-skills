#!/usr/bin/env python3
"""Run the Forge-50 registry, semantic, provenance, and protocol closure gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence


REPO = Path(__file__).resolve().parents[1]


class ForgeClosureError(RuntimeError):
    pass


def run(*arguments: str) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        [sys.executable, "-I", "-B", *arguments],
        cwd=REPO,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise ForgeClosureError(
            f"{' '.join(arguments)} failed: {(process.stderr or process.stdout).strip()}"
        )
    return process


def verify() -> dict[str, Any]:
    validation = run(str(REPO / "scripts/validate_skills.py"), "--json")
    value = json.loads(validation.stdout)
    summary = value.get("summary", {})
    if not value.get("valid") or summary.get("skillsLoaded") != 50 or summary.get("errors") != 0:
        raise ForgeClosureError("canonical validation did not prove 50/50 with zero errors")
    run(str(REPO / "scripts/verify_validation_records.py"))
    provenance = run(str(REPO / "scripts/verify_provenance.py"))
    provenance_report = json.loads(provenance.stdout)
    protocol = run(
        str(REPO / "skills/archipelago/protocol/scripts/validate_contracts.py")
    )
    protocol_passes = sum(
        line.startswith("[PASS]") for line in protocol.stdout.splitlines()
    )
    if protocol_passes != 5:
        raise ForgeClosureError("vendored Archipelago examples did not pass five contracts")
    return {
        "schema": "idc-forge-50-closure/v1",
        "pass": True,
        "skills": 50,
        "validationErrors": 0,
        "compatibilityAdvisories": summary.get("warnings"),
        "semanticRecords": 50,
        "provenance": provenance_report,
        "vendoredProtocolContracts": protocol_passes,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        report = verify()
    except (ForgeClosureError, json.JSONDecodeError) as exc:
        if args.json:
            print(json.dumps({"pass": False, "error": str(exc)}, sort_keys=True))
        else:
            print(f"FORGE 50 REFUSED - {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        print("FORGE 50 OK - registry+records+provenance+protocol")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
