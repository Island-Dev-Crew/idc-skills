#!/usr/bin/env python3
"""Signed, fail-closed integrity gate for the IDC Skills Forge.

The release profile binds all 50 registered skill trees, security-control files,
the external-reference set, and denied fetch/execute findings to one canonical
manifest signed by the 1Password-held Forge key. A passing repository check is
necessary before installation or skill invocation. It is not a sandbox and it
does not make permitted remote content or a signed author trustworthy.

Bootstrap is deliberately external: a consumer must first compare the public
key fingerprint with the trusted, out-of-band fingerprint documented below and
verify the detached signature with the system OpenSSH client. Code inside an
untrusted repository cannot establish its own root of trust.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


MANIFEST_SCHEMA = "idc-skill-integrity/v2"
POLICY_SCHEMA = "idc-skill-integrity-policy/v1"
SIGN_NAMESPACE = "file"
SIGN_IDENTITY = "idc-skills"
EXPECTED_SIGNING_FINGERPRINT = "SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA"
MAX_REMOTE_BYTES = 4 * 1024 * 1024
MAX_MANIFEST_BYTES = 64 * 1024 * 1024
MAX_ANCHOR_BYTES = 64 * 1024
MAX_SIGNATURE_BYTES = 1024 * 1024

REQUIRED_RELEASE_CONTROL_FILES = (
    ".gitattributes",
    ".github/workflows/validate.yml",
    "AGENTS.md",
    "CONTEXT.md",
    "integrity/README.md",
    "integrity/policy.json",
    "keys/allowed_signers",
    "keys/idc-skills-signing.pub",
    "scripts/install.py",
    "scripts/install.sh",
    "scripts/pretooluse-skill-integrity.py",
    "scripts/reaccept.py",
    "scripts/setup-signing-wizard.sh",
    "scripts/skill_integrity.py",
    "scripts/test-skill-integrity.sh",
    "skills/registry.json",
    "tests/test_install.py",
    "tests/test_security_scripts.py",
    "tests/test_skill_integrity.py",
)

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
NON_HTTP_REMOTE_RE = re.compile(
    r"(?:(?:git\+|ssh|git|ftp)://[^\s<>\"'`]+|git@[A-Za-z0-9._-]+:[^\s<>\"'`]+)",
    re.IGNORECASE,
)
NETWORK_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("fetch", re.compile(r"\b(?:curl|wget|fetch)\b|\bInvoke-WebRequest\b|\biwr\b", re.I)),
    ("package-network", re.compile(r"\b(?:pip(?:3)?\s+install|npm\s+(?:install|i|ci|exec)|pnpm\s+(?:add|install|exec)|yarn\s+(?:add|install|dlx)|npx\b|uvx\b|uv\s+sync\b|cargo\s+install\b|go\s+install\b|brew\s+install\b|apt-get\s+install\b)", re.I)),
    ("git-network", re.compile(r"\bgit\s+(?:clone|fetch|pull|submodule\s+update)\b", re.I)),
    ("language-network", re.compile(r"\b(?:requests|httpx)\.(?:get|post|request)\s*\(|urllib\.request|\bfetch\s*\(", re.I)),
    ("browser-open", re.compile(r"\b(?:open_url|webbrowser\.open)\b", re.I)),
)
DENIED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "fetch-pipe-interpreter",
        re.compile(
            r"\b(?:curl|wget|fetch)\b[^\n]*(?:\||\|&)[^\n]*\b(?:sh|bash|zsh|fish|python(?:3)?|perl|ruby|node|pwsh|powershell)\b",
            re.I,
        ),
    ),
    (
        "process-substitution-exec",
        re.compile(
            r"\b(?:source|\.|sh|bash|zsh|python(?:3)?|perl|ruby|node)\s+<\([^\n]*(?:curl|wget|fetch)\b",
            re.I,
        ),
    ),
    (
        "dynamic-fetch-exec",
        re.compile(
            r"\b(?:eval|Invoke-Expression|iex)\b[^\n]*(?:curl|wget|fetch|Invoke-WebRequest|iwr)\b",
            re.I,
        ),
    ),
    (
        "download-to-file",
        re.compile(
            r"\b(?:curl\b[^\n]*(?:\s-o\s|\s--output(?:=|\s))|wget\b[^\n]*(?:\s-O\s|\s--output-document(?:=|\s))|(?:Invoke-WebRequest|iwr)\b[^\n]*\s-OutFile(?:\s|:))",
            re.I,
        ),
    ),
    (
        "network-package-execution",
        re.compile(
            r"\b(?:npx\b|uvx\b|pip(?:3)?\s+install\b|npm\s+(?:install|i|ci|exec)\b|pnpm\s+(?:add|install|exec)\b|yarn\s+(?:add|install|dlx)\b|uv\s+sync\b|cargo\s+install\b|go\s+install\b|brew\s+install\b|apt-get\s+install\b)",
            re.I,
        ),
    ),
)


class IntegrityError(RuntimeError):
    """A deterministic integrity or policy failure."""


def sha256_bytes(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(128 * 1024), b""):
            digest.update(block)
    return "sha256:" + digest.hexdigest()


def canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise IntegrityError(f"missing {label}: {path}") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"invalid {label}: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise IntegrityError(f"{label} must be a JSON object: {path}")
    return value


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
    except ValueError:
        return False
    return True


def _trim_url(value: str) -> str:
    return value.rstrip(".,;:!?)]}")


def _line_hash(text: str) -> str:
    normalized = " ".join(text.strip().split())
    return sha256_bytes(normalized.encode("utf-8"))


def _preview(text: str, limit: int = 240) -> str:
    normalized = " ".join(text.strip().split())
    return normalized if len(normalized) <= limit else normalized[: limit - 1] + "…"


def _assert_path_set_portable(paths: Iterable[str], label: str) -> None:
    seen_casefold: dict[str, str] = {}
    seen_nfc: dict[str, str] = {}
    for path in paths:
        case_key = path.casefold()
        nfc_key = unicodedata.normalize("NFC", path)
        if case_key in seen_casefold and seen_casefold[case_key] != path:
            raise IntegrityError(
                f"{label} has a case-colliding path: {seen_casefold[case_key]!r} and {path!r}"
            )
        if nfc_key in seen_nfc and seen_nfc[nfc_key] != path:
            raise IntegrityError(
                f"{label} has a Unicode-normalization collision: {seen_nfc[nfc_key]!r} and {path!r}"
            )
        seen_casefold[case_key] = path
        seen_nfc[nfc_key] = path


def _walk_regular_files(root: Path) -> list[Path]:
    if not root.is_dir() or root.is_symlink():
        raise IntegrityError(f"expected a real directory, not a symlink: {root}")
    files: list[Path] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            candidate = current_path / name
            if candidate.is_symlink():
                raise IntegrityError(f"symlinked directories are denied: {candidate}")
        for name in names:
            candidate = current_path / name
            try:
                mode = candidate.lstat().st_mode
            except FileNotFoundError as exc:
                raise IntegrityError(f"file changed during enumeration: {candidate}") from exc
            if stat.S_ISLNK(mode):
                raise IntegrityError(f"symlinked files are denied: {candidate}")
            if not stat.S_ISREG(mode):
                raise IntegrityError(f"non-regular files are denied: {candidate}")
            files.append(candidate)
    relative = [path.relative_to(root).as_posix() for path in files]
    _assert_path_set_portable(relative, str(root))
    return sorted(files, key=lambda item: item.relative_to(root).as_posix())


def _file_record(path: Path) -> dict[str, Any]:
    before = path.stat()
    digest = sha256_file(path)
    after = path.stat()
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
        after.st_dev,
        after.st_ino,
        after.st_size,
        after.st_mtime_ns,
    ):
        raise IntegrityError(f"file changed while hashing: {path}")
    return {"sha256": digest, "size": before.st_size}


def _scan_text(data: bytes, relative_path: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise IntegrityError(
            f"non-UTF-8 or opaque skill content is denied until explicitly reviewable: {relative_path}"
        ) from exc
    if "\x00" in text:
        raise IntegrityError(
            f"NUL-bearing or wide-encoded skill content is denied until explicitly reviewable: {relative_path}"
        )
    references: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    denied: list[dict[str, Any]] = []
    non_http: list[str] = []
    logical_text = text.replace("\\\r\n", " ").replace("\\\n", " ")
    for line_number, line in enumerate(logical_text.splitlines(), start=1):
        for match in URL_RE.finditer(line):
            references.append(
                {"url": _trim_url(match.group(0)), "path": relative_path, "line": line_number}
            )
        for match in NON_HTTP_REMOTE_RE.finditer(line):
            non_http.append(_trim_url(match.group(0)))
        for kind, pattern in NETWORK_PATTERNS:
            if pattern.search(line):
                commands.append(
                    {
                        "kind": kind,
                        "path": relative_path,
                        "line": line_number,
                        "sha256": _line_hash(line),
                        "preview": _preview(line),
                    }
                )
        for kind, pattern in DENIED_PATTERNS:
            if pattern.search(line):
                denied.append(
                    {
                        "kind": kind,
                        "path": relative_path,
                        "line": line_number,
                        "sha256": _line_hash(line),
                        "preview": _preview(line),
                    }
                )
    return references, commands, denied, sorted(set(non_http))


def _load_registry(skills_dir: Path) -> tuple[dict[str, Any], list[str]]:
    registry = _load_json(skills_dir / "registry.json", "skills registry")
    records = registry.get("skills")
    if not isinstance(records, list):
        raise IntegrityError("skills/registry.json .skills must be an array")
    names: list[str] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict) or not isinstance(record.get("name"), str):
            raise IntegrityError(f"invalid registry skill at index {index}")
        if record.get("path") != record["name"]:
            raise IntegrityError(f"registry name/path mismatch at index {index}")
        names.append(record["name"])
    if len(names) != len(set(names)):
        raise IntegrityError("skills registry contains duplicate names")
    return registry, sorted(names)


def scan_skills(skills_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    registry, registered = _load_registry(skills_dir)
    actual = sorted(
        child.name
        for child in skills_dir.iterdir()
        if child.is_dir() and not child.is_symlink()
    )
    symlinked = sorted(child.name for child in skills_dir.iterdir() if child.is_symlink())
    if symlinked:
        raise IntegrityError("symlinked top-level skill entries are denied: " + ", ".join(symlinked))
    if registered != actual:
        missing = sorted(set(registered) - set(actual))
        extra = sorted(set(actual) - set(registered))
        raise IntegrityError(f"registry/directory mismatch: missing={missing} extra={extra}")

    skills: dict[str, Any] = {}
    for name in registered:
        directory = skills_dir / name
        files: dict[str, Any] = {}
        occurrences: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        denied: list[dict[str, Any]] = []
        non_http: set[str] = set()
        for path in _walk_regular_files(directory):
            relative = path.relative_to(directory).as_posix()
            data = path.read_bytes()
            files[relative] = {"sha256": sha256_bytes(data), "size": len(data)}
            refs, found_commands, found_denied, found_non_http = _scan_text(data, relative)
            occurrences.extend(refs)
            commands.extend(found_commands)
            denied.extend(found_denied)
            non_http.update(found_non_http)
        if "SKILL.md" not in files:
            raise IntegrityError(f"registered skill is missing SKILL.md: {name}")
        grouped: dict[str, list[dict[str, Any]]] = {}
        for occurrence in occurrences:
            grouped.setdefault(occurrence["url"], []).append(
                {"path": occurrence["path"], "line": occurrence["line"]}
            )
        references = [
            {"url": url, "occurrences": sorted(items, key=lambda item: (item["path"], item["line"]))}
            for url, items in sorted(grouped.items())
        ]
        skills[name] = {
            "files": dict(sorted(files.items())),
            "externalReferences": references,
            "networkCommands": sorted(commands, key=lambda item: (item["path"], item["line"], item["kind"])),
            "deniedPatterns": sorted(denied, key=lambda item: (item["path"], item["line"], item["kind"])),
            "nonHttpRemoteReferences": sorted(non_http),
        }
    return registry, skills


def _validate_policy(policy: Mapping[str, Any], registered: Sequence[str]) -> None:
    if policy.get("schema") != POLICY_SCHEMA:
        raise IntegrityError(f"policy schema must be {POLICY_SCHEMA!r}")
    profile = policy.get("profile")
    if profile not in {"release", "fixture"}:
        raise IntegrityError("policy profile must be 'release' or 'fixture'")
    expected = policy.get("expectedSkills")
    if not isinstance(expected, list) or not all(isinstance(item, str) for item in expected):
        raise IntegrityError("policy expectedSkills must be an array of names")
    if sorted(expected) != sorted(registered):
        raise IntegrityError("policy expectedSkills does not match the registry")
    expected_count = policy.get("expectedSkillCount")
    if expected_count != len(registered):
        raise IntegrityError(
            f"policy expectedSkillCount={expected_count!r}, registry has {len(registered)}"
        )
    if profile == "release":
        if len(registered) != 50:
            raise IntegrityError(f"release profile requires exactly 50 skills, found {len(registered)}")
        if policy.get("expectedSigningFingerprint") != EXPECTED_SIGNING_FINGERPRINT:
            raise IntegrityError("release policy signing fingerprint is not the trusted Forge fingerprint")


def _policy_reference_map(policy: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    entries = policy.get("externalReferences")
    if not isinstance(entries, list):
        raise IntegrityError("policy externalReferences must be an array")
    result: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict) or not isinstance(entry.get("url"), str):
            raise IntegrityError(f"invalid policy externalReferences[{index}]")
        url = entry["url"]
        if url in result:
            raise IntegrityError(f"duplicate policy reference: {url}")
        classification = entry.get("classification")
        if classification not in {"informational", "api-endpoint", "runtime-instruction"}:
            raise IntegrityError(f"invalid classification for {url}: {classification!r}")
        skills = entry.get("allowedSkills")
        if not isinstance(skills, list) or not skills or not all(isinstance(item, str) for item in skills):
            raise IntegrityError(f"policy reference {url} requires allowedSkills")
        if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
            raise IntegrityError(f"policy reference {url} requires a rationale")
        if classification == "runtime-instruction":
            pin = entry.get("sha256")
            if not isinstance(pin, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", pin):
                raise IntegrityError(f"runtime instruction {url} requires a SHA-256 content pin")
            if not isinstance(entry.get("finalUrl"), str):
                raise IntegrityError(f"runtime instruction {url} requires finalUrl")
            if policy.get("profile") == "release":
                source = urllib.parse.urlparse(url)
                final = urllib.parse.urlparse(entry["finalUrl"])
                if source.scheme.lower() != "https" or not source.netloc:
                    raise IntegrityError(
                        f"release runtime instruction must use HTTPS: {url}"
                    )
                if final.scheme.lower() != "https" or not final.netloc:
                    raise IntegrityError(
                        f"release runtime instruction finalUrl must use HTTPS: {url}"
                    )
                if "allowInsecureForFixture" in entry:
                    raise IntegrityError(
                        f"release runtime instruction may not use fixture transport escape: {url}"
                    )
        result[url] = dict(entry)
    return result


def _exception_key(item: Mapping[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("skill", "")),
        str(item.get("path", "")),
        str(item.get("kind", "")),
        str(item.get("sha256", "")),
    )


def _validate_denied_exceptions(policy: Mapping[str, Any], skills: Mapping[str, Any]) -> list[dict[str, Any]]:
    entries = policy.get("deniedPatternExceptions", [])
    if not isinstance(entries, list):
        raise IntegrityError("policy deniedPatternExceptions must be an array")
    approved: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise IntegrityError(f"invalid deniedPatternExceptions[{index}]")
        key = _exception_key(entry)
        if not all(key) or key in approved:
            raise IntegrityError(f"invalid or duplicate denied-pattern exception at index {index}")
        if not isinstance(entry.get("rationale"), str) or not entry["rationale"].strip():
            raise IntegrityError(f"denied-pattern exception {key} requires a rationale")
        approved[key] = dict(entry)
    used: set[tuple[str, str, str, str]] = set()
    materialized: list[dict[str, Any]] = []
    for skill_name, skill in skills.items():
        for finding in skill["deniedPatterns"]:
            key = (skill_name, finding["path"], finding["kind"], finding["sha256"])
            exception = approved.get(key)
            if exception is None:
                raise IntegrityError(
                    "denied fetch/execute pattern is not reviewed: "
                    f"{skill_name}/{finding['path']}:{finding['line']} "
                    f"kind={finding['kind']} sha256={finding['sha256']} preview={finding['preview']!r}"
                )
            used.add(key)
            materialized.append(
                {
                    "skill": skill_name,
                    **finding,
                    "classification": exception.get("classification", "reviewed-example"),
                    "rationale": exception["rationale"],
                }
            )
    unused = sorted(set(approved) - used)
    if unused:
        raise IntegrityError(f"stale denied-pattern exceptions are forbidden: {unused}")
    return sorted(materialized, key=lambda item: (item["skill"], item["path"], item["line"], item["kind"]))


def _fetch_remote(entry: Mapping[str, Any]) -> tuple[str, str, int]:
    url = str(entry["url"])
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" and not entry.get("allowInsecureForFixture", False):
        raise IntegrityError(f"runtime instruction must use HTTPS: {url}")
    maximum = int(entry.get("maxBytes", MAX_REMOTE_BYTES))
    if maximum < 1 or maximum > MAX_REMOTE_BYTES:
        raise IntegrityError(f"invalid maxBytes for {url}: {maximum}")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "IDC-Skills-Integrity/2.0.2", "Accept-Encoding": "identity"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(maximum + 1)
            final_url = response.geturl()
    except (OSError, urllib.error.URLError, urllib.error.HTTPError) as exc:
        raise IntegrityError(f"remote fetch failed for {url}: {exc}") from exc
    if len(data) > maximum:
        raise IntegrityError(f"remote content exceeds {maximum} bytes: {url}")
    return sha256_bytes(data), final_url, len(data)


def _control_files(repo_root: Path, policy: Mapping[str, Any]) -> dict[str, Any]:
    configured = policy.get("controlFiles", [])
    if not isinstance(configured, list) or not all(isinstance(item, str) for item in configured):
        raise IntegrityError("policy controlFiles must be an array of paths")
    required = set(REQUIRED_RELEASE_CONTROL_FILES if policy.get("profile") == "release" else ())
    paths = sorted(required | set(configured))
    _assert_path_set_portable(paths, "control files")
    records: dict[str, Any] = {}
    for relative in paths:
        relative_path = Path(relative)
        if (
            relative_path.is_absolute()
            or not relative_path.parts
            or any(part in {"", ".", ".."} for part in relative_path.parts)
        ):
            raise IntegrityError(f"unsafe control-file path: {relative!r}")
        path = repo_root / relative_path
        try:
            resolved = path.resolve(strict=True)
        except OSError as exc:
            raise IntegrityError(f"missing control file: {relative}") from exc
        if not _is_relative_to(resolved, repo_root) or resolved != path.absolute():
            raise IntegrityError(f"control file escapes the repository or crosses a symlink: {relative}")
        if path.is_symlink() or not path.is_file():
            raise IntegrityError(f"missing or symlinked control file: {relative}")
        records[relative] = _file_record(path)
    return records


def build_manifest(repo_root: Path, skills_dir: Path, policy_path: Path, *, fetch_remotes: bool) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    skills_dir = skills_dir.resolve()
    policy_path = policy_path.resolve()
    if not _is_relative_to(skills_dir, repo_root):
        raise IntegrityError("skills directory must be inside repo root")
    if not _is_relative_to(policy_path, repo_root):
        raise IntegrityError("policy must be inside repo root")
    policy = _load_json(policy_path, "integrity policy")
    registry, skills = scan_skills(skills_dir)
    registered = sorted(skills)
    _validate_policy(policy, registered)
    reference_policy = _policy_reference_map(policy)

    used_references: set[str] = set()
    remote_observations: list[dict[str, Any]] = []
    for skill_name, skill in skills.items():
        if skill["nonHttpRemoteReferences"]:
            raise IntegrityError(
                f"non-HTTP remote references are denied in {skill_name}: "
                + ", ".join(skill["nonHttpRemoteReferences"])
            )
        enriched: list[dict[str, Any]] = []
        for reference in skill["externalReferences"]:
            url = reference["url"]
            rule = reference_policy.get(url)
            if rule is None:
                raise IntegrityError(f"unclassified external reference: {skill_name}: {url}")
            if skill_name not in rule["allowedSkills"]:
                raise IntegrityError(f"external reference is not allowed for {skill_name}: {url}")
            used_references.add(url)
            item = {
                **reference,
                "classification": rule["classification"],
                "rationale": rule["rationale"],
            }
            if rule["classification"] == "runtime-instruction":
                item["sha256"] = rule["sha256"]
                item["finalUrl"] = rule["finalUrl"]
                if "maxBytes" in rule:
                    item["maxBytes"] = rule["maxBytes"]
                if rule.get("allowInsecureForFixture", False):
                    item["allowInsecureForFixture"] = True
                if fetch_remotes:
                    digest, final_url, size = _fetch_remote(rule)
                    if digest != rule["sha256"]:
                        raise IntegrityError(
                            f"remote content drift for {url}: expected {rule['sha256']}, got {digest}"
                        )
                    if final_url != rule["finalUrl"]:
                        raise IntegrityError(
                            f"remote redirect drift for {url}: expected {rule['finalUrl']}, got {final_url}"
                        )
                    remote_observations.append(
                        {"url": url, "sha256": digest, "finalUrl": final_url, "size": size}
                    )
            enriched.append(item)
        skill["externalReferences"] = enriched

    unused_references = sorted(set(reference_policy) - used_references)
    if unused_references:
        raise IntegrityError(f"stale external-reference policy entries are forbidden: {unused_references}")
    approved_denied = _validate_denied_exceptions(policy, skills)
    controls = _control_files(repo_root, policy)
    policy_relative = policy_path.relative_to(repo_root).as_posix()
    return {
        "schema": MANIFEST_SCHEMA,
        "profile": policy["profile"],
        "release": registry.get("release"),
        "anchor": {
            "expectedFingerprint": policy.get("expectedSigningFingerprint"),
            "identity": SIGN_IDENTITY,
            "namespace": SIGN_NAMESPACE,
        },
        "policy": {"path": policy_relative, "sha256": sha256_file(policy_path)},
        "skillCount": len(skills),
        "skillNames": registered,
        "skills": dict(sorted(skills.items())),
        "controlFiles": controls,
        "approvedDeniedPatterns": approved_denied,
        "remoteObservations": sorted(remote_observations, key=lambda item: item["url"]),
    }


def _fingerprint_public_key(key_data: str) -> str:
    process = subprocess.run(
        ["ssh-keygen", "-lf", "-"],
        input=key_data,
        text=True,
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        raise IntegrityError(f"ssh-keygen rejected public key: {(process.stderr or process.stdout).strip()}")
    fields = process.stdout.split()
    if len(fields) < 2:
        raise IntegrityError("ssh-keygen returned no public-key fingerprint")
    return fields[1]


def _read_regular_snapshot(path: Path, label: str, max_bytes: int) -> bytes:
    """Read one bounded regular-file snapshot without following a final symlink."""

    try:
        path_stat = os.lstat(path)
    except OSError as exc:
        raise IntegrityError(f"cannot inspect {label}: {path}: {exc}") from exc
    if stat.S_ISLNK(path_stat.st_mode):
        raise IntegrityError(f"refusing symlinked {label}: {path}")
    if not stat.S_ISREG(path_stat.st_mode):
        raise IntegrityError(f"{label} must be a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise IntegrityError(f"cannot open {label}: {path}: {exc}") from exc
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise IntegrityError(f"{label} must be a regular file: {path}")
        if (path_stat.st_dev, path_stat.st_ino) != (file_stat.st_dev, file_stat.st_ino):
            raise IntegrityError(f"{label} path changed before it could be captured: {path}")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            data = stream.read(max_bytes + 1)
    finally:
        os.close(descriptor)
    if len(data) > max_bytes:
        raise IntegrityError(f"{label} exceeds {max_bytes} bytes: {path}")
    return data


def _decode_anchor(data: bytes, label: str) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise IntegrityError(f"invalid UTF-8 in {label}") from exc


def _validate_anchor_bytes(
    public_key_data: bytes,
    allowed_signers_data: bytes,
    expected_fingerprint: str,
) -> None:
    try:
        public_fields = _decode_anchor(public_key_data, "public signing key").strip().split()
    except IntegrityError as exc:
        raise IntegrityError("invalid public signing key") from exc
    if len(public_fields) < 2:
        raise IntegrityError("invalid public signing key")
    public_material = " ".join(public_fields[:2]) + "\n"
    public_fingerprint = _fingerprint_public_key(public_material)
    if public_fingerprint != expected_fingerprint:
        raise IntegrityError(
            f"public-key fingerprint mismatch: expected {expected_fingerprint}, got {public_fingerprint}"
        )
    lines = [
        line.strip()
        for line in _decode_anchor(allowed_signers_data, "allowed_signers").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if len(lines) != 1:
        raise IntegrityError("allowed_signers must contain exactly one non-comment signer")
    fields = lines[0].split()
    if len(fields) < 3 or SIGN_IDENTITY not in fields[0].split(","):
        raise IntegrityError(f"allowed_signers must bind principal {SIGN_IDENTITY!r}")
    allowed_material = " ".join(fields[1:3]) + "\n"
    allowed_fingerprint = _fingerprint_public_key(allowed_material)
    if allowed_fingerprint != expected_fingerprint or allowed_material != public_material:
        raise IntegrityError(
            "allowed_signers key does not match the trusted public signing key "
            f"({allowed_fingerprint})"
        )


def validate_anchor(public_key: Path, allowed_signers: Path, expected_fingerprint: str) -> None:
    """Validate one captured public-key and allowed-signers snapshot."""

    _validate_anchor_bytes(
        _read_regular_snapshot(public_key, "public signing key", MAX_ANCHOR_BYTES),
        _read_regular_snapshot(allowed_signers, "allowed_signers", MAX_ANCHOR_BYTES),
        expected_fingerprint,
    )


def _verify_signature_bytes(
    manifest_data: bytes,
    signature_data: bytes,
    allowed_signers_data: bytes,
) -> None:
    """Verify the exact bytes later parsed; never reopen caller-controlled paths."""

    try:
        with tempfile.TemporaryDirectory(prefix="idc-integrity-") as temporary:
            temporary_root = Path(temporary)
            os.chmod(temporary_root, 0o700)
            allowed_snapshot = temporary_root / "allowed_signers"
            signature_snapshot = temporary_root / "manifest.sig"
            allowed_snapshot.write_bytes(allowed_signers_data)
            signature_snapshot.write_bytes(signature_data)
            os.chmod(allowed_snapshot, 0o600)
            os.chmod(signature_snapshot, 0o600)
            process = subprocess.run(
                [
                    "ssh-keygen",
                    "-Y",
                    "verify",
                    "-f",
                    str(allowed_snapshot),
                    "-I",
                    SIGN_IDENTITY,
                    "-n",
                    SIGN_NAMESPACE,
                    "-s",
                    str(signature_snapshot),
                ],
                input=manifest_data,
                capture_output=True,
                check=False,
            )
    except FileNotFoundError as exc:
        raise IntegrityError("ssh-keygen is required for signature verification") from exc
    if process.returncode != 0:
        detail = (process.stderr or process.stdout).decode("utf-8", errors="replace").strip()
        raise IntegrityError(f"signature invalid: {detail}")


def _load_canonical_manifest_bytes(data: bytes) -> dict[str, Any]:
    try:
        manifest = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise IntegrityError(f"invalid integrity manifest: {exc}") from exc
    if not isinstance(manifest, dict):
        raise IntegrityError("integrity manifest must be a JSON object")
    if manifest.get("schema") != MANIFEST_SCHEMA:
        raise IntegrityError(f"manifest schema must be {MANIFEST_SCHEMA!r}")
    if data != canonical_bytes(manifest):
        raise IntegrityError("manifest JSON is not canonical")
    return manifest


def _load_canonical_manifest(path: Path) -> dict[str, Any]:
    return _load_canonical_manifest_bytes(
        _read_regular_snapshot(path, "integrity manifest", MAX_MANIFEST_BYTES)
    )


def _load_verified_manifest_snapshot(
    manifest_path: Path,
    public_key: Path,
    allowed_signers: Path,
    expected_fingerprint: str,
) -> dict[str, Any]:
    """Capture every signed input once, authenticate it, then parse those same bytes."""

    manifest_data = _read_regular_snapshot(
        manifest_path, "integrity manifest", MAX_MANIFEST_BYTES
    )
    signature_data = _read_regular_snapshot(
        Path(str(manifest_path) + ".sig"), "detached signature", MAX_SIGNATURE_BYTES
    )
    public_key_data = _read_regular_snapshot(
        public_key, "public signing key", MAX_ANCHOR_BYTES
    )
    allowed_signers_data = _read_regular_snapshot(
        allowed_signers, "allowed_signers", MAX_ANCHOR_BYTES
    )
    _validate_anchor_bytes(public_key_data, allowed_signers_data, expected_fingerprint)
    _verify_signature_bytes(manifest_data, signature_data, allowed_signers_data)
    return _load_canonical_manifest_bytes(manifest_data)


def _check_result(passed: bool, detail: str, failures: Sequence[str] = ()) -> dict[str, Any]:
    return {"pass": passed, "detail": detail, "failures": list(failures)}


def _compare_section(stored: Any, current: Any, label: str) -> list[str]:
    return [] if stored == current else [f"{label} differs from the signed manifest"]


def verify_repository(
    repo_root: Path,
    *,
    skills_dir: Path | None = None,
    manifest_path: Path | None = None,
    policy_path: Path | None = None,
    public_key: Path | None = None,
    allowed_signers: Path | None = None,
    expected_fingerprint: str = EXPECTED_SIGNING_FINGERPRINT,
    allow_fixture: bool = False,
    include_verified_manifest: bool = False,
) -> dict[str, Any]:
    """Return the five-check report; never raises for an ordinary gate failure."""

    repo_root = repo_root.resolve()
    skills_dir = (skills_dir or repo_root / "skills").resolve()
    manifest_path = (manifest_path or repo_root / "integrity" / "manifest.json").resolve()
    policy_path = (policy_path or repo_root / "integrity" / "policy.json").resolve()
    public_key = (public_key or repo_root / "keys" / "idc-skills-signing.pub").resolve()
    allowed_signers = (allowed_signers or repo_root / "keys" / "allowed_signers").resolve()
    checks: dict[str, dict[str, Any]] = {}
    stored: dict[str, Any] | None = None

    signature_failures: list[str] = []
    try:
        if expected_fingerprint != EXPECTED_SIGNING_FINGERPRINT and not allow_fixture:
            raise IntegrityError("release verification cannot override the trusted Forge fingerprint")
        stored = _load_verified_manifest_snapshot(
            manifest_path,
            public_key,
            allowed_signers,
            expected_fingerprint,
        )
        if stored.get("profile") != "release" and not allow_fixture:
            raise IntegrityError("fixture manifests cannot authorize installation or execution")
        if stored.get("anchor") != {
            "expectedFingerprint": expected_fingerprint,
            "identity": SIGN_IDENTITY,
            "namespace": SIGN_NAMESPACE,
        }:
            raise IntegrityError("signed manifest anchor metadata does not match the trusted anchor")
    except (IntegrityError, OSError, subprocess.SubprocessError) as exc:
        signature_failures.append(str(exc))
    checks["signature"] = _check_result(
        not signature_failures,
        "trusted fingerprint, signer binding, detached signature, and canonical manifest",
        signature_failures,
    )

    current: dict[str, Any] | None = None
    build_failure: str | None = None
    try:
        current = build_manifest(repo_root, skills_dir, policy_path, fetch_remotes=False)
    except (IntegrityError, OSError) as exc:
        build_failure = str(exc)

    local_failures: list[str] = []
    external_failures: list[str] = []
    denied_failures: list[str] = []
    if stored is None:
        local_failures.append("signed manifest unavailable for byte comparison")
        external_failures.append("signed manifest unavailable for reference comparison")
        denied_failures.append("signed manifest unavailable for denied-pattern comparison")
    if current is None:
        local_failures.append(build_failure or "current repository could not be analyzed")
        external_failures.append(build_failure or "current repository could not be analyzed")
        denied_failures.append(build_failure or "current repository could not be analyzed")
    if stored is not None and current is not None:
        for key in ("release", "anchor", "skillCount", "skillNames", "controlFiles", "policy"):
            local_failures.extend(_compare_section(stored.get(key), current.get(key), key))
        stored_files = {
            name: skill.get("files") for name, skill in stored.get("skills", {}).items()
        }
        current_files = {
            name: skill.get("files") for name, skill in current.get("skills", {}).items()
        }
        local_failures.extend(_compare_section(stored_files, current_files, "skill files"))
        for field in ("externalReferences", "networkCommands", "nonHttpRemoteReferences"):
            stored_values = {
                name: skill.get(field) for name, skill in stored.get("skills", {}).items()
            }
            current_values = {
                name: skill.get(field) for name, skill in current.get("skills", {}).items()
            }
            external_failures.extend(_compare_section(stored_values, current_values, field))
        denied_failures.extend(
            _compare_section(
                stored.get("approvedDeniedPatterns"),
                current.get("approvedDeniedPatterns"),
                "reviewed denied-pattern exceptions",
            )
        )

    checks["local_bytes"] = _check_result(
        not local_failures,
        "all registered skill bytes, inventory, policy, and security-control bytes",
        local_failures,
    )
    checks["external_reference_set"] = _check_result(
        not external_failures,
        "all HTTP(S) references and network-command occurrences are signed and classified",
        external_failures,
    )

    remote_failures: list[str] = []
    remote_checked = 0
    allowlisted_non_instruction = 0
    if stored is None:
        remote_failures.append("signed manifest unavailable for remote-pin verification")
    else:
        seen_runtime: set[str] = set()
        for skill in stored.get("skills", {}).values():
            for reference in skill.get("externalReferences", []):
                if reference.get("classification") != "runtime-instruction":
                    allowlisted_non_instruction += 1
                    continue
                url = reference.get("url")
                if not isinstance(url, str) or url in seen_runtime:
                    continue
                seen_runtime.add(url)
                remote_checked += 1
                try:
                    digest, final_url, _ = _fetch_remote(reference)
                    if digest != reference.get("sha256"):
                        raise IntegrityError(
                            f"remote content drift for {url}: expected {reference.get('sha256')}, got {digest}"
                        )
                    if final_url != reference.get("finalUrl"):
                        raise IntegrityError(
                            f"remote redirect drift for {url}: expected {reference.get('finalUrl')}, got {final_url}"
                        )
                except IntegrityError as exc:
                    remote_failures.append(str(exc))
    checks["remote_content_pins"] = _check_result(
        not remote_failures,
        f"pinned runtime instructions checked={remote_checked}; allowlisted non-instruction references={allowlisted_non_instruction}",
        remote_failures,
    )
    checks["fetch_execute_policy"] = _check_result(
        not denied_failures,
        "fetch/execute patterns are denied unless an exact signed, reviewed example is present",
        denied_failures,
    )

    # Close the observable in-verifier race: remote checks may take time, so a
    # writer could replace a file after its first hash but before this function
    # returns. Recompute the entire local manifest immediately before the
    # authorization decision. Mutation after this final read remains the
    # documented same-user post-check boundary and requires OS containment.
    try:
        final_snapshot = build_manifest(
            repo_root,
            skills_dir,
            policy_path,
            fetch_remotes=False,
        )
    except (IntegrityError, OSError) as exc:
        final_snapshot = None
        stability_failure = f"final repository snapshot failed: {exc}"
    else:
        stability_failure = (
            "repository bytes or policy changed during integrity verification"
            if current is None or final_snapshot != current
            else None
        )
    if stability_failure:
        checks["local_bytes"]["pass"] = False
        checks["local_bytes"]["failures"].append(stability_failure)

    passed_count = sum(1 for check in checks.values() if check["pass"])
    profile = stored.get("profile") if stored else None
    passed = passed_count == 5
    ready = (
        passed
        and profile == "release"
        and expected_fingerprint == EXPECTED_SIGNING_FINGERPRINT
        and stored is not None
        and stored.get("skillCount") == 50
    )
    report = {
        "schema": "idc-skill-integrity-report/v1",
        "pass": passed,
        "readyToRun": ready,
        "score": f"{passed_count}/5",
        "profile": profile,
        "skillsChecked": current.get("skillCount", 0) if current else 0,
        "manifest": str(manifest_path),
        "expectedSigningFingerprint": expected_fingerprint,
        "checks": checks,
    }
    if include_verified_manifest and stored is not None:
        report["_verifiedManifest"] = stored
    return report


def verify_skill_directory(directory: Path, expected_files: Mapping[str, Any]) -> list[str]:
    """Compare an installed/staged skill directory to its signed file map."""

    def capture() -> dict[str, Any]:
        return {
            path.relative_to(directory).as_posix(): _file_record(path)
            for path in _walk_regular_files(directory)
        }

    try:
        actual = capture()
        final_snapshot = capture()
    except (IntegrityError, OSError) as exc:
        return [str(exc)]
    failures: list[str] = []
    if final_snapshot != actual:
        failures.append("skill directory changed during byte verification")
    expected = dict(expected_files)
    for relative in sorted(set(expected) | set(actual)):
        if relative not in expected:
            failures.append(f"unexpected file: {relative}")
        elif relative not in actual:
            failures.append(f"missing file: {relative}")
        elif expected[relative] != actual[relative]:
            failures.append(f"byte drift: {relative}")
    return failures


def _safe_manifest_output(path: Path, skills_dir: Path) -> None:
    resolved = path.resolve()
    if _is_relative_to(resolved, skills_dir.resolve()):
        raise IntegrityError("manifest output may not be inside the canonical skills tree")
    if resolved.is_symlink():
        raise IntegrityError("refusing symlinked manifest output")


def cmd_manifest(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    skills_dir = (args.skills or repo_root / "skills").resolve()
    policy_path = (args.policy or repo_root / "integrity" / "policy.json").resolve()
    output = (args.out or repo_root / "integrity" / "manifest.json").resolve()
    try:
        _safe_manifest_output(output, skills_dir)
        manifest = build_manifest(repo_root, skills_dir, policy_path, fetch_remotes=True)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(canonical_bytes(manifest))
    except (IntegrityError, OSError) as exc:
        print(f"MANIFEST REFUSED — {exc}", file=sys.stderr)
        return 1
    references = sum(
        len(skill["externalReferences"]) for skill in manifest["skills"].values()
    )
    commands = sum(len(skill["networkCommands"]) for skill in manifest["skills"].values())
    print(
        f"MANIFEST OK — profile={manifest['profile']} skills={manifest['skillCount']} "
        f"references={references} networkCommands={commands} path={output}"
    )
    return 0


def cmd_sign(args: argparse.Namespace) -> int:
    repo_root = args.repo_root.resolve()
    manifest_path = (args.manifest or repo_root / "integrity" / "manifest.json").resolve()
    public_key = (args.public_key or repo_root / "keys" / "idc-skills-signing.pub").resolve()
    allowed_signers = (args.allowed_signers or repo_root / "keys" / "allowed_signers").resolve()
    try:
        manifest = _load_canonical_manifest(manifest_path)
        if manifest.get("profile") != "release":
            raise IntegrityError("only a release-profile manifest may be signed by this command")
        validate_anchor(public_key, allowed_signers, EXPECTED_SIGNING_FINGERPRINT)
        signature = Path(str(manifest_path) + ".sig")
        if signature.exists():
            if signature.is_symlink() or not signature.is_file():
                raise IntegrityError(f"refusing unsafe signature target: {signature}")
            signature.unlink()
        process = subprocess.run(
            [
                "ssh-keygen",
                "-Y",
                "sign",
                "-f",
                str(public_key),
                "-U",
                "-n",
                SIGN_NAMESPACE,
                str(manifest_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise IntegrityError(f"agent signing failed: {(process.stderr or process.stdout).strip()}")
        _load_verified_manifest_snapshot(
            manifest_path,
            public_key,
            allowed_signers,
            EXPECTED_SIGNING_FINGERPRINT,
        )
    except (IntegrityError, OSError, subprocess.SubprocessError) as exc:
        print(f"SIGN REFUSED — {exc}", file=sys.stderr)
        return 1
    print(
        f"SIGNED — identity={SIGN_IDENTITY} namespace={SIGN_NAMESPACE} "
        f"fingerprint={EXPECTED_SIGNING_FINGERPRINT} signature={manifest_path}.sig"
    )
    return 0


def _print_report(report: Mapping[str, Any]) -> None:
    label = "READY" if report["readyToRun"] else "NOT READY"
    print(
        f"{label} {report['score']} — skills={report['skillsChecked']} "
        f"profile={report.get('profile') or 'unverified'}"
    )
    for name, check in report["checks"].items():
        status = "PASS" if check["pass"] else "FAIL"
        print(f"  {status} {name}: {check['detail']}")
        for failure in check["failures"]:
            print(f"    - {failure}")


def cmd_verify(args: argparse.Namespace) -> int:
    report = verify_repository(
        args.repo_root,
        skills_dir=args.skills,
        manifest_path=args.manifest,
        policy_path=args.policy,
        public_key=args.public_key,
        allowed_signers=args.allowed_signers,
        expected_fingerprint=EXPECTED_SIGNING_FINGERPRINT,
        allow_fixture=False,
    )
    if args.json:
        print(json.dumps(report, sort_keys=True, indent=2))
    else:
        _print_report(report)
    return 0 if report["readyToRun"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root (default: parent of scripts/)",
    )
    parser.add_argument("--skills", type=Path, help="override canonical skills directory")
    parser.add_argument("--policy", type=Path, help="override integrity policy")
    subparsers = parser.add_subparsers(dest="command", required=True)

    manifest = subparsers.add_parser("manifest", help="generate a canonical policy-checked manifest")
    manifest.add_argument("--out", type=Path, help="manifest output path")
    manifest.set_defaults(function=cmd_manifest)

    sign = subparsers.add_parser("sign", help="sign through the 1Password SSH agent")
    sign.add_argument("--manifest", type=Path, help="canonical manifest path")
    sign.add_argument("--public-key", type=Path, help="agent-served public-key path")
    sign.add_argument("--allowed-signers", type=Path, help="OpenSSH allowed_signers path")
    sign.set_defaults(function=cmd_sign)

    verify = subparsers.add_parser("verify", help="run the fail-closed five-check gate")
    verify.add_argument("--manifest", type=Path, help="signed manifest path")
    verify.add_argument("--public-key", type=Path, help="trusted public-key path")
    verify.add_argument("--allowed-signers", type=Path, help="OpenSSH allowed_signers path")
    verify.add_argument("--json", action="store_true", help="emit the machine-readable report")
    verify.set_defaults(function=cmd_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.function(args)


if __name__ == "__main__":
    raise SystemExit(main())
