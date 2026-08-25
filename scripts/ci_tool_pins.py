#!/usr/bin/env python3
"""Export exact OpenSSH tool identity for content-only CI reacceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path


class PinError(RuntimeError):
    pass


def tool_record(value: Path | None) -> tuple[Path, str]:
    discovered = shutil.which("ssh-keygen") if value is None else None
    if value is None and discovered is None:
        raise PinError("ssh-keygen is unavailable")
    candidate = value if value is not None else Path(discovered or "")
    try:
        resolved = candidate.resolve(strict=True)
        metadata = resolved.stat()
    except OSError as exc:
        raise PinError(f"cannot resolve ssh-keygen: {exc}") from exc
    if (
        not resolved.is_absolute()
        or not stat.S_ISREG(metadata.st_mode)
        or not os.access(resolved, os.X_OK)
    ):
        raise PinError("ssh-keygen must resolve to an absolute executable regular file")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return resolved, "sha256:" + digest.hexdigest()


def append_github_env(path: Path, tool: Path, digest: str) -> None:
    if not path.is_absolute() or "\n" in str(tool) or "\r" in str(tool):
        raise PinError("GITHUB_ENV and tool paths must be absolute single-line values")
    if path.is_symlink():
        raise PinError("GITHUB_ENV must not be a symlink")
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_CLOEXEC", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PinError("GITHUB_ENV must be a regular file")
        payload = (
            f"IDC_SKILLS_SSH_KEYGEN={tool}\n"
            f"IDC_SKILLS_SSH_KEYGEN_SHA256={digest}\n"
        ).encode("utf-8")
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument(
        "--github-env",
        type=Path,
        default=Path(os.environ.get("GITHUB_ENV", "")),
    )
    parser.add_argument("--ssh-keygen", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    try:
        tool, digest = tool_record(args.ssh_keygen)
        append_github_env(args.github_env, tool, digest)
    except (OSError, PinError) as exc:
        print(f"CI TOOL PIN REFUSED - {exc}", file=sys.stderr)
        return 2
    report = {"path": str(tool), "sha256": digest}
    print(json.dumps(report, sort_keys=True) if args.json else f"PINNED ssh-keygen {digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
