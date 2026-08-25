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
import errno
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
SSH_KEYGEN_ENV = "IDC_SKILLS_SSH_KEYGEN"
SSH_KEYGEN_SHA256_ENV = "IDC_SKILLS_SSH_KEYGEN_SHA256"
SHA256_RE = re.compile(r"sha256:[0-9a-f]{64}\Z")


def _skill_from_payload(payload: Mapping[str, Any]) -> str | None:
    containers: list[tuple[str, Mapping[str, Any]]] = [("payload", payload)]
    for key in ("tool_input", "toolInput", "input"):
        if key not in payload:
            continue
        value = payload[key]
        if not isinstance(value, dict):
            raise ValueError(f"hook payload container {key!r} must be an object")
        containers.append((key, value))
    representations: list[tuple[str, str]] = []
    for container_name, container in containers:
        for key in ("skill", "skill_name", "skillName", "name"):
            if key not in container:
                continue
            value = container[key]
            if not isinstance(value, str) or SKILL_NAME_RE.fullmatch(value.strip()) is None:
                raise ValueError(
                    f"hook payload skill representation {container_name}.{key} is invalid"
                )
            representations.append((f"{container_name}.{key}", value.strip()))
    if not representations:
        return None
    names = {value for _, value in representations}
    if len(names) != 1:
        detail = ", ".join(f"{location}={value!r}" for location, value in representations)
        raise ValueError(f"conflicting hook skill representations: {detail}")
    if len(representations) != 1:
        detail = ", ".join(location for location, _ in representations)
        raise ValueError(f"duplicate hook skill representations: {detail}")
    return representations[0][1]


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in hook input: {key}")
        result[key] = value
    return result


def _read_payload() -> dict[str, Any]:
    raw = sys.stdin.buffer.read(MAX_HOOK_INPUT + 1)
    if len(raw) > MAX_HOOK_INPUT:
        raise ValueError("hook input exceeds 1 MiB")
    if not raw.strip():
        return {}
    value = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique_object)
    if not isinstance(value, dict):
        raise ValueError("hook input must be a JSON object")
    return value


def _write_stderr(message: str) -> None:
    """Write without TextIO buffering so a closed hook pipe cannot rewrite exit 2."""

    try:
        descriptor = sys.stderr.fileno()
    except (AttributeError, OSError, ValueError):
        try:
            sys.stderr.write(message + "\n")
        except (BrokenPipeError, OSError, ValueError):
            pass
        return
    try:
        os.write(descriptor, (message + "\n").encode("ascii", errors="replace"))
    except OSError as exc:
        if not isinstance(exc, BrokenPipeError) and exc.errno not in {errno.EBADF, errno.EPIPE}:
            return
        try:
            null_fd = os.open(os.devnull, os.O_WRONLY)
            os.dup2(null_fd, 2)
            os.close(null_fd)
        except OSError:
            pass


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
        _write_stderr(
            "SKILL BLOCKED - invoke this hook through the external idc-verify-fresh launcher"
        )
        return 2
    payload = _read_payload()
    report = skill_integrity.verify_repository(
        args.repo_root,
        ssh_keygen=os.environ.get(SSH_KEYGEN_ENV),
        ssh_keygen_sha256=os.environ.get(SSH_KEYGEN_SHA256_ENV),
        include_verified_manifest=True,
    )
    manifest = report.pop("_verifiedManifest", None)
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    if not (
        report.get("contentReady") is True
        and report.get("profile") == "release"
        and report.get("score") == "5/5"
    ):
        _write_stderr(f"SKILL BLOCKED - content gate is {report['score']}")
        return 2

    payload_skill = _skill_from_payload(payload)
    if args.skill and payload_skill:
        relation = "conflict" if args.skill != payload_skill else "duplicate"
        _write_stderr(
            f"SKILL BLOCKED - explicit skill and hook payload {relation}; "
            "exactly one identity representation is required"
        )
        return 2
    skill_name = args.skill or payload_skill
    if not skill_name:
        _write_stderr("SKILL BLOCKED - hook payload did not identify a skill")
        return 2
    try:
        if not isinstance(manifest, dict):
            raise skill_integrity.IntegrityError("authenticated manifest snapshot unavailable")
        expected = manifest["skills"][skill_name]["files"]
    except (KeyError, skill_integrity.IntegrityError) as exc:
        _write_stderr(
            f"SKILL BLOCKED - unknown or unreadable skill {skill_name!r}: {exc}"
        )
        return 2
    failures = skill_integrity.verify_skill_directory(
        args.installed_skills / skill_name, expected
    )
    if failures:
        _write_stderr(
            f"SKILL BLOCKED - installed bytes drifted for {skill_name}: "
            + "; ".join(failures)
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
        _write_stderr("SKILL BLOCKED - integrity adapter failure: " + type(exc).__name__)
        return 2


if __name__ == "__main__":
    try:
        result = main()
    except BaseException:
        result = 2
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.flush()
        except BaseException:
            pass
    # Avoid Python's shutdown flush rewriting a deliberate blocking exit 2 to
    # interpreter-specific 120 when the hook transport closes a pipe.
    os._exit(result)
