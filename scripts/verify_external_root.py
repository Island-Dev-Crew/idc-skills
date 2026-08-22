#!/usr/bin/env python3
"""Verify an IDC release from an out-of-repository threshold root."""

from __future__ import annotations

import argparse
import os
import stat
import sys
from pathlib import Path

from trust_root import TrustError, canonical_json, verify_external_release


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser(description=__doc__)
    value.add_argument("--repo", required=True, type=Path)
    value.add_argument("--trusted-root", required=True, type=Path)
    value.add_argument("--trusted-root-sha256", required=True)
    value.add_argument("--root-update", action="append", default=[], type=Path)
    value.add_argument("--release-statement", required=True, type=Path)
    value.add_argument("--archive", required=True, type=Path)
    value.add_argument("--freshness-index", required=True, type=Path)
    value.add_argument("--install-inventory", required=True, type=Path)
    value.add_argument("--manifest", required=True, type=Path)
    value.add_argument("--registry", required=True, type=Path)
    value.add_argument("--ssh-keygen", required=True, type=Path)
    value.add_argument("--ssh-keygen-sha256", required=True)
    value.add_argument("--git", required=True, type=Path)
    value.add_argument("--git-sha256", required=True)
    value.add_argument("--root-checkpoint", required=True, type=Path)
    return value


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(list(argv if argv is not None else sys.argv[1:]))
    try:
        checkpoint_path = args.root_checkpoint
        if not checkpoint_path.is_absolute():
            raise TrustError("root checkpoint path must be absolute")
        repo_resolved = args.repo.resolve(strict=True)
        checkpoint_resolved_parent = checkpoint_path.parent.resolve(strict=True)
        parent_metadata = checkpoint_resolved_parent.stat()
        if not stat.S_ISDIR(parent_metadata.st_mode):
            raise TrustError("root checkpoint parent must be a directory")
        if os.name != "nt" and (
            parent_metadata.st_uid not in {0, os.geteuid()}
            or parent_metadata.st_mode & 0o022
        ):
            raise TrustError(
                "root checkpoint parent must be owner-controlled and not group/world writable"
            )
        try:
            checkpoint_resolved_parent.relative_to(repo_resolved)
            raise TrustError("root checkpoint must be outside the candidate repository")
        except ValueError:
            pass
        checkpoint_data = None
        if checkpoint_path.exists():
            if checkpoint_path.is_symlink() or not checkpoint_path.is_file():
                raise TrustError("root checkpoint must be a regular non-symlink file")
            metadata = checkpoint_path.stat()
            if os.name != "nt" and (
                metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
            ):
                raise TrustError("root checkpoint must be owner-controlled and not group/world writable")
            checkpoint_data = checkpoint_path.read_bytes()
            if len(checkpoint_data) > 16 * 1024:
                raise TrustError("root checkpoint exceeds 16384 bytes")
        result = verify_external_release(
            repo=args.repo,
            trusted_root_path=args.trusted_root,
            trusted_root_digest=args.trusted_root_sha256,
            root_updates=args.root_update,
            statement_path=args.release_statement,
            artifacts={
                "archive": args.archive,
                "freshnessIndex": args.freshness_index,
                "installInventory": args.install_inventory,
                "manifest": args.manifest,
                "registry": args.registry,
            },
            ssh_keygen=args.ssh_keygen,
            ssh_keygen_digest=args.ssh_keygen_sha256,
            git=args.git,
            git_digest=args.git_sha256,
            root_checkpoint_data=checkpoint_data,
        )
        checkpoint_bytes = canonical_json(result["rootCheckpoint"])
        temporary = checkpoint_path.with_name(checkpoint_path.name + f".tmp-{os.getpid()}")
        try:
            descriptor = os.open(
                temporary,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0),
                0o600,
            )
            try:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    stream.write(checkpoint_bytes)
                    stream.flush()
                    os.fsync(descriptor)
            finally:
                os.close(descriptor)
            os.replace(temporary, checkpoint_path)
            if os.name != "nt":
                checkpoint_path.chmod(0o600)
                directory_descriptor = os.open(checkpoint_resolved_parent, os.O_RDONLY)
                try:
                    os.fsync(directory_descriptor)
                finally:
                    os.close(directory_descriptor)
        finally:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    except TrustError as exc:
        print(f"EXTERNAL TRUST REFUSED — {exc}", file=sys.stderr)
        return 2
    sys.stdout.buffer.write(canonical_json(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
