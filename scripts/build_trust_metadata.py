#!/usr/bin/env python3
"""Build canonical unsigned IDC trust payloads and assemble public envelopes.

This tool never accepts or opens a private key. Sign each emitted payload on its
custodian device with OpenSSH, then use ``envelope`` to combine the detached
public signatures.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

from trust_root import (
    RELEASE_NAMESPACE,
    RELEASE_SCHEMA,
    ROOT_NAMESPACE,
    ROOT_SCHEMA,
    TrustError,
    canonical_json,
    keyid_for,
    parse_release,
    parse_root,
    ParsedEnvelope,
    sha256_file,
)


def public_key(path: Path) -> tuple[str, dict[str, object]]:
    try:
        parts = path.read_text(encoding="utf-8").split()
    except (OSError, UnicodeDecodeError) as exc:
        raise TrustError(f"cannot read public key {path}: {exc}") from exc
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise TrustError(f"public key must begin with ssh-ed25519: {path}")
    value = {
        "keytype": "ed25519",
        "keyval": {"public": f"{parts[0]} {parts[1]}"},
        "scheme": "ssh-ed25519",
    }
    return keyid_for(value), value


def write_new(path: Path, value: object) -> None:
    if path.is_symlink():
        raise TrustError(f"output must not be a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as stream:
            stream.write(canonical_json(value))
        if os.name != "nt":
            path.chmod(0o644)
    except FileExistsError as exc:
        raise TrustError(f"refusing to overwrite existing output: {path}") from exc


def cmd_keyid(args: argparse.Namespace) -> None:
    keyid, _ = public_key(args.public_key)
    print(keyid)


def cmd_root(args: argparse.Namespace) -> None:
    root = [public_key(path) for path in args.root_key]
    release = [public_key(path) for path in args.release_key]
    root_ids = [item[0] for item in root]
    release_ids = [item[0] for item in release]
    if len(root_ids) != len(set(root_ids)) or len(release_ids) != len(set(release_ids)):
        raise TrustError("each role must list unique public keys")
    keys = dict(root + release)
    signed = {
        "_type": "root",
        "consistentSnapshot": True,
        "expires": args.expires,
        "keys": keys,
        "roles": {
            "release": {"keyids": release_ids, "threshold": args.release_threshold},
            "root": {"keyids": root_ids, "threshold": args.root_threshold},
        },
        "schema": ROOT_SCHEMA,
        "specVersion": "1.0",
        "version": args.version,
    }
    envelope = ParsedEnvelope(value={}, signed=signed, signed_bytes=canonical_json(signed), digest="")
    parse_root(envelope, "root payload")
    write_new(args.output, signed)
    print(f"wrote unsigned root payload {args.output} namespace={ROOT_NAMESPACE}")
    for keyid in root_ids:
        print(f"root-keyid {keyid}")
    for keyid in release_ids:
        print(f"release-keyid {keyid}")


def artifact(path: Path) -> dict[str, object]:
    if path.is_symlink() or not path.is_file():
        raise TrustError(f"artifact must be a regular non-symlink file: {path}")
    size = path.stat().st_size
    if size < 1:
        raise TrustError(f"artifact must not be empty: {path}")
    return {"sha256": sha256_file(path), "size": size}


def cmd_release(args: argparse.Namespace) -> None:
    signed = {
        "_type": "release",
        "artifacts": {
            "archive": artifact(args.archive),
            "freshnessIndex": artifact(args.freshness_index),
            "installInventory": artifact(args.install_inventory),
            "manifest": artifact(args.manifest),
            "registry": artifact(args.registry),
        },
        "expires": args.expires,
        "git": {"commit": args.git_commit, "tag": args.release, "tree": args.git_tree},
        "release": args.release,
        "releaseSequence": args.release_sequence,
        "rootVersion": args.root_version,
        "schema": RELEASE_SCHEMA,
    }
    envelope = ParsedEnvelope(value={}, signed=signed, signed_bytes=canonical_json(signed), digest="")
    parse_release(envelope)
    write_new(args.output, signed)
    print(f"wrote unsigned release payload {args.output} namespace={RELEASE_NAMESPACE}")


def signature_arg(value: str) -> tuple[str, Path]:
    keyid, separator, path = value.partition("=")
    if not separator or not re.fullmatch(r"[0-9a-f]{64}", keyid) or not path:
        raise argparse.ArgumentTypeError("signature must be KEYID=/absolute/or/relative/signature")
    return keyid, Path(path)


def cmd_envelope(args: argparse.Namespace) -> None:
    try:
        raw = args.payload.read_bytes()
        signed = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"cannot read payload: {exc}") from exc
    if raw != canonical_json(signed) or not isinstance(signed, dict):
        raise TrustError("payload must be one canonical JSON object")
    signatures = []
    seen: set[str] = set()
    for keyid, path in args.signature:
        if keyid in seen:
            raise TrustError(f"duplicate signature keyid: {keyid}")
        seen.add(keyid)
        try:
            value = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise TrustError(f"cannot read signature {path}: {exc}") from exc
        if not value.startswith("-----BEGIN SSH SIGNATURE-----\n") or not value.endswith(
            "-----END SSH SIGNATURE-----\n"
        ):
            raise TrustError(f"signature is not an armored OpenSSH signature: {path}")
        signatures.append({"keyid": keyid, "sig": value})
    write_new(args.output, {"signatures": signatures, "signed": signed})
    print(f"wrote public signature envelope {args.output} signatures={len(signatures)}")


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    keyid = commands.add_parser("keyid", help="derive the canonical IDC key ID")
    keyid.add_argument("--public-key", required=True, type=Path)
    keyid.set_defaults(function=cmd_keyid)

    root = commands.add_parser("root-payload", help="build an unsigned canonical root payload")
    root.add_argument("--version", required=True, type=int)
    root.add_argument("--expires", required=True)
    root.add_argument("--root-key", required=True, action="append", type=Path)
    root.add_argument("--root-threshold", required=True, type=int)
    root.add_argument("--release-key", required=True, action="append", type=Path)
    root.add_argument("--release-threshold", required=True, type=int)
    root.add_argument("--output", required=True, type=Path)
    root.set_defaults(function=cmd_root)

    release = commands.add_parser("release-payload", help="build an unsigned release payload")
    release.add_argument("--release", required=True)
    release.add_argument("--release-sequence", required=True, type=int)
    release.add_argument("--root-version", required=True, type=int)
    release.add_argument("--expires", required=True)
    release.add_argument("--git-commit", required=True)
    release.add_argument("--git-tree", required=True)
    release.add_argument("--archive", required=True, type=Path)
    release.add_argument("--freshness-index", required=True, type=Path)
    release.add_argument("--install-inventory", required=True, type=Path)
    release.add_argument("--manifest", required=True, type=Path)
    release.add_argument("--registry", required=True, type=Path)
    release.add_argument("--output", required=True, type=Path)
    release.set_defaults(function=cmd_release)

    envelope = commands.add_parser("envelope", help="assemble detached signatures around a payload")
    envelope.add_argument("--payload", required=True, type=Path)
    envelope.add_argument("--signature", required=True, action="append", type=signature_arg)
    envelope.add_argument("--output", required=True, type=Path)
    envelope.set_defaults(function=cmd_envelope)
    return parser


def main() -> int:
    args = make_parser().parse_args()
    try:
        args.function(args)
    except TrustError as exc:
        print(f"TRUST METADATA BUILD REFUSED — {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
