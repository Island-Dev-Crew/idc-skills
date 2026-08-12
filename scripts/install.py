#!/usr/bin/env python3
"""Dependency-free installer and compatibility exporter for IDC skills.

Native ``install`` mode copies canonical skill directories byte-for-byte to the
documented Codex/Claude Code/Pi/Hermes topology or to explicitly named custom
targets. ``export-claude-ai`` is a separate, non-canonical export profile.  Its
frontmatter allow-list is the six-key set supplied by the user on 2026-08-11
(``allowed-tools``, ``compatibility``, ``description``, ``license``, ``metadata``,
``name``); that historical compatibility snapshot came from a user-supplied
prior-upload audit, is not an official current specification, and current upload
acceptance is unverified.  Export behavior is defined by an explicit profile
so another strict harness can add its own allow-list without changing canonical
skills.  The Claude.ai profile validates against exactly the supplied set and
moves ``disable-model-invocation`` and ``argument-hint`` under ``metadata``
without changing their scalar values.  This preserves information only; it does
not assert that a harness which ignores those metadata fields retains invocation
behavior.

No mode edits the repository's canonical ``skills/`` tree.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import uuid
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Sequence


CLAUDE_AI_ALLOWED_KEYS = (
    "allowed-tools",
    "compatibility",
    "description",
    "license",
    "metadata",
    "name",
)
CLAUDE_AI_TRANSFORM_KEYS = ("disable-model-invocation", "argument-hint")
CLAUDE_AI_ASSUMPTION = (
    "historical user-supplied prior-upload audit captured 2026-08-11: the upload "
    "validator was reported to accept exactly allowed-tools, compatibility, "
    "description, license, metadata, name; not an official current specification; "
    "current upload acceptance is unverified"
)
DEFAULT_TARGET_ORDER = ("agents", "claude", "pi", "hermes")
TOP_LEVEL_KEY_RE = re.compile(r"^([A-Za-z0-9_-]+):(?:[ \t]*(.*))?$")
SKILL_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class InstallError(RuntimeError):
    """A safe, user-actionable installer failure."""


@dataclass(frozen=True)
class ExportProfile:
    """An explicit, extendable strict-frontmatter export contract."""

    identifier: str
    harness: str
    allowed_top_level_keys: tuple[str, ...]
    keys_to_metadata: tuple[str, ...]
    assumption: str
    assumption_status: str
    assumption_source: str
    semantics_note: str


CLAUDE_AI_PROFILE = ExportProfile(
    identifier="claude-ai-supplied-20260811",
    harness="claude.ai supplied compatibility snapshot (2026-08-11)",
    allowed_top_level_keys=CLAUDE_AI_ALLOWED_KEYS,
    keys_to_metadata=CLAUDE_AI_TRANSFORM_KEYS,
    assumption=CLAUDE_AI_ASSUMPTION,
    assumption_status=(
        "historical user-supplied snapshot; not official current specification; "
        "current upload acceptance unverified"
    ),
    assumption_source="user-supplied prior-upload audit captured 2026-08-11",
    semantics_note=(
        "Values are preserved as metadata only. Invocation behavior is not asserted; "
        "a harness that ignores these metadata fields will not retain that behavior."
    ),
)


@dataclass(frozen=True)
class ManifestEntry:
    path: str
    size: int
    sha256: str
    kind: str = "file"

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class TreeManifest:
    entries: tuple[ManifestEntry, ...]
    sha256: str

    def as_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "files": [entry.as_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class TargetSpec:
    name: str
    path: Path
    optional_if_absent: bool = False
    provenance: str = "custom"


@dataclass
class SkillResult:
    skill: str
    status: str
    source_sha256: str
    destination_sha256: str | None = None
    differences: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "skill": self.skill,
            "status": self.status,
            "sourceSha256": self.source_sha256,
            "destinationSha256": self.destination_sha256,
        }
        if self.differences:
            result["differences"] = list(self.differences)
        return result


@dataclass
class TargetResult:
    name: str
    path: str
    status: str
    provenance: str
    covered_by: str | None = None
    skills: list[SkillResult] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "name": self.name,
            "path": self.path,
            "status": self.status,
            "provenance": self.provenance,
            "skills": [skill.as_dict() for skill in self.skills],
        }
        if self.covered_by:
            result["coveredBy"] = self.covered_by
        if self.error:
            result["error"] = self.error
        return result


@dataclass
class InstallReport:
    mode: str
    success: bool
    dry_run: bool
    verify_only: bool
    targets: list[TargetResult]
    errors: list[str] = field(default_factory=list)
    assumption: str | None = None

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "mode": self.mode,
            "success": self.success,
            "dryRun": self.dry_run,
            "verifyOnly": self.verify_only,
            "targets": [target.as_dict() for target in self.targets],
            "errors": self.errors,
        }
        if self.assumption:
            result["assumption"] = self.assumption
        return result


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _manifest_digest(entries: Iterable[ManifestEntry]) -> str:
    payload = json.dumps(
        [entry.as_dict() for entry in entries],
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return _sha256_bytes(payload)


def tree_manifest(root: Path) -> TreeManifest:
    """Hash every file and symlink below *root* in stable relative-path order."""
    root = Path(root)
    if not root.is_dir():
        raise InstallError(f"manifest root is not a directory: {root}")

    entries: list[ManifestEntry] = []
    for path in sorted(root.rglob("*"), key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            target = os.readlink(path)
            payload = ("SYMLINK\0" + target).encode("utf-8", errors="surrogateescape")
            entries.append(
                ManifestEntry(relative, len(payload), _sha256_bytes(payload), "symlink")
            )
        elif path.is_file():
            digest = hashlib.sha256()
            size = 0
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    size += len(chunk)
                    digest.update(chunk)
            entries.append(ManifestEntry(relative, size, digest.hexdigest()))
        elif not path.is_dir():
            raise InstallError(f"unsupported filesystem entry: {path}")
    frozen = tuple(entries)
    return TreeManifest(frozen, _manifest_digest(frozen))


def manifest_differences(expected: TreeManifest, actual: TreeManifest) -> tuple[str, ...]:
    expected_by_path = {entry.path: entry for entry in expected.entries}
    actual_by_path = {entry.path: entry for entry in actual.entries}
    differences: list[str] = []
    for path in sorted(expected_by_path.keys() - actual_by_path.keys()):
        differences.append(f"missing:{path}")
    for path in sorted(actual_by_path.keys() - expected_by_path.keys()):
        differences.append(f"extra:{path}")
    for path in sorted(expected_by_path.keys() & actual_by_path.keys()):
        if expected_by_path[path] != actual_by_path[path]:
            differences.append(f"changed:{path}")
    return tuple(differences)


def _resolved(path: Path) -> Path:
    return Path(os.path.abspath(os.path.realpath(os.path.expanduser(str(path)))))


def _path_key(path: Path) -> str:
    return os.path.normcase(str(_resolved(path)))


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        _resolved(path).relative_to(_resolved(parent))
        return True
    except ValueError:
        return False


def validate_target_path(source_skills: Path, target: Path) -> None:
    """Reject targets that could overwrite or recursively copy canonical skills."""
    source = _resolved(source_skills)
    destination = _resolved(target)
    if source == destination:
        raise InstallError(f"unsafe target equals canonical skills directory: {target}")
    if _is_relative_to(destination, source):
        raise InstallError(f"unsafe target is inside canonical skills directory: {target}")
    if _is_relative_to(source, destination):
        raise InstallError(f"unsafe target contains canonical skills directory: {target}")


def _frontmatter_lines(data: bytes, source: str) -> tuple[list[str], list[str], str]:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InstallError(f"{source}: SKILL.md is not UTF-8: {exc}") from exc
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise InstallError(f"{source}: SKILL.md must start with YAML frontmatter")
    closing = next(
        (index for index, line in enumerate(lines[1:], start=1) if line.rstrip("\r\n") == "---"),
        None,
    )
    if closing is None:
        raise InstallError(f"{source}: SKILL.md frontmatter has no closing delimiter")
    newline = "\r\n" if lines[0].endswith("\r\n") else "\n"
    return lines[1:closing], lines[closing + 1 :], newline


def _top_level_keys(frontmatter: Sequence[str], source: str) -> list[tuple[int, str, str]]:
    found: list[tuple[int, str, str]] = []
    seen: set[str] = set()
    for index, raw_line in enumerate(frontmatter):
        line = raw_line.rstrip("\r\n")
        if not line or line.lstrip().startswith("#") or line[0].isspace():
            continue
        match = TOP_LEVEL_KEY_RE.match(line)
        if not match:
            raise InstallError(f"{source}: unsupported top-level frontmatter syntax: {line!r}")
        key, value = match.group(1), match.group(2) or ""
        if key in seen:
            raise InstallError(f"{source}: duplicate frontmatter key: {key}")
        seen.add(key)
        found.append((index, key, value))
    return found


def frontmatter_name(skill_md: Path) -> str:
    frontmatter, _, _ = _frontmatter_lines(skill_md.read_bytes(), str(skill_md))
    keys = _top_level_keys(frontmatter, str(skill_md))
    values = [value.strip().strip("\"'") for _, key, value in keys if key == "name"]
    if len(values) != 1 or not values[0]:
        raise InstallError(f"{skill_md}: frontmatter must contain exactly one scalar name")
    return values[0]


def transform_frontmatter_for_profile(
    data: bytes,
    profile: ExportProfile,
    source: str = "SKILL.md",
) -> tuple[bytes, tuple[str, ...]]:
    """Move profile-declared top-level keys into allowed ``metadata``."""
    frontmatter, body, newline = _frontmatter_lines(data, source)
    keys = _top_level_keys(frontmatter, source)
    allowed_input = set(profile.allowed_top_level_keys) | set(profile.keys_to_metadata)
    unexpected = sorted(key for _, key, _ in keys if key not in allowed_input)
    if unexpected:
        raise InstallError(
            f"{source}: frontmatter keys outside the {profile.harness} profile allow-list: "
            + ", ".join(unexpected)
        )

    to_move = [(index, key, value) for index, key, value in keys if key in profile.keys_to_metadata]
    if not to_move:
        return data, ()
    for _, key, value in to_move:
        if not value.strip():
            raise InstallError(f"{source}: cannot losslessly nest block-valued key {key}")

    metadata_matches = [(index, value) for index, key, value in keys if key == "metadata"]
    if metadata_matches and metadata_matches[0][1].strip():
        raise InstallError(f"{source}: inline/scalar metadata cannot be extended losslessly")

    move_indexes = {index for index, _, _ in to_move}
    output = [line for index, line in enumerate(frontmatter) if index not in move_indexes]
    nested = [f"  {key}: {value}{newline}" for _, key, value in to_move]
    if metadata_matches:
        metadata_original_index = metadata_matches[0][0]
        metadata_output_index = sum(1 for index in range(metadata_original_index + 1) if index not in move_indexes)
        output[metadata_output_index:metadata_output_index] = nested
    else:
        first_original_index = min(move_indexes)
        insertion_index = sum(1 for index in range(first_original_index) if index not in move_indexes)
        output[insertion_index:insertion_index] = [f"metadata:{newline}", *nested]

    transformed = (f"---{newline}" + "".join(output) + f"---{newline}" + "".join(body)).encode("utf-8")
    transformed_frontmatter, _, _ = _frontmatter_lines(transformed, source)
    transformed_keys = _top_level_keys(transformed_frontmatter, source)
    invalid = sorted(key for _, key, _ in transformed_keys if key not in profile.allowed_top_level_keys)
    if invalid:
        raise InstallError(f"{source}: transformed frontmatter remains invalid: {', '.join(invalid)}")
    return transformed, tuple(key for _, key, _ in to_move)


def transform_claude_ai_frontmatter(data: bytes, source: str = "SKILL.md") -> tuple[bytes, tuple[str, ...]]:
    """Apply the explicit, user-supplied Claude.ai compatibility profile."""
    return transform_frontmatter_for_profile(data, CLAUDE_AI_PROFILE, source)


def discover_skills(source_skills: Path, selected: Sequence[str] | None = None) -> list[Path]:
    source_skills = Path(source_skills)
    if not source_skills.is_dir():
        raise InstallError(f"canonical skills directory not found: {source_skills}")
    available = {
        child.name: child
        for child in source_skills.iterdir()
        if child.is_dir() and (child / "SKILL.md").is_file()
    }
    names = list(selected or sorted(available))
    if len(names) != len(set(names)):
        raise InstallError("duplicate --skill values are not allowed")
    invalid_names = [name for name in names if not SKILL_NAME_RE.fullmatch(name)]
    if invalid_names:
        raise InstallError("invalid skill name(s): " + ", ".join(invalid_names))
    missing = [name for name in names if name not in available]
    if missing:
        raise InstallError("requested skill(s) not found: " + ", ".join(missing))
    skills = [available[name] for name in names]
    for skill in skills:
        declared = frontmatter_name(skill / "SKILL.md")
        if declared != skill.name:
            raise InstallError(
                f"{skill / 'SKILL.md'}: frontmatter name {declared!r} != folder {skill.name!r}"
            )
    return skills


def default_targets(home: Path) -> dict[str, TargetSpec]:
    home = Path(home)
    return {
        "agents": TargetSpec("agents", home / ".agents" / "skills", False, "documented-canonical"),
        "claude": TargetSpec("claude", home / ".claude" / "skills", True, "documented-conditional"),
        "pi": TargetSpec("pi", home / ".pi" / "agent" / "skills", True, "documented-conditional"),
        "hermes": TargetSpec("hermes", home / ".hermes" / "skills", False, "documented-independent"),
    }


def parse_custom_targets(values: Sequence[str]) -> dict[str, TargetSpec]:
    custom: dict[str, TargetSpec] = {}
    for value in values:
        name, separator, raw_path = value.partition("=")
        if not separator or not name or not raw_path:
            raise InstallError(f"custom target must be NAME=PATH: {value!r}")
        if not SKILL_NAME_RE.fullmatch(name):
            raise InstallError(f"invalid custom target name: {name!r}")
        if name in DEFAULT_TARGET_ORDER or name in custom:
            raise InstallError(f"duplicate or reserved custom target name: {name}")
        custom[name] = TargetSpec(name, Path(raw_path).expanduser(), False, "user-specified")
    return custom


def select_targets(
    home: Path,
    requested: Sequence[str] | None,
    custom: Mapping[str, TargetSpec] | None = None,
) -> list[TargetSpec]:
    defaults = default_targets(home)
    custom = dict(custom or {})
    all_targets = {**defaults, **custom}
    if requested:
        names = list(requested)
    elif custom:
        # A custom target with no --target is intentionally custom-only.  This
        # prevents an exporter for Cursor/Buzz/etc. from also writing fleet homes.
        names = list(custom)
    else:
        names = list(DEFAULT_TARGET_ORDER)
    if len(names) != len(set(names)):
        raise InstallError("duplicate --target values are not allowed")
    unknown = [name for name in names if name not in all_targets]
    if unknown:
        raise InstallError("unknown target(s): " + ", ".join(unknown))
    return [all_targets[name] for name in names]


def _remove_path(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.exists():
        shutil.rmtree(path)


def _transactional_copy(source: Path, destination: Path, expected: TreeManifest) -> None:
    target_root = destination.parent
    target_root.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        raise InstallError(f"refusing to replace symlinked skill destination: {destination}")
    if destination.exists() and not destination.is_dir():
        raise InstallError(f"skill destination is not a directory: {destination}")

    staging_root = Path(tempfile.mkdtemp(prefix=f".{destination.name}.install-", dir=target_root))
    staged = staging_root / "payload"
    backup = target_root / f".{destination.name}.backup-{uuid.uuid4().hex}"
    moved_old = False
    moved_new = False
    try:
        shutil.copytree(source, staged, symlinks=True, copy_function=shutil.copy2)
        staged_manifest = tree_manifest(staged)
        if staged_manifest.sha256 != expected.sha256:
            raise InstallError(f"staged copy failed byte verification for {source.name}")
        if destination.exists():
            os.replace(destination, backup)
            moved_old = True
        try:
            os.replace(staged, destination)
            moved_new = True
            installed = tree_manifest(destination)
            if installed.sha256 != expected.sha256:
                raise InstallError(f"installed copy failed byte verification for {source.name}")
        except BaseException:
            if moved_new and destination.exists():
                _remove_path(destination)
                moved_new = False
            if moved_old and backup.exists() and not destination.exists():
                os.replace(backup, destination)
                moved_old = False
            raise
        if moved_old:
            _remove_path(backup)
            moved_old = False
    finally:
        if moved_old and backup.exists() and not destination.exists():
            os.replace(backup, destination)
        if backup.exists():
            _remove_path(backup)
        if staging_root.exists():
            shutil.rmtree(staging_root)


def _sync_skill(
    source: Path,
    target_root: Path,
    expected: TreeManifest,
    *,
    dry_run: bool,
    verify_only: bool,
) -> SkillResult:
    destination = target_root / source.name
    if destination.is_symlink():
        raise InstallError(f"refusing symlinked skill destination: {destination}")
    if not destination.exists():
        status = "missing" if verify_only else "would-install" if dry_run else "installed"
        result = SkillResult(source.name, status, expected.sha256, None, ("missing:<skill-directory>",))
        if not dry_run and not verify_only:
            _transactional_copy(source, destination, expected)
            result.destination_sha256 = expected.sha256
            result.differences = ()
        return result
    if not destination.is_dir():
        raise InstallError(f"skill destination is not a directory: {destination}")

    actual = tree_manifest(destination)
    if actual.sha256 == expected.sha256:
        return SkillResult(
            source.name,
            "verified" if verify_only else "unchanged",
            expected.sha256,
            actual.sha256,
        )
    differences = manifest_differences(expected, actual)
    status = "drift" if verify_only else "would-update" if dry_run else "updated"
    result = SkillResult(source.name, status, expected.sha256, actual.sha256, differences)
    if not dry_run and not verify_only:
        _transactional_copy(source, destination, expected)
        result.destination_sha256 = expected.sha256
    return result


def run_install(
    source_skills: Path,
    targets: Sequence[TargetSpec],
    selected_skills: Sequence[str] | None = None,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> InstallReport:
    """Install or verify skills. All inputs are validated before any write."""
    if dry_run and verify_only:
        raise InstallError("--dry-run and --verify-only are mutually exclusive")
    source_skills = Path(source_skills)
    skills = discover_skills(source_skills, selected_skills)
    expected = {skill.name: tree_manifest(skill) for skill in skills}

    for target in targets:
        validate_target_path(source_skills, target.path)
        if target.path.exists() and not target.path.is_dir():
            raise InstallError(f"target is not a directory: {target.name}={target.path}")

    report = InstallReport("install", True, dry_run, verify_only, [])
    seen_paths: dict[str, str] = {}
    for target in targets:
        path_text = str(target.path.expanduser().absolute())
        target_key = _path_key(target.path)
        if target_key in seen_paths:
            report.targets.append(
                TargetResult(
                    target.name,
                    path_text,
                    "covered",
                    target.provenance,
                    covered_by=seen_paths[target_key],
                )
            )
            continue
        seen_paths[target_key] = target.name

        exists = target.path.exists()
        if target.optional_if_absent and not exists:
            report.targets.append(
                TargetResult(target.name, path_text, "skipped-absent", target.provenance)
            )
            continue
        if verify_only and not exists:
            report.targets.append(
                TargetResult(
                    target.name,
                    path_text,
                    "missing-target",
                    target.provenance,
                    error="required target directory does not exist",
                )
            )
            report.success = False
            continue

        target_result = TargetResult(target.name, path_text, "ready", target.provenance)
        try:
            for skill in skills:
                target_result.skills.append(
                    _sync_skill(
                        skill,
                        target.path,
                        expected[skill.name],
                        dry_run=dry_run,
                        verify_only=verify_only,
                    )
                )
            failure_statuses = {"missing", "drift"}
            if any(skill.status in failure_statuses for skill in target_result.skills):
                target_result.status = "failed-verification"
                report.success = False
            elif dry_run and any(skill.status.startswith("would-") for skill in target_result.skills):
                target_result.status = "changes-planned"
            else:
                target_result.status = "ok"
        except (InstallError, OSError) as exc:
            target_result.status = "error"
            target_result.error = str(exc)
            report.errors.append(f"{target.name}: {exc}")
            report.success = False
        report.targets.append(target_result)
    return report


def _zip_tree(tree: Path, destination: Path, overrides: Mapping[str, bytes]) -> None:
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        files = sorted(path for path in tree.rglob("*") if path.is_file())
        for path in files:
            relative = path.relative_to(tree).as_posix()
            data = overrides.get(relative, path.read_bytes())
            info = zipfile.ZipInfo(relative, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)


def _exported_manifest(source: Path, transformed_skill_md: bytes) -> TreeManifest:
    entries: list[ManifestEntry] = []
    for path in sorted((item for item in source.rglob("*") if item.is_file()), key=lambda p: p.relative_to(source).as_posix()):
        relative = path.relative_to(source).as_posix()
        data = transformed_skill_md if relative == "SKILL.md" else path.read_bytes()
        entries.append(ManifestEntry(relative, len(data), _sha256_bytes(data)))
    frozen = tuple(entries)
    return TreeManifest(frozen, _manifest_digest(frozen))


def _build_profile_export(profile: ExportProfile, skills: Sequence[Path], output: Path) -> None:
    bundles: list[dict[str, object]] = []
    for skill in skills:
        symlinks = [path for path in skill.rglob("*") if path.is_symlink()]
        if symlinks:
            relative = symlinks[0].relative_to(skill).as_posix()
            raise InstallError(
                f"{skill.name}: compatibility export does not flatten symlink {relative}"
            )
        source_manifest = tree_manifest(skill)
        transformed, moved = transform_frontmatter_for_profile(
            (skill / "SKILL.md").read_bytes(), profile, str(skill / "SKILL.md")
        )
        exported_manifest = _exported_manifest(skill, transformed)
        bundle_name = f"{skill.name}.zip"
        bundle_path = output / bundle_name
        _zip_tree(skill, bundle_path, {"SKILL.md": transformed})
        bundle_bytes = bundle_path.read_bytes()
        bundles.append(
            {
                "skill": skill.name,
                "file": bundle_name,
                "bytes": len(bundle_bytes),
                "sha256": _sha256_bytes(bundle_bytes),
                "sourceManifestSha256": source_manifest.sha256,
                "exportedManifestSha256": exported_manifest.sha256,
                "transformedKeys": list(moved),
            }
        )

    manifest = {
        "schemaVersion": 1,
        "profile": profile.harness,
        "profileId": profile.identifier,
        "allowedFrontmatterKeys": list(profile.allowed_top_level_keys),
        "compatibilityAssumption": {
            "status": profile.assumption_status,
            "source": profile.assumption_source,
            "statement": profile.assumption,
        },
        "metadataTransform": {
            "movedKeys": list(profile.keys_to_metadata),
            "valuePreservation": "lexical scalar value preserved",
            "invocationSemantics": "not asserted",
            "note": profile.semantics_note,
        },
        "canonicalMutation": False,
        "bundles": bundles,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _replace_export(staged: Path, output: Path, expected: TreeManifest) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    backup = output.parent / f".{output.name}.backup-{uuid.uuid4().hex}"
    moved_old = False
    moved_new = False
    try:
        if output.is_symlink():
            raise InstallError(f"refusing to replace symlinked export output: {output}")
        if output.exists():
            os.replace(output, backup)
            moved_old = True
        try:
            os.replace(staged, output)
            moved_new = True
            if tree_manifest(output).sha256 != expected.sha256:
                raise InstallError("written export failed byte verification")
        except BaseException:
            if moved_new and output.exists():
                _remove_path(output)
                moved_new = False
            if moved_old and backup.exists() and not output.exists():
                os.replace(backup, output)
                moved_old = False
            raise
        if moved_old:
            _remove_path(backup)
            moved_old = False
    finally:
        if moved_old and backup.exists() and not output.exists():
            os.replace(backup, output)
        if backup.exists():
            _remove_path(backup)


def run_profile_export(
    profile: ExportProfile,
    source_skills: Path,
    output: Path,
    selected_skills: Sequence[str] | None = None,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> InstallReport:
    if dry_run and verify_only:
        raise InstallError("--dry-run and --verify-only are mutually exclusive")
    source_skills = Path(source_skills)
    output = Path(output)
    validate_target_path(source_skills, output)
    if output.is_symlink():
        raise InstallError(f"refusing symlinked export output: {output}")
    if output.exists() and not output.is_dir():
        raise InstallError(f"export output is not a directory: {output}")
    skills = discover_skills(source_skills, selected_skills)

    with tempfile.TemporaryDirectory(prefix=f"idc-{profile.identifier}-export-") as temporary:
        staged = Path(temporary) / "payload"
        staged.mkdir()
        _build_profile_export(profile, skills, staged)
        expected = tree_manifest(staged)
        actual = tree_manifest(output) if output.exists() else None
        differences = manifest_differences(expected, actual) if actual else ("missing:<export-directory>",)
        if actual and actual.sha256 == expected.sha256:
            skill_result = SkillResult("<export>", "verified" if verify_only else "unchanged", expected.sha256, actual.sha256)
            status = "ok"
            success = True
        elif verify_only:
            skill_result = SkillResult("<export>", "drift" if actual else "missing", expected.sha256, actual.sha256 if actual else None, differences)
            status = "failed-verification"
            success = False
        elif dry_run:
            skill_result = SkillResult("<export>", "would-update" if actual else "would-install", expected.sha256, actual.sha256 if actual else None, differences)
            status = "changes-planned"
            success = True
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            sibling_stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.export-", dir=output.parent))
            payload = sibling_stage / "payload"
            try:
                shutil.copytree(staged, payload, copy_function=shutil.copy2)
                if tree_manifest(payload).sha256 != expected.sha256:
                    raise InstallError("staged export failed byte verification")
                _replace_export(payload, output, expected)
            finally:
                if sibling_stage.exists():
                    shutil.rmtree(sibling_stage)
            final_differences = differences if actual else ()
            skill_result = SkillResult(
                "<export>",
                "updated" if actual else "installed",
                expected.sha256,
                expected.sha256,
                final_differences,
            )
            status = "ok"
            success = True

    target = TargetResult(
        f"{profile.identifier}-export",
        str(output.absolute()),
        status,
        "user-specified-export",
        skills=[skill_result],
    )
    return InstallReport(
        "export-claude-ai" if profile is CLAUDE_AI_PROFILE else f"export-{profile.identifier}",
        success,
        dry_run,
        verify_only,
        [target],
        assumption=profile.assumption + "; " + profile.semantics_note,
    )


def run_claude_ai_export(
    source_skills: Path,
    output: Path,
    selected_skills: Sequence[str] | None = None,
    *,
    dry_run: bool = False,
    verify_only: bool = False,
) -> InstallReport:
    """Run the Claude.ai profile without mutating canonical skills."""
    return run_profile_export(
        CLAUDE_AI_PROFILE,
        source_skills,
        output,
        selected_skills,
        dry_run=dry_run,
        verify_only=verify_only,
    )


def _add_common_mode_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--skill", action="append", help="operate on one named skill; repeatable")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report writes without changing targets")
    mode.add_argument("--verify-only", action="store_true", help="fail on missing or byte-drifted outputs")
    parser.add_argument("--json", action="store_true", help="emit the complete machine-readable report")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="repository root (default: parent of scripts/)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    install = subparsers.add_parser("install", help="byte-preserving native fleet/custom install")
    install.add_argument(
        "--target",
        action="append",
        help="agents|claude|pi|hermes or a name declared with --custom-target; repeatable",
    )
    install.add_argument(
        "--custom-target",
        action="append",
        default=[],
        metavar="NAME=PATH",
        help="explicit harness target; with no --target, custom targets are custom-only",
    )
    install.add_argument("--home", type=Path, default=Path.home(), help=argparse.SUPPRESS)
    _add_common_mode_flags(install)

    export = subparsers.add_parser(
        "export-claude-ai",
        help="historical supplied-snapshot bundles; current upload acceptance unverified",
        description=(
            "Export deterministic ZIP bundles for a user-supplied claude.ai prior-upload "
            "snapshot captured 2026-08-11. It is not an official current specification; "
            "current upload acceptance is unverified. Moved values survive as metadata; "
            "invocation behavior is not asserted."
        ),
    )
    export.add_argument("--output", type=Path, required=True, help="separate export directory")
    _add_common_mode_flags(export)
    return parser


def _print_human(report: InstallReport) -> None:
    print(f"mode={report.mode} success={str(report.success).lower()}")
    if report.assumption:
        print(f"assumption={report.assumption}")
    for target in report.targets:
        detail = f" covered-by={target.covered_by}" if target.covered_by else ""
        print(f"target={target.name} status={target.status} path={target.path}{detail}")
        if target.error:
            print(f"  error={target.error}")
        for skill in target.skills:
            print(
                f"  skill={skill.skill} status={skill.status} "
                f"source-sha256={skill.source_sha256} "
                f"destination-sha256={skill.destination_sha256 or '-'}"
            )
            for difference in skill.differences:
                print(f"    drift={difference}")
    for error in report.errors:
        print(f"error={error}", file=sys.stderr)


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        source_skills = args.repo_root.resolve() / "skills"
        if args.command == "install":
            custom = parse_custom_targets(args.custom_target)
            targets = select_targets(args.home, args.target, custom)
            report = run_install(
                source_skills,
                targets,
                args.skill,
                dry_run=args.dry_run,
                verify_only=args.verify_only,
            )
        else:
            report = run_claude_ai_export(
                source_skills,
                args.output,
                args.skill,
                dry_run=args.dry_run,
                verify_only=args.verify_only,
            )
    except (InstallError, OSError) as exc:
        if getattr(args, "json", False):
            print(json.dumps({"mode": args.command, "success": False, "errors": [str(exc)]}, sort_keys=True))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    else:
        _print_human(report)
    return 0 if report.success else 1


if __name__ == "__main__":
    raise SystemExit(main())
