#!/usr/bin/env python3
"""Fail-closed URL and plaintext-secret path validation for wizard.sh."""

from __future__ import annotations

import argparse
import ipaddress
import os
import re
import stat
import subprocess
import sys
import urllib.parse
from pathlib import Path


class SafetyError(RuntimeError):
    pass


def validate_url(value: str) -> tuple[str, str]:
    if not value or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise SafetyError("URL contains empty or control-character input")
    if "\\" in value or any(character.isspace() for character in value):
        raise SafetyError("URL contains a backslash or whitespace")
    try:
        parsed = urllib.parse.urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise SafetyError(f"URL authority or port is invalid: {exc}") from exc
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"} or not parsed.netloc or parsed.hostname is None:
        raise SafetyError("URL must have an HTTP(S) scheme and authority")
    if parsed.username is not None or parsed.password is not None:
        raise SafetyError("URL credentials/userinfo are forbidden")
    host = parsed.hostname.lower()
    if not host.isascii() or host.endswith(".") or "%" in host:
        raise SafetyError("URL host must use canonical ASCII/IDNA form without a trailing dot")
    is_ip = False
    try:
        address = ipaddress.ip_address(host)
        is_ip = True
        canonical_host = address.compressed
    except ValueError:
        labels = host.split(".")
        if any(
            not label
            or len(label) > 63
            or re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label) is None
            for label in labels
        ):
            raise SafetyError("URL hostname has an invalid DNS label")
        try:
            canonical_host = host.encode("ascii").decode("idna").encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise SafetyError("URL hostname has invalid IDNA form") from exc
        if canonical_host != host:
            raise SafetyError("URL hostname is not canonical IDNA ASCII")
    loopback = host == "localhost" or (is_ip and address.is_loopback)
    if scheme == "http" and not loopback:
        raise SafetyError("plain HTTP is allowed only for an exact loopback host")
    if scheme == "https" and port not in {None, 443}:
        raise SafetyError("HTTPS wizard URLs may use only the default port 443")
    display_host = f"[{canonical_host}]" if ":" in canonical_host else canonical_host
    authority = display_host
    if port is not None and not (scheme == "https" and port == 443):
        authority += f":{port}"
    normalized = urllib.parse.urlunsplit(
        (scheme, authority, parsed.path or "/", parsed.query, parsed.fragment)
    )
    return normalized, canonical_host


def _git(git: Path, directory: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(git), "-C", str(directory), "-c", "core.hooksPath=/dev/null", *arguments],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=10,
        env={"LANG": "C", "LC_ALL": "C", "PATH": str(git.parent)},
    )


def validate_env_path(value: str, git_value: str) -> Path:
    candidate = Path(value)
    absolute = Path(os.path.abspath(candidate))
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(metadata.st_mode) and metadata.st_uid != 0:
            raise SafetyError(f"plaintext env path crosses a non-system symlink: {current}")
    resolved = absolute.resolve(strict=False)
    forbidden = {".git", "artifacts", "build", "dist", "docs", "out", "public", "release", "site"}
    if any(part.casefold() in forbidden for part in resolved.parts):
        raise SafetyError("plaintext env path is inside a build or publication context")
    parent = resolved.parent
    if not parent.is_dir() or parent.is_symlink():
        raise SafetyError("plaintext env parent must be a real existing directory")
    protected_descendant = False
    current = parent
    while True:
        metadata = current.stat()
        if os.name != "nt":
            if metadata.st_uid not in {0, os.geteuid()}:
                raise SafetyError(f"plaintext env ancestor has an unexpected owner: {current}")
            writable = bool(metadata.st_mode & 0o022)
            sticky = bool(metadata.st_mode & stat.S_ISVTX)
            if writable and not (sticky and protected_descendant):
                raise SafetyError(f"plaintext env ancestor is group/world writable: {current}")
            if not writable:
                protected_descendant = True
        if current.parent == current:
            break
        current = current.parent
    if resolved.exists():
        metadata = resolved.stat()
        if resolved.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise SafetyError("plaintext env target must be a regular non-symlink file")
        if os.name != "nt" and (
            metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600
        ):
            raise SafetyError("existing plaintext env target must already be owner mode 0600")
    git = Path(git_value)
    if not git.is_absolute() or not git.is_file():
        raise SafetyError("an absolute Git executable is required to prove plaintext scope")
    top = _git(git, parent, "rev-parse", "--show-toplevel")
    if top.returncode == 0:
        repository = Path(top.stdout.strip()).resolve(strict=True)
        try:
            relative = resolved.relative_to(repository).as_posix()
        except ValueError:
            relative = ""
        if relative:
            tracked = _git(git, repository, "ls-files", "--error-unmatch", "--", relative)
            if tracked.returncode == 0:
                raise SafetyError("plaintext env target is tracked by Git")
            ignored = _git(git, repository, "check-ignore", "-q", "--", relative)
            if ignored.returncode != 0:
                raise SafetyError("plaintext env target is not covered by a Git ignore rule")
    return resolved


def main() -> int:
    if sys.version_info < (3, 10):
        print("wizard safety requires Python >=3.10", file=sys.stderr)
        return 2
    parser = argparse.ArgumentParser(allow_abbrev=False)
    commands = parser.add_subparsers(dest="command", required=True)
    url = commands.add_parser("url", allow_abbrev=False)
    url.add_argument("value")
    env = commands.add_parser("env", allow_abbrev=False)
    env.add_argument("value")
    env.add_argument("--git", required=True)
    args = parser.parse_args()
    try:
        if args.command == "url":
            normalized, host = validate_url(args.value)
            print(normalized)
            print(host)
        else:
            print(validate_env_path(args.value, args.git))
    except (OSError, SafetyError, subprocess.SubprocessError) as exc:
        print(f"wizard safety refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
