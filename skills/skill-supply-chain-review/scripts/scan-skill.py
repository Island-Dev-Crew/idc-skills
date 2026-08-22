#!/usr/bin/env python3
"""NUL-safe, terminal-safe advisory scanner for untrusted skill trees."""

from __future__ import annotations

import os
import re
import stat
import sys
from pathlib import Path
from typing import Iterator


MAX_FILE_BYTES = 4 * 1024 * 1024
SAFE_DISPLAY = frozenset(b"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._/-")
CLASSES = (
    ("shell-exec", r"\b(?:bash|sh\s+-c|exec|spawn)\b|\bsystem\s*\(|subprocess|child_process|os\.system"),
    ("network-egress", r"\b(?:curl|wget|nc)\b|\bfetch\s*\(|axios|urllib|requests\.(?:get|post)"),
    ("write-out-of-scope", r"~/|/etc/|/usr/|\$HOME|%APPDATA%|\.\./\.\."),
    ("dynamic-code", r"\beval\s*[('\"]|\bFunction\s*\(|\batob\s*[('\"]|base64\s+-d"),
    ("obfuscation", r"base64|fromCharCode|\\x[0-9a-f]{2}|eval\s*\(\s*atob|[A-Za-z0-9+/]{40,}={0,2}"),
    ("credential-access", r"API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE_KEY|process\.env|os\.environ|getenv"),
    ("unpinned-install", r"pip\s+install|npm\s+install|cargo\s+install|\bnpx\s|\buvx\s|\|\s*sh\b"),
    ("shell-profile", r"\.(?:bashrc|zshrc|profile|bash_profile)"),
    ("prompt-injection", r"ignore\s+(?:previous|all|prior|above)|disregard\s+(?:previous|all|prior)|do\s+not\s+(?:tell|inform)|without\s+(?:asking|confirmation|approval)|system\s+prompt|as\s+(?:an\s+)?(?:admin|root)|jailbreak"),
)
COMPILED = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in CLASSES)


def encode_display(value: bytes, limit: int | None = None) -> str:
    if limit is not None:
        value = value[:limit]
    return "".join(chr(byte) if byte in SAFE_DISPLAY else f"%{byte:02X}" for byte in value)


def relative(path: bytes, root: bytes) -> bytes:
    return os.path.relpath(path, root)


def snapshot(path: bytes) -> tuple[bytes, os.stat_result]:
    before = os.lstat(path)
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise OSError("opened candidate is not a regular file")
        if (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino):
            raise OSError("candidate identity changed before capture")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
    finally:
        os.close(descriptor)
    after = os.lstat(path)
    fields = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_size,
        item.st_mtime_ns,
    )
    if fields(before) != fields(opened) or fields(opened) != fields(after):
        raise OSError("candidate changed during capture")
    return data, opened


def walk(root: bytes) -> Iterator[tuple[bytes, os.stat_result]]:
    failures: list[OSError] = []

    def onerror(error: OSError) -> None:
        failures.append(error)

    for directory, dirnames, filenames in os.walk(
        root, topdown=True, onerror=onerror, followlinks=False
    ):
        dirnames.sort()
        filenames.sort()
        retained: list[bytes] = []
        for name in dirnames:
            path = os.path.join(directory, name)
            metadata = os.lstat(path)
            if stat.S_ISDIR(metadata.st_mode):
                retained.append(name)
            else:
                yield path, metadata
        dirnames[:] = retained
        for name in filenames:
            path = os.path.join(directory, name)
            yield path, os.lstat(path)
    if failures:
        raise failures[0]


def emit(location: str, classification: str, snippet: str) -> None:
    print(f"{location}\t{classification}\t{snippet}")


def main() -> int:
    if len(sys.argv) != 2:
        print("scan refused: exactly one candidate directory is required", file=sys.stderr)
        return 2
    root_path = Path(sys.argv[1])
    try:
        root = os.fsencode(root_path.resolve(strict=True))
    except OSError as exc:
        print(f"scan refused: {type(exc).__name__}", file=sys.stderr)
        return 2
    findings = 0
    entries = 0
    print("LOCATION\tCLASS\tSNIPPET")
    try:
        for path, metadata in walk(root):
            entries += 1
            shown = encode_display(relative(path, root))
            mode = metadata.st_mode
            if stat.S_ISLNK(mode):
                emit(shown, "symlink", "target=" + encode_display(os.readlink(path)))
                findings += 1
                continue
            if not stat.S_ISREG(mode):
                emit(shown, "special-file", f"mode={stat.S_IFMT(mode):#o}")
                findings += 1
                continue
            data, _ = snapshot(path)
            if len(data) > MAX_FILE_BYTES:
                emit(shown, "oversized", f"bytes>{MAX_FILE_BYTES}")
                findings += 1
                continue
            if b"\0" in data or any(byte < 32 and byte not in b"\t\n\v\f\r" for byte in data):
                emit(shown, "binary-blob", "not-text-scannable")
                findings += 1
                continue
            for line_number, raw_line in enumerate(data.splitlines(), 1):
                text = raw_line.decode("latin-1")
                for label, pattern in COMPILED:
                    if pattern.search(text) is None:
                        continue
                    emit(
                        f"{shown}:{line_number}",
                        label,
                        encode_display(raw_line.lstrip(), limit=60),
                    )
                    findings += 1
    except (OSError, ValueError) as exc:
        print(f"scan refused: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(f"scan complete: {findings} candidate finding(s) across {entries} entries.")
    print("ADVISORY - every hit needs human intent review; findings are evidence, not verdicts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
