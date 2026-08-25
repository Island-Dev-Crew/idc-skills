#!/usr/bin/env python3
"""Build canonical unsigned IDC trust payloads and assemble public envelopes.

This tool never accepts or opens a private key. Sign each emitted payload on its
custodian device with OpenSSH, then use ``envelope`` to combine the detached
public signatures.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import io
import json
import os
import re
import stat
import sys
import tarfile
from pathlib import Path

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
if str(SCRIPT_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIRECTORY))
BOOTSTRAP_DIRECTORY = SCRIPT_DIRECTORY.parent / "bootstrap"
if str(BOOTSTRAP_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(BOOTSTRAP_DIRECTORY))

import idc_verify_fresh as freshness

from trust_root import (
    RELEASE_NAMESPACE,
    RELEASE_SCHEMA,
    ROOT_NAMESPACE,
    ROOT_SCHEMA,
    TrustError,
    MAX_MANIFEST_BYTES,
    MAX_RELEASE_ARCHIVE_BYTES,
    canonical_json,
    build_install_inventory,
    content_signing_record,
    git_blob_oid,
    git_tree_entries,
    keyid_for,
    parse_release,
    parse_release_index,
    parse_registry,
    parse_root,
    parse_manifest_identity,
    parse_install_inventory,
    validate_release_archive,
    ParsedEnvelope,
    sha256_bytes,
    _git,
    _git_bytes,
    _regular_bytes,
    _validate_tool,
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


def _within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _external_path(path: Path, repo: Path, label: str) -> Path:
    if not path.is_absolute():
        raise TrustError(f"{label} path must be absolute")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TrustError(f"cannot resolve {label}: {exc}") from exc
    if _within(resolved, repo.resolve(strict=True)):
        raise TrustError(f"{label} must be outside the candidate repository")
    return resolved


def _protected_external_path(path: Path, repo: Path, label: str) -> Path:
    resolved = _external_path(path, repo, label)
    metadata = resolved.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
        raise TrustError(f"{label} must be a single-link regular file")
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise TrustError(f"{label} must be owner-controlled and not writable by others")
    return resolved


def write_new_external(path: Path, data: bytes, repo: Path) -> None:
    if not path.is_absolute():
        raise TrustError("release-index output path must be absolute")
    if path.is_symlink():
        raise TrustError(f"output must not be a symlink: {path}")
    try:
        parent = path.parent.resolve(strict=True)
    except OSError as exc:
        raise TrustError(f"release-index output parent is unavailable: {exc}") from exc
    if _within(parent, repo.resolve(strict=True)):
        raise TrustError("release-index output must be outside the candidate repository")
    metadata = parent.stat()
    if not stat.S_ISDIR(metadata.st_mode):
        raise TrustError("release-index output parent must be a directory")
    if os.name != "nt" and (
        metadata.st_uid not in {0, os.geteuid()} or metadata.st_mode & 0o022
    ):
        raise TrustError("release-index output parent must be owner-controlled and not writable by others")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o644)
    except FileExistsError as exc:
        raise TrustError(f"refusing to overwrite existing output: {path}") from exc
    except OSError as exc:
        raise TrustError(f"cannot create release-index output: {exc}") from exc
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(descriptor)
    except OSError as exc:
        raise TrustError(f"cannot write release-index output: {exc}") from exc
    finally:
        os.close(descriptor)


def _manifest_file_digest(
    repo: Path, manifest: dict[str, object], relative: str
) -> str:
    records = manifest.get("repositoryFiles")
    if not isinstance(records, dict) or relative not in records:
        raise TrustError(f"integrity manifest does not bind {relative}")
    record = records[relative]
    if not isinstance(record, dict) or set(record) != {"posixMode", "sha256", "size"}:
        raise TrustError(f"integrity manifest record differs for {relative}")
    path = repo / relative
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise TrustError(f"cannot resolve signed repository file {relative}: {exc}") from exc
    if resolved != path.absolute() or not resolved.is_file():
        raise TrustError(f"signed repository file crosses a symlink: {relative}")
    data = _regular_bytes(path, f"signed repository file {relative}", 64 * 1024 * 1024)
    observed = sha256_bytes(data)
    if (
        type(record.get("size")) is not int
        or record["size"] != len(data)
        or not isinstance(record.get("sha256"), str)
        or record["sha256"] != observed
        or type(record.get("posixMode")) is not int
    ):
        raise TrustError(f"signed repository file differs from manifest: {relative}")
    return observed


def _load_manifest_object(data: bytes) -> dict[str, object]:
    parse_manifest_identity(data)
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TrustError(f"integrity manifest is invalid: {exc}") from exc
    if not isinstance(value, dict):
        raise TrustError("integrity manifest must be an object")
    return value


def _verify_candidate_closure(
    repo: Path,
    git: Path,
    manifest: dict[str, object],
    manifest_data: bytes,
    signature_data: bytes,
) -> None:
    raw_tree = _git_bytes(git, repo, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    tree: dict[str, tuple[str, str]] = {}
    for raw_entry in raw_tree.split(b"\0"):
        if not raw_entry:
            continue
        header, separator, raw_path = raw_entry.partition(b"\t")
        fields = header.split()
        if not separator or len(fields) != 3:
            raise TrustError("Git tree emitted an invalid entry")
        mode, kind, oid = (field.decode("ascii", errors="strict") for field in fields)
        try:
            relative = raw_path.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise TrustError("Git tree path is not UTF-8") from exc
        if kind != "blob" or relative in tree:
            raise TrustError(f"release Git tree has unsupported entry: {relative}")
        tree[relative] = (mode, oid)
    records = manifest.get("repositoryFiles")
    if not isinstance(records, dict) or not records:
        raise TrustError("integrity manifest repositoryFiles must be a non-empty object")
    expected_paths = set(records) | {
        "integrity/manifest.json",
        "integrity/manifest.json.sig",
    }
    if set(tree) != expected_paths:
        raise TrustError(
            "signed Git tree differs from the manifest closure: "
            f"missing={sorted(expected_paths - set(tree))} "
            f"unexpected={sorted(set(tree) - expected_paths)}"
        )
    for relative, raw_record in records.items():
        if not isinstance(relative, str) or not relative:
            raise TrustError("integrity manifest repository path is invalid")
        record = raw_record if isinstance(raw_record, dict) else {}
        if set(record) != {"posixMode", "sha256", "size"}:
            raise TrustError(f"integrity manifest record differs for {relative}")
        path = repo / relative
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise TrustError(f"missing signed repository file: {relative}") from exc
        if resolved != path.absolute() or not resolved.is_file() or path.is_symlink():
            raise TrustError(f"signed repository path crosses a symlink: {relative}")
        data = _regular_bytes(path, f"signed repository file {relative}", 64 * 1024 * 1024)
        expected_mode = record.get("posixMode")
        git_mode = "100755" if expected_mode == 0o755 else "100644"
        if expected_mode not in {0o644, 0o755}:
            raise TrustError(f"manifest POSIX mode is not Git-canonical: {relative}")
        if (
            record.get("size") != len(data)
            or record.get("sha256") != sha256_bytes(data)
            or tree[relative] != (git_mode, git_blob_oid(data))
        ):
            raise TrustError(f"signed repository closure differs at {relative}")
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != expected_mode:
            raise TrustError(f"signed repository POSIX mode differs at {relative}")
    for relative, data in (
        ("integrity/manifest.json", manifest_data),
        ("integrity/manifest.json.sig", signature_data),
    ):
        path = repo / relative
        observed = _regular_bytes(path, relative, freshness.MAX_SIGNATURE_BYTES if relative.endswith(".sig") else MAX_MANIFEST_BYTES)
        if observed != data or tree[relative] != ("100644", git_blob_oid(data)):
            raise TrustError(f"{relative} differs from the signed Git tree")
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) != 0o644:
            raise TrustError(f"{relative} must have canonical POSIX mode 0644")


def _freshness_error(operation: str, callback: object) -> object:
    try:
        return callback()  # type: ignore[operator]
    except freshness.FreshnessError as exc:
        raise TrustError(f"{operation} refused: {exc}") from exc


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


def captured_artifact(data: bytes, label: str) -> dict[str, object]:
    if not data:
        raise TrustError(f"{label} artifact must not be empty")
    return {"sha256": sha256_bytes(data), "size": len(data)}


def cmd_release(args: argparse.Namespace) -> None:
    repo = args.repo.resolve(strict=True)
    if not repo.is_dir():
        raise TrustError("candidate repository must be a directory")
    git = _validate_tool(args.git, args.git_sha256, "Git", repo)
    ssh_keygen = _validate_tool(
        args.ssh_keygen, args.ssh_keygen_sha256, "ssh-keygen", repo
    )
    expected_manifest = repo / "integrity/manifest.json"
    expected_signature = repo / "integrity/manifest.json.sig"
    try:
        if args.manifest.resolve(strict=True) != expected_manifest.resolve(strict=True):
            raise TrustError("release payload must use the candidate integrity/manifest.json")
        if args.manifest_signature.resolve(strict=True) != expected_signature.resolve(strict=True):
            raise TrustError("release payload must use the candidate integrity/manifest.json.sig")
    except OSError as exc:
        raise TrustError(f"cannot resolve candidate manifest inputs: {exc}") from exc
    head = _git(git, repo, "rev-parse", "HEAD")
    tree = _git(git, repo, "rev-parse", "HEAD^{tree}")
    if head != args.git_commit:
        raise TrustError("requested release commit differs from clean candidate HEAD")
    if tree != args.git_tree:
        raise TrustError("requested release tree differs from candidate HEAD tree")
    tag_ref = f"refs/tags/{args.release}"
    if _git(git, repo, "cat-file", "-t", tag_ref) != "tag":
        raise TrustError("release payload requires an annotated local release tag")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{commit}}") != head:
        raise TrustError("release tag does not peel to candidate HEAD")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{tree}}") != tree:
        raise TrustError("release tag tree differs from candidate HEAD tree")
    manifest_data = _regular_bytes(args.manifest, "integrity manifest", MAX_MANIFEST_BYTES)
    signature_data = _regular_bytes(
        args.manifest_signature, "integrity manifest signature", 1024 * 1024
    )
    public_path = _protected_external_path(args.content_public_key, repo, "content public key")
    allowed_path = _protected_external_path(
        args.content_allowed_signers, repo, "content allowed_signers"
    )
    public_data = _regular_bytes(public_path, "content public key", 64 * 1024)
    allowed_data = _regular_bytes(allowed_path, "content allowed_signers", 64 * 1024)
    _freshness_error(
        "content signing anchor validation",
        lambda: freshness.validate_anchor(
            public_data,
            allowed_data,
            args.expected_content_fingerprint,
            str(ssh_keygen),
        ),
    )
    _freshness_error(
        "manifest signature verification",
        lambda: freshness.verify_signature(
            manifest_data,
            signature_data,
            allowed_data,
            freshness.MANIFEST_NAMESPACE,
            str(ssh_keygen),
        ),
    )
    manifest = _load_manifest_object(manifest_data)
    manifest_identity = parse_manifest_identity(manifest_data)
    if _manifest_file_digest(
        repo, manifest, "keys/idc-skills-signing.pub"
    ) != sha256_bytes(public_data):
        raise TrustError("external content public key differs from the signed manifest record")
    if _manifest_file_digest(
        repo, manifest, "keys/allowed_signers"
    ) != sha256_bytes(allowed_data):
        raise TrustError("external content allowed_signers differs from the signed manifest record")
    if manifest_identity["release"] != args.release:
        raise TrustError("integrity manifest release differs from requested release")
    inventory_data = _regular_bytes(
        args.install_inventory, "install inventory", 512 * 1024
    )
    parse_install_inventory(inventory_data, manifest_data)
    index_data = _regular_bytes(
        args.freshness_index, "release index", freshness.MAX_INDEX_BYTES
    )
    index_signature_data = _regular_bytes(
        args.freshness_index_signature,
        "release index signature",
        freshness.MAX_SIGNATURE_BYTES,
    )
    _freshness_error(
        "release-index signature verification",
        lambda: freshness.verify_signature(
            index_data,
            index_signature_data,
            allowed_data,
            freshness.INDEX_NAMESPACE,
            str(ssh_keygen),
        ),
    )
    release_index = parse_release_index(index_data)
    newest = release_index["releases"][-1]
    if newest["release"] != args.release:
        raise TrustError("release index newest release differs from requested release")
    if newest["manifestSequence"] != manifest_identity["manifestSequence"]:
        raise TrustError("release index newest manifest sequence differs from the manifest")
    if newest["manifestSHA256"] != sha256_bytes(manifest_data):
        raise TrustError("release index newest manifest digest differs from the manifest")
    if newest["gitCommit"] != args.git_commit:
        raise TrustError("release index newest Git commit differs from requested commit")
    records = manifest.get("repositoryFiles")
    if not isinstance(records, dict):
        raise TrustError("integrity manifest repositoryFiles must be an object")
    for relative, field in (
        ("bootstrap/idc_verify_fresh.py", "launcherSHA256"),
        ("scripts/skill_integrity.py", "verifierSHA256"),
    ):
        record = records.get(relative)
        if not isinstance(record, dict) or record.get("sha256") != newest[field]:
            raise TrustError(f"release index {field} differs from manifest record {relative}")
    registry_data = _regular_bytes(args.registry, "skills registry", 16 * 1024 * 1024)
    parse_registry(registry_data, manifest_identity)
    registry_record = records.get("skills/registry.json")
    if (
        not isinstance(registry_record, dict)
        or registry_record.get("sha256") != sha256_bytes(registry_data)
        or registry_record.get("size") != len(registry_data)
    ):
        raise TrustError("registry artifact differs from the integrity manifest")
    _verify_candidate_closure(repo, git, manifest, manifest_data, signature_data)
    archive_data = _regular_bytes(
        args.archive, "release archive", MAX_RELEASE_ARCHIVE_BYTES
    )
    validate_release_archive(
        archive_data,
        manifest_identity,
        manifest_data,
        signature_data,
        args.release,
        git_tree=git_tree_entries(git, repo, head),
    )
    signed = {
        "_type": "release",
        "artifacts": {
            "archive": captured_artifact(archive_data, "archive"),
            "freshnessIndex": captured_artifact(index_data, "freshness index"),
            "installInventory": captured_artifact(inventory_data, "install inventory"),
            "manifest": captured_artifact(manifest_data, "manifest"),
            "registry": captured_artifact(registry_data, "registry"),
        },
        "contentSigning": content_signing_record(
            public_path, allowed_path
        ),
        "expires": args.expires,
        "git": {"commit": args.git_commit, "tag": args.release, "tree": args.git_tree},
        "release": args.release,
        "releaseSequence": args.release_sequence,
        "rootVersion": args.root_version,
        "schema": RELEASE_SCHEMA,
    }
    envelope = ParsedEnvelope(value={}, signed=signed, signed_bytes=canonical_json(signed), digest="")
    parse_release(envelope)
    if dt.datetime.strptime(args.expires, "%Y-%m-%dT%H:%M:%SZ").replace(
        tzinfo=dt.timezone.utc
    ) <= dt.datetime.now(dt.timezone.utc):
        raise TrustError("release payload is already expired")
    if _git(git, repo, "rev-parse", "HEAD") != head or _git(
        git, repo, "rev-parse", "HEAD^{tree}"
    ) != tree:
        raise TrustError("candidate repository changed while release payload was built")
    write_new_external(args.output, canonical_json(signed), repo)
    print(f"wrote unsigned release payload {args.output} namespace={RELEASE_NAMESPACE}")


def cmd_install_inventory(args: argparse.Namespace) -> None:
    manifest_data = _regular_bytes(
        args.manifest,
        "integrity manifest",
        16 * 1024 * 1024,
    )
    inventory = build_install_inventory(manifest_data)
    write_new(args.output, inventory)
    print(f"wrote expected install inventory {args.output}")


def _build_release_archive_bytes(
    repo: Path,
    manifest: dict[str, object],
    manifest_data: bytes,
    signature_data: bytes,
    release: str,
) -> bytes:
    records = manifest.get("repositoryFiles")
    if not isinstance(records, dict):
        raise TrustError("integrity manifest repositoryFiles must be an object")
    files: dict[str, tuple[bytes, int]] = {}
    for relative, raw_record in records.items():
        if not isinstance(relative, str) or not isinstance(raw_record, dict):
            raise TrustError("integrity manifest repository record is invalid")
        files[relative] = (
            _regular_bytes(
                repo / relative,
                f"archive source {relative}",
                64 * 1024 * 1024,
            ),
            raw_record["posixMode"],
        )
    files["integrity/manifest.json"] = (manifest_data, 0o644)
    files["integrity/manifest.json.sig"] = (signature_data, 0o644)
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for relative in sorted(files):
            data, mode = files[relative]
            member = tarfile.TarInfo(f"idc-skills-{release}/{relative}")
            member.size = len(data)
            member.mode = mode
            member.mtime = 0
            member.uid = 0
            member.gid = 0
            member.uname = ""
            member.gname = ""
            archive.addfile(member, io.BytesIO(data))
    compressed = io.BytesIO()
    with gzip.GzipFile(
        filename="", fileobj=compressed, mode="wb", compresslevel=9, mtime=0
    ) as stream:
        stream.write(tar_buffer.getvalue())
    return compressed.getvalue()


def cmd_release_archive(args: argparse.Namespace) -> None:
    repo = args.repo.resolve(strict=True)
    if not repo.is_dir():
        raise TrustError("candidate repository must be a directory")
    git = _validate_tool(args.git, args.git_sha256, "Git", repo)
    ssh_keygen = _validate_tool(
        args.ssh_keygen, args.ssh_keygen_sha256, "ssh-keygen", repo
    )
    expected_manifest = repo / "integrity/manifest.json"
    expected_signature = repo / "integrity/manifest.json.sig"
    try:
        if args.manifest.resolve(strict=True) != expected_manifest.resolve(strict=True):
            raise TrustError("release archive must use candidate integrity/manifest.json")
        if args.manifest_signature.resolve(strict=True) != expected_signature.resolve(strict=True):
            raise TrustError("release archive must use candidate integrity/manifest.json.sig")
    except OSError as exc:
        raise TrustError(f"cannot resolve candidate manifest inputs: {exc}") from exc
    head = _git(git, repo, "rev-parse", "HEAD")
    tree = _git(git, repo, "rev-parse", "HEAD^{tree}")
    manifest_data = _regular_bytes(args.manifest, "integrity manifest", MAX_MANIFEST_BYTES)
    signature_data = _regular_bytes(
        args.manifest_signature, "integrity manifest signature", freshness.MAX_SIGNATURE_BYTES
    )
    public_path = _protected_external_path(
        args.content_public_key, repo, "content public key"
    )
    allowed_path = _protected_external_path(
        args.content_allowed_signers, repo, "content allowed_signers"
    )
    public_data = _regular_bytes(public_path, "content public key", 64 * 1024)
    allowed_data = _regular_bytes(allowed_path, "content allowed_signers", 64 * 1024)
    _freshness_error(
        "content signing anchor validation",
        lambda: freshness.validate_anchor(
            public_data,
            allowed_data,
            args.expected_content_fingerprint,
            str(ssh_keygen),
        ),
    )
    _freshness_error(
        "manifest signature verification",
        lambda: freshness.verify_signature(
            manifest_data,
            signature_data,
            allowed_data,
            freshness.MANIFEST_NAMESPACE,
            str(ssh_keygen),
        ),
    )
    manifest = _load_manifest_object(manifest_data)
    identity = parse_manifest_identity(manifest_data)
    if _manifest_file_digest(
        repo, manifest, "keys/idc-skills-signing.pub"
    ) != sha256_bytes(public_data):
        raise TrustError("external content public key differs from signed manifest record")
    if _manifest_file_digest(
        repo, manifest, "keys/allowed_signers"
    ) != sha256_bytes(allowed_data):
        raise TrustError("external content allowed_signers differs from signed manifest record")
    registry_data = _regular_bytes(
        repo / "skills/registry.json", "skills registry", 16 * 1024 * 1024
    )
    parse_registry(registry_data, identity)
    tag_ref = f"refs/tags/{identity['release']}"
    if _git(git, repo, "cat-file", "-t", tag_ref) != "tag":
        raise TrustError("release archive requires an annotated local release tag")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{commit}}") != head:
        raise TrustError("release tag does not peel to candidate HEAD")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{tree}}") != tree:
        raise TrustError("release tag tree differs from candidate HEAD tree")
    _verify_candidate_closure(repo, git, manifest, manifest_data, signature_data)
    archive_data = _build_release_archive_bytes(
        repo, manifest, manifest_data, signature_data, identity["release"]
    )
    validate_release_archive(
        archive_data,
        identity,
        manifest_data,
        signature_data,
        identity["release"],
        git_tree=git_tree_entries(git, repo, head),
    )
    _verify_candidate_closure(repo, git, manifest, manifest_data, signature_data)
    if _git(git, repo, "rev-parse", "HEAD") != head or _git(
        git, repo, "rev-parse", "HEAD^{tree}"
    ) != tree:
        raise TrustError("candidate repository changed while release archive was built")
    write_new_external(args.output, archive_data, repo)
    print(
        f"wrote deterministic release archive {args.output} "
        f"release={identity['release']} commit={head} sha256={sha256_bytes(archive_data)}"
    )


def cmd_release_index(args: argparse.Namespace) -> None:
    repo = args.repo.resolve(strict=True)
    if not repo.is_dir():
        raise TrustError("candidate repository must be a directory")
    git = _validate_tool(args.git, args.git_sha256, "Git", repo)
    ssh_keygen = _validate_tool(
        args.ssh_keygen, args.ssh_keygen_sha256, "ssh-keygen", repo
    )
    expected_manifest = repo / "integrity/manifest.json"
    expected_signature = repo / "integrity/manifest.json.sig"
    try:
        if args.manifest.resolve(strict=True) != expected_manifest.resolve(strict=True):
            raise TrustError("release index must use the candidate integrity/manifest.json")
        if args.manifest_signature.resolve(strict=True) != expected_signature.resolve(strict=True):
            raise TrustError("release index must use the candidate integrity/manifest.json.sig")
    except OSError as exc:
        raise TrustError(f"cannot resolve candidate manifest inputs: {exc}") from exc
    head = _git(git, repo, "rev-parse", "HEAD")
    if not re.fullmatch(r"[0-9a-f]{40}", head):
        raise TrustError("candidate HEAD must be a 40-character SHA-1 commit")

    manifest_data = _regular_bytes(args.manifest, "integrity manifest", MAX_MANIFEST_BYTES)
    signature_data = _regular_bytes(
        args.manifest_signature, "integrity manifest signature", 1024 * 1024
    )
    public_path = _protected_external_path(args.content_public_key, repo, "content public key")
    allowed_path = _protected_external_path(
        args.content_allowed_signers, repo, "content allowed_signers"
    )
    public_data = _regular_bytes(public_path, "content public key", 64 * 1024)
    allowed_data = _regular_bytes(allowed_path, "content allowed_signers", 64 * 1024)
    _freshness_error(
        "content signing anchor validation",
        lambda: freshness.validate_anchor(
            public_data,
            allowed_data,
            args.expected_content_fingerprint,
            str(ssh_keygen),
        ),
    )
    _freshness_error(
        "manifest signature verification",
        lambda: freshness.verify_signature(
            manifest_data,
            signature_data,
            allowed_data,
            freshness.MANIFEST_NAMESPACE,
            str(ssh_keygen),
        ),
    )
    manifest = _load_manifest_object(manifest_data)
    identity = parse_manifest_identity(manifest_data)
    if _manifest_file_digest(
        repo, manifest, "keys/idc-skills-signing.pub"
    ) != sha256_bytes(public_data):
        raise TrustError("external content public key differs from the signed manifest record")
    if _manifest_file_digest(
        repo, manifest, "keys/allowed_signers"
    ) != sha256_bytes(allowed_data):
        raise TrustError("external content allowed_signers differs from the signed manifest record")
    tag_ref = f"refs/tags/{identity['release']}"
    if _git(git, repo, "cat-file", "-t", tag_ref) != "tag":
        raise TrustError("release index requires an annotated local release tag")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{commit}}") != head:
        raise TrustError("release tag does not peel to candidate HEAD")
    if _git(git, repo, "rev-parse", f"{tag_ref}^{{tree}}") != _git(
        git, repo, "rev-parse", "HEAD^{tree}"
    ):
        raise TrustError("release tag tree differs from candidate HEAD tree")
    entry = {
        "gitCommit": head,
        "launcherSHA256": _manifest_file_digest(
            repo, manifest, "bootstrap/idc_verify_fresh.py"
        ),
        "manifestSHA256": sha256_bytes(manifest_data),
        "manifestSequence": identity["manifestSequence"],
        "release": identity["release"],
        "verifierSHA256": _manifest_file_digest(
            repo, manifest, "scripts/skill_integrity.py"
        ),
    }

    previous_arguments = (
        args.previous_index,
        args.previous_index_signature,
        args.previous_checkpoint,
        args.previous_checkpoint_sha256,
    )
    previous_generated_at = None
    if args.genesis:
        if any(value is not None for value in previous_arguments):
            raise TrustError("--genesis is mutually exclusive with previous-index inputs")
        if identity["manifestSequence"] != 1:
            raise TrustError("release-index genesis is allowed only for manifest sequence 1")
        index_sequence = 1
        releases = [entry]
    else:
        if any(value is None for value in previous_arguments):
            raise TrustError(
                "non-genesis release index requires previous index, signature, and checkpoint"
            )
        previous_index_path = _protected_external_path(
            args.previous_index, repo, "previous release index"
        )
        previous_signature_path = _protected_external_path(
            args.previous_index_signature, repo, "previous release index signature"
        )
        previous_checkpoint_path = _protected_external_path(
            args.previous_checkpoint, repo, "previous freshness checkpoint"
        )
        previous_data = _regular_bytes(
            previous_index_path,
            "previous release index",
            freshness.MAX_INDEX_BYTES,
        )
        previous_signature = _regular_bytes(
            previous_signature_path,
            "previous release index signature",
            freshness.MAX_SIGNATURE_BYTES,
        )
        _freshness_error(
            "previous release-index signature verification",
            lambda: freshness.verify_signature(
                previous_data,
                previous_signature,
                allowed_data,
                freshness.INDEX_NAMESPACE,
                str(ssh_keygen),
            ),
        )
        try:
            previous_untrusted = json.loads(previous_data.decode("utf-8"))
            previous_generated = freshness._parse_utc(
                previous_untrusted.get("generatedAt") if isinstance(previous_untrusted, dict) else None,
                "generatedAt",
            )
        except (UnicodeDecodeError, json.JSONDecodeError, freshness.FreshnessError) as exc:
            raise TrustError(f"previous release index cannot be imported: {exc}") from exc
        previous_generated_at = previous_generated
        previous_index = _freshness_error(
            "previous release-index validation",
            lambda: freshness.parse_index(previous_data, now=previous_generated),
        )
        checkpoint_data = _regular_bytes(
            previous_checkpoint_path,
            "previous freshness checkpoint",
            freshness.MAX_CHECKPOINT_BYTES,
        )
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", args.previous_checkpoint_sha256):
            raise TrustError("previous freshness-checkpoint digest pin is invalid")
        if sha256_bytes(checkpoint_data) != args.previous_checkpoint_sha256:
            raise TrustError("previous freshness checkpoint differs from its external digest pin")
        checkpoint = _freshness_error(
            "previous freshness-checkpoint validation",
            lambda: freshness._parse_checkpoint(checkpoint_data),
        )
        previous_digest = freshness.sha256_bytes(previous_data)
        if (
            checkpoint["indexSequence"] != previous_index["indexSequence"]
            or checkpoint["indexSHA256"] != previous_digest
            or checkpoint["releases"] != previous_index["releases"]
        ):
            raise TrustError(
                "previous freshness checkpoint does not identify the supplied latest index"
            )
        if previous_index["indexSequence"] >= freshness.MAX_SEQUENCE:
            raise TrustError("release index sequence is exhausted")
        index_sequence = previous_index["indexSequence"] + 1
        releases = list(previous_index["releases"])
        by_sequence = {item["manifestSequence"]: item for item in releases}
        old = by_sequence.get(identity["manifestSequence"])
        if old is not None:
            if old != entry:
                raise TrustError(
                    "manifest-sequence equivocation differs from previous release history"
                )
        else:
            if identity["manifestSequence"] <= releases[-1]["manifestSequence"]:
                raise TrustError("release manifest sequence does not advance previous history")
            if identity["release"] in {item["release"] for item in releases}:
                raise TrustError("release name already exists in previous release history")
            releases.append(entry)

    value = {
        "generatedAt": args.generated_at,
        "indexSequence": index_sequence,
        "releases": releases,
        "schema": freshness.INDEX_SCHEMA,
        "validUntil": args.valid_until,
    }
    try:
        generated = freshness._parse_utc(args.generated_at, "generatedAt")
        output_data = freshness.canonical_bytes(value)
        parsed = freshness.parse_index(output_data)
    except freshness.FreshnessError as exc:
        raise TrustError(f"new release index is invalid: {exc}") from exc
    if previous_generated_at is not None and generated <= previous_generated_at:
        raise TrustError("new release index generatedAt does not advance previous index time")
    if parsed != value:
        raise TrustError("new release index parser changed the derived payload")
    _verify_candidate_closure(repo, git, manifest, manifest_data, signature_data)
    if head != _git(git, repo, "rev-parse", "HEAD"):
        raise TrustError("candidate repository changed while release index was built")
    write_new_external(args.output, output_data, repo)
    print(
        f"wrote unsigned release index {args.output} "
        f"indexSequence={index_sequence} release={identity['release']} commit={head}"
    )


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
    release.add_argument("--repo", required=True, type=Path)
    release.add_argument("--release", required=True)
    release.add_argument("--release-sequence", required=True, type=int)
    release.add_argument("--root-version", required=True, type=int)
    release.add_argument("--expires", required=True)
    release.add_argument("--git-commit", required=True)
    release.add_argument("--git-tree", required=True)
    release.add_argument("--archive", required=True, type=Path)
    release.add_argument("--freshness-index", required=True, type=Path)
    release.add_argument("--freshness-index-signature", required=True, type=Path)
    release.add_argument("--install-inventory", required=True, type=Path)
    release.add_argument("--manifest", required=True, type=Path)
    release.add_argument("--manifest-signature", required=True, type=Path)
    release.add_argument("--registry", required=True, type=Path)
    release.add_argument("--content-public-key", required=True, type=Path)
    release.add_argument("--content-allowed-signers", required=True, type=Path)
    release.add_argument("--expected-content-fingerprint", required=True)
    release.add_argument("--git", required=True, type=Path)
    release.add_argument("--git-sha256", required=True)
    release.add_argument("--ssh-keygen", required=True, type=Path)
    release.add_argument("--ssh-keygen-sha256", required=True)
    release.add_argument("--output", required=True, type=Path)
    release.set_defaults(function=cmd_release)

    inventory = commands.add_parser(
        "install-inventory",
        help="build a canonical pre-install expectation from a release manifest",
    )
    inventory.add_argument("--manifest", required=True, type=Path)
    inventory.add_argument("--output", required=True, type=Path)
    inventory.set_defaults(function=cmd_install_inventory)

    archive = commands.add_parser(
        "release-archive",
        help="build a deterministic exact-tree tar.gz from a signed clean candidate",
    )
    archive.add_argument("--repo", required=True, type=Path)
    archive.add_argument("--manifest", required=True, type=Path)
    archive.add_argument("--manifest-signature", required=True, type=Path)
    archive.add_argument("--content-public-key", required=True, type=Path)
    archive.add_argument("--content-allowed-signers", required=True, type=Path)
    archive.add_argument("--expected-content-fingerprint", required=True)
    archive.add_argument("--git", required=True, type=Path)
    archive.add_argument("--git-sha256", required=True)
    archive.add_argument("--ssh-keygen", required=True, type=Path)
    archive.add_argument("--ssh-keygen-sha256", required=True)
    archive.add_argument("--output", required=True, type=Path)
    archive.set_defaults(function=cmd_release_archive)

    index = commands.add_parser(
        "release-index",
        help="derive a canonical unsigned release index from a clean signed candidate",
    )
    index.add_argument("--repo", required=True, type=Path)
    index.add_argument("--manifest", required=True, type=Path)
    index.add_argument("--manifest-signature", required=True, type=Path)
    index.add_argument("--content-public-key", required=True, type=Path)
    index.add_argument("--content-allowed-signers", required=True, type=Path)
    index.add_argument("--expected-content-fingerprint", required=True)
    index.add_argument("--generated-at", required=True)
    index.add_argument("--valid-until", required=True)
    index.add_argument("--git", required=True, type=Path)
    index.add_argument("--git-sha256", required=True)
    index.add_argument("--ssh-keygen", required=True, type=Path)
    index.add_argument("--ssh-keygen-sha256", required=True)
    index.add_argument("--genesis", action="store_true")
    index.add_argument("--previous-index", type=Path)
    index.add_argument("--previous-index-signature", type=Path)
    index.add_argument("--previous-checkpoint", type=Path)
    index.add_argument("--previous-checkpoint-sha256")
    index.add_argument("--output", required=True, type=Path)
    index.set_defaults(function=cmd_release_index)

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
