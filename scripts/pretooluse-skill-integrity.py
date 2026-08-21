#!/usr/bin/env python3
"""PreToolUse adapter that blocks skill invocation unless content is verified.

Configure this only for the harness's Skill tool. The installed skill root is
mandatory: canonical integrity without the bytes the harness will execute is
not sufficient execution authorization. Route this adapter through the
independently installed freshness launcher; the handoff marker below prevents
accidental direct routing but is not itself the security boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

import skill_integrity


SKILL_NAME_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
MAX_HOOK_INPUT = 1024 * 1024
FRESHNESS_HANDOFF_ENV = "IDC_SKILLS_FRESHNESS_HANDOFF"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _skill_from_payload(payload: Mapping[str, Any]) -> str | None:
    containers: list[Mapping[str, Any]] = [payload]
    for key in ("tool_input", "toolInput", "input"):
        value = payload.get(key)
        if isinstance(value, dict):
            containers.append(value)
    for container in containers:
        for key in ("skill", "skill_name", "name"):
            value = container.get(key)
            if isinstance(value, str) and SKILL_NAME_RE.fullmatch(value.strip()):
                return value.strip()
    return None


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT + 1)
    if len(raw) > MAX_HOOK_INPUT:
        raise ValueError("hook input exceeds 1 MiB")
    if not raw.strip():
        return {}
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="verified release repository containing integrity/ and keys/",
    )
    parser.add_argument(
        "--installed-skills",
        type=Path,
        required=True,
        help="mandatory fleet skill root whose selected skill bytes must match the signed manifest",
    )
    parser.add_argument("--skill", help="explicit skill name for smoke tests")
    parser.add_argument("--json", action="store_true", help="emit the integrity report")
    return parser


def _authorize(args: argparse.Namespace) -> int:
    if SHA256_RE.fullmatch(os.environ.get(FRESHNESS_HANDOFF_ENV, "")) is None:
        print(
            "SKILL BLOCKED - invoke this hook through the external idc-verify-fresh launcher",
            file=sys.stderr,
        )
        return 2
    payload = _read_payload()
    report = skill_integrity.verify_repository(
        args.repo_root, include_verified_manifest=True
    )
    manifest = report.pop("_verifiedManifest", None)
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    if not (
        report.get("contentReady") is True
        and report.get("profile") == "release"
        and report.get("score") == "5/5"
    ):
        print(f"SKILL BLOCKED - content gate is {report['score']}", file=sys.stderr)
        return 2

    payload_skill = _skill_from_payload(payload)
    if args.skill and payload_skill and args.skill != payload_skill:
        print(
            "SKILL BLOCKED - explicit skill and hook payload disagree: "
            f"{args.skill!r} != {payload_skill!r}",
            file=sys.stderr,
        )
        return 2
    skill_name = args.skill or payload_skill
    if not skill_name:
        print("SKILL BLOCKED - hook payload did not identify a skill", file=sys.stderr)
        return 2
    try:
        if not isinstance(manifest, dict):
            raise skill_integrity.IntegrityError("authenticated manifest snapshot unavailable")
        expected = manifest["skills"][skill_name]["files"]
    except (KeyError, skill_integrity.IntegrityError) as exc:
        print(
            f"SKILL BLOCKED - unknown or unreadable skill {skill_name!r}: {exc}",
            file=sys.stderr,
        )
        return 2
    failures = skill_integrity.verify_skill_directory(
        args.installed_skills / skill_name, expected
    )
    if failures:
        print(
            f"SKILL BLOCKED - installed bytes drifted for {skill_name}: "
            + "; ".join(failures),
            file=sys.stderr,
        )
        return 2

    print(f"SKILL CONTENT VERIFIED 5/5 - installed skill={skill_name}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return _authorize(args)
    except Exception as exc:
        # A PreToolUse exit 1 may be treated as non-blocking by the receiving
        # harness. Every unexpected adapter failure must therefore collapse to
        # the documented blocking exit 2, without an authorization result.
        print(
            "SKILL BLOCKED - integrity adapter failure: " + type(exc).__name__,
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
