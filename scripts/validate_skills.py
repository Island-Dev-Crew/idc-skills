#!/usr/bin/env python3
"""Validate the IDC skills forge without third-party dependencies.

The default ``canonical`` profile validates the authored source for Claude Code
and Codex. The supplied 2026-08-11 claude.ai probe uses a smaller frontmatter
vocabulary, so unsupported keys are warnings by default and become errors under
the explicitly dated profile. The validator never rewrites source files.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import unquote


SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MARKDOWN_LINK_RE = re.compile(r"!?\[([^\]]*)\]\(([^)\n]+)\)")
WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")

# Union of the portable Agent Skills fields and Claude Code's documented skill
# extensions. Harness-specific invocation semantics are checked separately.
CANONICAL_FRONTMATTER_KEYS = frozenset(
    {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
        "allowed-tools",
        "argument-hint",
        "disable-model-invocation",
    }
)
CLAUDE_AI_SUPPLIED_FRONTMATTER_KEYS = frozenset(
    {"allowed-tools", "compatibility", "description", "license", "metadata", "name"}
)
CODEX_STRICT_FRONTMATTER_KEYS = frozenset(
    {"allowed-tools", "description", "license", "metadata", "name"}
)
OPENAI_TOP_LEVEL_KEYS = frozenset({"interface", "policy"})
OPENAI_INTERFACE_KEYS = frozenset(
    {
        "display_name",
        "short_description",
        "icon_small",
        "icon_large",
        "brand_color",
        "default_prompt",
    }
)
OPENAI_POLICY_KEYS = frozenset({"allow_implicit_invocation"})
SCRIPT_SUFFIXES = frozenset({".py", ".sh", ".js", ".mjs", ".cjs", ".ps1"})
BINARY_SUFFIXES = frozenset(
    {
        ".avif",
        ".gif",
        ".ico",
        ".jpeg",
        ".jpg",
        ".pdf",
        ".png",
        ".webp",
        ".woff",
        ".woff2",
        ".zip",
    }
)
PROFILE_SEMANTICS = {
    "canonical": (
        "Authored-source profile: Claude Code extensions are allowed, Codex invocation parity is enforced "
        "through agents/openai.yaml, and the supplied 2026-08-11 claude.ai allowlist probe is advisory."
    ),
    "codex-strict": (
        "Compatibility profile for Codex's bundled quick_validate.py allowlist. This is stricter than the "
        "observed Codex runtime loader and must not be reported as runtime non-loadability."
    ),
    "claude-ai-supplied-2026-08-11": (
        "Reproduces the six-key claude.ai allowlist supplied with this task on 2026-08-11. Current official "
        "claude.ai documentation does not publish that allowlist, so this is a named supplied probe, not a "
        "claim about the current canonical service; source files are never rewritten."
    ),
}


class SimpleYamlError(ValueError):
    """A syntax error in the dependency-free YAML subset used by this repo."""

    def __init__(self, message: str, line: int | None = None) -> None:
        super().__init__(message)
        self.line = line


@dataclass(order=True)
class Diagnostic:
    sort_key: tuple[str, int, str, str] = field(init=False, repr=False)
    severity: str
    code: str
    check: str
    path: str
    message: str
    line: int | None = None
    skill: str | None = None

    def __post_init__(self) -> None:
        self.sort_key = (self.path, self.line or 0, self.severity, self.code)

    def as_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "severity": self.severity,
            "code": self.code,
            "check": self.check,
            "path": self.path,
            "message": self.message,
        }
        if self.line is not None:
            data["line"] = self.line
        if self.skill is not None:
            data["skill"] = self.skill
        return data


@dataclass
class SkillSource:
    name: str
    folder: Path
    skill_path: Path
    body: str
    frontmatter: dict[str, Any]
    frontmatter_lines: dict[str, int]


def _strip_yaml_comment(value: str) -> str:
    quote: str | None = None
    index = 0
    while index < len(value):
        char = value[index]
        if quote == '"' and char == "\\":
            index += 2
            continue
        if quote == "'" and char == "'" and index + 1 < len(value) and value[index + 1] == "'":
            index += 2
            continue
        if char in {"'", '"'}:
            if quote == char:
                quote = None
            elif quote is None:
                preceding = value[:index].rstrip()
                # A quote begins a YAML scalar only at the start or directly
                # after the mapping colon. Apostrophes in plain prose (it's,
                # project's) remain ordinary characters.
                if not preceding or preceding.endswith(":"):
                    quote = char
        elif char == "#" and quote is None and (index == 0 or value[index - 1].isspace()):
            return value[:index].rstrip()
        index += 1
    if quote is not None:
        raise SimpleYamlError("unterminated quoted scalar")
    return value.rstrip()


def _split_yaml_mapping_line(content: str, line: int) -> tuple[str, str]:
    if ":" not in content:
        raise SimpleYamlError("expected a 'key: value' mapping entry", line)
    key, value = content.split(":", 1)
    key = key.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", key):
        raise SimpleYamlError(f"invalid mapping key {key!r}", line)
    return key, value.strip()


def _parse_yaml_scalar(value: str, line: int) -> Any:
    value = _strip_yaml_comment(value).strip()
    if not value:
        return ""
    if value.startswith('"'):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise SimpleYamlError(f"invalid double-quoted scalar: {exc.msg}", line) from exc
        if not isinstance(parsed, str):
            raise SimpleYamlError("double-quoted YAML scalar must be a string", line)
        return parsed
    if value.startswith("'"):
        if len(value) < 2 or not value.endswith("'"):
            raise SimpleYamlError("unterminated single-quoted scalar", line)
        return value[1:-1].replace("''", "'")
    if ": " in value:
        raise SimpleYamlError("colon-space in an unquoted scalar", line)
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"null", "~"}:
        return None
    if re.fullmatch(r"-?[0-9]+", value):
        return int(value)
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        return [] if not inner else [_parse_yaml_scalar(item.strip(), line) for item in inner.split(",")]
    return value


def parse_simple_yaml(text: str, *, line_offset: int = 0) -> tuple[dict[str, Any], dict[str, int]]:
    """Parse the mapping-only YAML shape used by SKILL.md and openai.yaml.

    The parser deliberately rejects aliases, tags, tabs, duplicate keys, and
    mapping sequences. Those features are unnecessary for portable skill
    metadata and make safe dependency-free validation ambiguous.
    """

    root: dict[str, Any] = {}
    key_lines: dict[str, int] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    last_indent = -1
    pending_container: dict[str, Any] | None = None

    for relative_line, raw_line in enumerate(text.splitlines(), start=1):
        line = relative_line + line_offset
        if "\t" in raw_line[: len(raw_line) - len(raw_line.lstrip(" \t"))]:
            raise SimpleYamlError("tabs are not valid indentation", line)
        uncommented = _strip_yaml_comment(raw_line)
        if not uncommented.strip():
            continue
        if uncommented.lstrip().startswith(("- ", "-\t")):
            raise SimpleYamlError("mapping sequences are not supported in portable metadata", line)
        indent = len(uncommented) - len(uncommented.lstrip(" "))
        if indent % 2:
            raise SimpleYamlError("indentation must use multiples of two spaces", line)
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise SimpleYamlError("invalid indentation", line)
        if indent > last_indent + 2 and last_indent >= 0:
            raise SimpleYamlError("indentation jumped more than one mapping level", line)
        parent = stack[-1][1]
        key, raw_value = _split_yaml_mapping_line(uncommented.strip(), line)
        if key in parent:
            raise SimpleYamlError(f"duplicate mapping key {key!r}", line)
        if raw_value in {"|", "|-", "|+", ">", ">-", ">+"}:
            raise SimpleYamlError("block scalars are not supported in portable metadata", line)
        if raw_value:
            parent[key] = _parse_yaml_scalar(raw_value, line)
            pending_container = None
        else:
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
            pending_container = child
        if len(stack) == 1:
            key_lines[key] = line
        elif indent == 0:
            key_lines[key] = line
        last_indent = indent

    del pending_container  # documents intent; empty mappings are valid
    return root, key_lines


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return str(path)


class ForgeValidator:
    def __init__(self, root: Path, profile: str = "canonical") -> None:
        self.root = root.resolve()
        self.profile = profile
        self.diagnostics: list[Diagnostic] = []
        self.skills: dict[str, SkillSource] = {}
        self.registry: dict[str, Any] = {}
        self._checks_seen: set[str] = set()
        self._tooling: dict[str, str | None] = {
            "bash": shutil.which("bash"),
            "node": shutil.which("node"),
            "pwsh": shutil.which("pwsh") or shutil.which("powershell"),
            "python": sys.executable,
        }

    def add(
        self,
        severity: str,
        code: str,
        check: str,
        path: Path | str,
        message: str,
        *,
        line: int | None = None,
        skill: str | None = None,
    ) -> None:
        self._checks_seen.add(check)
        normalized = path if isinstance(path, str) else _relative(path, self.root)
        self.diagnostics.append(
            Diagnostic(
                severity=severity,
                code=code,
                check=check,
                path=normalized,
                message=message,
                line=line,
                skill=skill,
            )
        )

    def _mark_check(self, *names: str) -> None:
        self._checks_seen.update(names)

    def _read_utf8(self, path: Path, *, skill: str | None = None) -> str | None:
        self._mark_check("utf8")
        try:
            data = path.read_bytes()
        except OSError as exc:
            self.add("error", "FILE_READ", "utf8", path, f"cannot read file: {exc}", skill=skill)
            return None
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            self.add(
                "error",
                "INVALID_UTF8",
                "utf8",
                path,
                f"not valid UTF-8 at byte {exc.start}",
                skill=skill,
            )
            return None

    def _load_registry(self) -> None:
        self._mark_check("registry_bijection")
        registry_path = self.root / "skills" / "registry.json"
        text = self._read_utf8(registry_path)
        if text is None:
            return
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            self.add(
                "error",
                "REGISTRY_JSON",
                "registry_bijection",
                registry_path,
                f"invalid JSON: {exc.msg}",
                line=exc.lineno,
            )
            return
        if not isinstance(value, dict):
            self.add("error", "REGISTRY_SHAPE", "registry_bijection", registry_path, "registry root must be an object")
            return
        self.registry = value

    def _registry_entries(self) -> list[dict[str, Any]]:
        entries = self.registry.get("skills", [])
        if not isinstance(entries, list):
            self.add(
                "error",
                "REGISTRY_SKILLS_TYPE",
                "registry_bijection",
                self.root / "skills" / "registry.json",
                "registry.skills must be an array",
            )
            return []
        valid_entries: list[dict[str, Any]] = []
        seen_names: set[str] = set()
        seen_paths: set[str] = set()
        for index, entry in enumerate(entries):
            if not isinstance(entry, dict):
                self.add(
                    "error",
                    "REGISTRY_ENTRY_TYPE",
                    "registry_bijection",
                    "skills/registry.json",
                    f"skills[{index}] must be an object",
                )
                continue
            name = entry.get("name")
            path = entry.get("path")
            invocation = entry.get("invocation")
            if not isinstance(name, str) or not isinstance(path, str):
                self.add(
                    "error",
                    "REGISTRY_ENTRY_FIELDS",
                    "registry_bijection",
                    "skills/registry.json",
                    f"skills[{index}] requires string name and path",
                )
                continue
            if name in seen_names:
                self.add("error", "REGISTRY_DUPLICATE_NAME", "registry_bijection", "skills/registry.json", f"duplicate skill name {name!r}", skill=name)
            if path in seen_paths:
                self.add("error", "REGISTRY_DUPLICATE_PATH", "registry_bijection", "skills/registry.json", f"duplicate skill path {path!r}", skill=name)
            if path != name:
                self.add("error", "REGISTRY_NAME_PATH", "registry_bijection", "skills/registry.json", f"registry path {path!r} must equal name {name!r}", skill=name)
            if invocation not in {"model", "user"}:
                self.add("error", "REGISTRY_INVOCATION", "invocation_parity", "skills/registry.json", f"invocation must be 'model' or 'user', got {invocation!r}", skill=name)
            seen_names.add(name)
            seen_paths.add(path)
            valid_entries.append(entry)

        build_order = self.registry.get("buildOrder")
        if not isinstance(build_order, list) or not all(isinstance(item, str) for item in build_order):
            self.add("error", "BUILD_ORDER_TYPE", "registry_bijection", "skills/registry.json", "buildOrder must be an array of skill names")
        else:
            duplicates = sorted({item for item in build_order if build_order.count(item) > 1})
            if duplicates:
                self.add("error", "BUILD_ORDER_DUPLICATE", "registry_bijection", "skills/registry.json", f"duplicate buildOrder entries: {', '.join(duplicates)}")
            if set(build_order) != seen_names:
                missing = sorted(seen_names - set(build_order))
                extra = sorted(set(build_order) - seen_names)
                self.add("error", "BUILD_ORDER_BIJECTION", "registry_bijection", "skills/registry.json", f"buildOrder mismatch; missing={missing}, extra={extra}")
        return valid_entries

    def _extract_frontmatter(self, path: Path, skill: str) -> SkillSource | None:
        self._mark_check("frontmatter", "canonical_compatibility")
        text = self._read_utf8(path, skill=skill)
        if text is None:
            return None
        lines = text.splitlines()
        if not lines or lines[0] != "---":
            self.add("error", "FRONTMATTER_OPEN", "frontmatter", path, "first line must be exactly '---'", line=1, skill=skill)
            return None
        closing = next((index for index in range(1, len(lines)) if lines[index] == "---"), None)
        if closing is None:
            self.add("error", "FRONTMATTER_CLOSE", "frontmatter", path, "missing closing '---' boundary", skill=skill)
            return None
        yaml_text = "\n".join(lines[1:closing])
        if "<" in yaml_text or ">" in yaml_text:
            self.add("error", "FRONTMATTER_ANGLE", "frontmatter", path, "frontmatter must not contain '<' or '>'", skill=skill)
        try:
            frontmatter, key_lines = parse_simple_yaml(yaml_text, line_offset=1)
        except SimpleYamlError as exc:
            self.add("error", "FRONTMATTER_YAML", "frontmatter", path, str(exc), line=exc.line, skill=skill)
            return None
        unsupported = sorted(set(frontmatter) - CANONICAL_FRONTMATTER_KEYS)
        if unsupported:
            self.add("error", "FRONTMATTER_KEY", "canonical_compatibility", path, f"unsupported canonical top-level keys: {', '.join(unsupported)}", skill=skill)
        body = "\n".join(lines[closing + 1 :]).strip()
        if not body:
            self.add("error", "SKILL_BODY_EMPTY", "frontmatter", path, "SKILL.md body is empty", skill=skill)
        return SkillSource(skill, path.parent, path, body, frontmatter, key_lines)

    def _check_bijection_and_load(self, entries: Sequence[dict[str, Any]]) -> None:
        skills_root = self.root / "skills"
        if not skills_root.is_dir():
            self.add("error", "SKILLS_DIR_MISSING", "registry_bijection", skills_root, "skills directory is missing")
            return
        folders = {path.name: path for path in skills_root.iterdir() if path.is_dir()}
        registry_names = {str(entry["path"]) for entry in entries}
        for extra in sorted(set(folders) - registry_names):
            self.add("error", "UNREGISTERED_SKILL_FOLDER", "registry_bijection", folders[extra], "skill folder is not present in registry", skill=extra)
        for missing in sorted(registry_names - set(folders)):
            self.add("error", "REGISTERED_FOLDER_MISSING", "registry_bijection", skills_root / missing, "registered skill folder is missing", skill=missing)

        for entry in entries:
            name = str(entry["name"])
            folder = folders.get(str(entry["path"]))
            if folder is None:
                continue
            skill_path = folder / "SKILL.md"
            sidecar_path = folder / "agents" / "openai.yaml"
            if not skill_path.is_file():
                self.add("error", "SKILL_MD_MISSING", "registry_bijection", skill_path, "skill folder has no SKILL.md", skill=name)
            if not sidecar_path.is_file():
                self.add("error", "OPENAI_SIDECAR_MISSING", "registry_bijection", sidecar_path, "skill folder has no agents/openai.yaml", skill=name)
            if skill_path.is_file():
                source = self._extract_frontmatter(skill_path, name)
                if source is not None:
                    self.skills[name] = source

    def _check_skill_contract(self, entry: dict[str, Any], source: SkillSource) -> None:
        self._mark_check("name_folder", "description_contract", "invocation_parity", "claude_ai_exportability")
        name_value = source.frontmatter.get("name")
        if not isinstance(name_value, str):
            self.add("error", "NAME_MISSING", "name_folder", source.skill_path, "frontmatter name must be a string", skill=source.name)
        else:
            if not 1 <= len(name_value) <= 64 or not NAME_RE.fullmatch(name_value):
                self.add("error", "NAME_FORMAT", "name_folder", source.skill_path, "name must be 1-64 lowercase letters, digits, or single hyphens", line=source.frontmatter_lines.get("name"), skill=source.name)
            if name_value != source.folder.name or name_value != source.name:
                self.add("error", "NAME_MISMATCH", "name_folder", source.skill_path, f"frontmatter name {name_value!r}, folder {source.folder.name!r}, and registry name {source.name!r} must match", line=source.frontmatter_lines.get("name"), skill=source.name)

        description = source.frontmatter.get("description")
        if not isinstance(description, str) or not description.strip():
            self.add("error", "DESCRIPTION_MISSING", "description_contract", source.skill_path, "description must be a non-empty string", skill=source.name)
        else:
            if len(description) > 1024:
                self.add("error", "DESCRIPTION_LENGTH", "description_contract", source.skill_path, f"description length {len(description)} exceeds 1024 characters", line=source.frontmatter_lines.get("description"), skill=source.name)
            # Model-visible descriptions are routing pointers and must contain
            # trigger + differentiator language. The canon intentionally strips
            # those from user-only descriptions; registry.triggers remains the
            # discoverability contract for those skills.
            if entry.get("invocation") == "model":
                trigger_pattern = re.compile(r"\b(?:use|read|invoke|fires?)\s+(?:when|for|before|after|whenever)\b", re.IGNORECASE)
                if trigger_pattern.search(description) is None:
                    self.add("error", "DESCRIPTION_TRIGGER", "description_contract", source.skill_path, "model-invoked description must explicitly state when to use or read the skill", line=source.frontmatter_lines.get("description"), skill=source.name)
                if "differentiator" not in description.lower():
                    self.add("error", "DESCRIPTION_DIFFERENTIATOR", "description_contract", source.skill_path, "model-invoked description must include a Differentiator clause", line=source.frontmatter_lines.get("description"), skill=source.name)

        registry_triggers = entry.get("triggers")
        if not isinstance(registry_triggers, list) or not registry_triggers or not all(isinstance(item, str) and item.strip() for item in registry_triggers):
            self.add("error", "REGISTRY_TRIGGERS", "description_contract", "skills/registry.json", "every skill requires a non-empty array of trigger phrases", skill=source.name)

        disabled = source.frontmatter.get("disable-model-invocation", False)
        if "disable-model-invocation" in source.frontmatter and disabled is not True:
            self.add("error", "DISABLE_INVOCATION_VALUE", "invocation_parity", source.skill_path, "disable-model-invocation must be true when present; omit it for model invocation", line=source.frontmatter_lines.get("disable-model-invocation"), skill=source.name)
        expected_invocation = "user" if disabled is True else "model"
        if entry.get("invocation") != expected_invocation:
            self.add("error", "REGISTRY_FRONTMATTER_INVOCATION", "invocation_parity", source.skill_path, f"registry says {entry.get('invocation')!r}, frontmatter implies {expected_invocation!r}", skill=source.name)

        unsupported_ai = sorted(set(source.frontmatter) - CLAUDE_AI_SUPPLIED_FRONTMATTER_KEYS)
        if unsupported_ai and self.profile in {"canonical", "claude-ai-supplied-2026-08-11"}:
            severity = "error" if self.profile == "claude-ai-supplied-2026-08-11" else "warning"
            self.add(severity, "CLAUDE_AI_SUPPLIED_UNSUPPORTED_KEYS", "claude_ai_exportability", source.skill_path, f"supplied 2026-08-11 claude.ai probe rejects top-level keys: {', '.join(unsupported_ai)}", skill=source.name)
        unsupported_codex_strict = sorted(set(source.frontmatter) - CODEX_STRICT_FRONTMATTER_KEYS)
        if unsupported_codex_strict and self.profile == "codex-strict":
            self.add("error", "CODEX_STRICT_UNSUPPORTED_KEYS", "codex_strict_compatibility", source.skill_path, f"Codex quick-validator rejects top-level keys: {', '.join(unsupported_codex_strict)}", skill=source.name)

    def _check_sidecar(self, entry: dict[str, Any], source: SkillSource) -> None:
        self._mark_check("openai_sidecar", "invocation_parity", "canonical_compatibility")
        sidecar = source.folder / "agents" / "openai.yaml"
        text = self._read_utf8(sidecar, skill=source.name)
        if text is None:
            return
        try:
            data, _ = parse_simple_yaml(text)
        except SimpleYamlError as exc:
            self.add("error", "OPENAI_YAML", "openai_sidecar", sidecar, str(exc), line=exc.line, skill=source.name)
            return
        unsupported_top = sorted(set(data) - OPENAI_TOP_LEVEL_KEYS)
        if unsupported_top:
            self.add("error", "OPENAI_TOP_LEVEL_KEY", "canonical_compatibility", sidecar, f"unsupported openai.yaml top-level keys: {', '.join(unsupported_top)}", skill=source.name)
        interface = data.get("interface")
        if not isinstance(interface, dict):
            self.add("error", "OPENAI_INTERFACE", "openai_sidecar", sidecar, "interface must be a mapping", skill=source.name)
        else:
            unsupported_interface = sorted(set(interface) - OPENAI_INTERFACE_KEYS)
            if unsupported_interface:
                self.add("error", "OPENAI_INTERFACE_KEY", "canonical_compatibility", sidecar, f"unsupported interface keys: {', '.join(unsupported_interface)}", skill=source.name)
            display_name = interface.get("display_name")
            short_description = interface.get("short_description")
            if not isinstance(display_name, str) or not display_name.strip():
                self.add("error", "OPENAI_DISPLAY_NAME", "openai_sidecar", sidecar, "interface.display_name must be a non-empty string", skill=source.name)
            if not isinstance(short_description, str) or not short_description.strip():
                self.add("error", "OPENAI_SHORT_DESCRIPTION", "openai_sidecar", sidecar, "interface.short_description must be a non-empty string", skill=source.name)
            elif len(short_description) > 200:
                self.add("error", "OPENAI_SHORT_DESCRIPTION_LENGTH", "openai_sidecar", sidecar, "interface.short_description exceeds 200 characters", skill=source.name)

        policy = data.get("policy")
        expected_user = entry.get("invocation") == "user"
        if expected_user:
            if not isinstance(policy, dict) or policy.get("allow_implicit_invocation") is not False:
                self.add("error", "OPENAI_POLICY_USER", "invocation_parity", sidecar, "user-invoked skill requires policy.allow_implicit_invocation: false", skill=source.name)
        elif policy is not None:
            self.add("error", "OPENAI_POLICY_MODEL", "invocation_parity", sidecar, "model-invoked skill must omit the policy block", skill=source.name)
        if isinstance(policy, dict):
            unsupported_policy = sorted(set(policy) - OPENAI_POLICY_KEYS)
            if unsupported_policy:
                self.add("error", "OPENAI_POLICY_KEY", "canonical_compatibility", sidecar, f"unsupported policy keys: {', '.join(unsupported_policy)}", skill=source.name)

    @staticmethod
    def _markdown_target(raw_target: str) -> str:
        target = raw_target.strip()
        if target.startswith("<") and ">" in target:
            return target[1 : target.index(">")]
        return target.split(maxsplit=1)[0]

    @staticmethod
    def _is_external_or_template(label: str, target: str) -> bool:
        lowered = target.lower()
        return (
            not target
            or target.startswith("#")
            or lowered.startswith(("http://", "https://", "mailto:", "data:"))
            or ("<" in label and ">" in label)
            or target in {"link", "path", "url", "URL"}
        )

    def _resolve_reference(self, source_file: Path, label: str, raw_target: str, skill: str, line: int) -> Path | None:
        target = unquote(self._markdown_target(raw_target)).split("#", 1)[0]
        if self._is_external_or_template(label, target):
            return None
        if "\\" in target:
            self.add("error", "REFERENCE_SEPARATOR", "references", source_file, f"reference must use portable '/' separators: {target!r}", line=line, skill=skill)
            return None
        if target.startswith(("/", "~")) or WINDOWS_ABSOLUTE_RE.match(target):
            self.add("error", "REFERENCE_ABSOLUTE", "references", source_file, f"reference must be relative: {target!r}", line=line, skill=skill)
            return None
        resolved = (source_file.parent / Path(target)).resolve()
        try:
            resolved.relative_to(self.root)
        except ValueError:
            self.add("error", "REFERENCE_ESCAPE", "references", source_file, f"reference escapes the repository: {target!r}", line=line, skill=skill)
            return None
        if not resolved.exists():
            self.add("error", "REFERENCE_MISSING", "references", source_file, f"referenced path does not exist: {target!r}", line=line, skill=skill)
            return None
        return resolved

    def _check_references(self, source: SkillSource) -> None:
        self._mark_check("references", "one_hop_references")
        text = self._read_utf8(source.skill_path, skill=source.name)
        if text is None:
            return
        for match in MARKDOWN_LINK_RE.finditer(text):
            line = text.count("\n", 0, match.start()) + 1
            self._resolve_reference(source.skill_path, match.group(1), match.group(2), source.name, line)
        references_dir = source.folder / "references"
        if references_dir.is_dir():
            for reference in sorted(references_dir.rglob("*.md")):
                reference_text = self._read_utf8(reference, skill=source.name)
                if reference_text is None:
                    continue
                for match in MARKDOWN_LINK_RE.finditer(reference_text):
                    target = self._markdown_target(match.group(2))
                    if self._is_external_or_template(match.group(1), target):
                        continue
                    line = reference_text.count("\n", 0, match.start()) + 1
                    self.add("error", "REFERENCE_CHAIN", "one_hop_references", reference, f"reference file links onward to local path {target!r}; point to it directly from SKILL.md", line=line, skill=source.name)

    def _check_utf8_tree(self, source: SkillSource) -> None:
        for path in sorted(source.folder.rglob("*")):
            if path.is_file() and path.suffix.lower() not in BINARY_SUFFIXES:
                self._read_utf8(path, skill=source.name)

    def _run_script_check(self, path: Path, text: str, skill: str) -> None:
        suffix = path.suffix.lower()
        self._mark_check("script_syntax")
        if suffix == ".py":
            try:
                compile(text, str(path), "exec")
            except SyntaxError as exc:
                self.add("error", "PYTHON_SYNTAX", "script_syntax", path, exc.msg, line=exc.lineno, skill=skill)
            return
        command: list[str] | None = None
        stdin: str | None = None
        if suffix == ".sh" and self._tooling["bash"]:
            command = [str(self._tooling["bash"]), "-n", "-"]
            stdin = text
        elif suffix in {".js", ".mjs", ".cjs"} and self._tooling["node"]:
            command = [str(self._tooling["node"]), "--check", str(path)]
        elif suffix == ".ps1" and self._tooling["pwsh"]:
            escaped = str(path).replace("'", "''")
            command = [
                str(self._tooling["pwsh"]),
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"$e=$null; [System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$null,[ref]$e)>$null; if($e){{ $e | ForEach-Object {{$_.Message}}; exit 1 }}",
            ]
        elif suffix in SCRIPT_SUFFIXES:
            tool = {".sh": "bash", ".js": "node", ".mjs": "node", ".cjs": "node", ".ps1": "pwsh"}.get(suffix, suffix)
            self.add("warning", "SCRIPT_CHECK_UNAVAILABLE", "script_syntax", path, f"{tool} unavailable; syntax check skipped", skill=skill)
            return
        if command is None:
            return
        try:
            completed = subprocess.run(
                command,
                input=stdin.encode("utf-8") if stdin is not None else None,
                capture_output=True,
                cwd=path.parent,
                timeout=15,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.add("warning", "SCRIPT_CHECK_FAILED_TO_RUN", "script_syntax", path, f"syntax checker could not run: {exc}", skill=skill)
            return
        if completed.returncode:
            output = (completed.stderr or completed.stdout).decode("utf-8", errors="replace")
            detail = output.strip().splitlines()
            message = detail[-1] if detail else f"syntax checker exited {completed.returncode}"
            self.add("error", "SCRIPT_SYNTAX", "script_syntax", path, message, skill=skill)

    def _check_scripts(self, source: SkillSource) -> None:
        for path in sorted(source.folder.rglob("*")):
            if path.is_file() and path.suffix.lower() in SCRIPT_SUFFIXES:
                text = self._read_utf8(path, skill=source.name)
                if text is not None:
                    self._run_script_check(path, text, source.name)

    def validate(self) -> dict[str, Any]:
        self._load_registry()
        entries = self._registry_entries() if self.registry else []
        self._check_bijection_and_load(entries)
        entries_by_name = {str(entry["name"]): entry for entry in entries}
        for name in sorted(self.skills):
            source = self.skills[name]
            entry = entries_by_name[name]
            self._check_skill_contract(entry, source)
            if (source.folder / "agents" / "openai.yaml").is_file():
                self._check_sidecar(entry, source)
            self._check_references(source)
            self._check_utf8_tree(source)
            self._check_scripts(source)

        self.diagnostics.sort()
        errors = sum(item.severity == "error" for item in self.diagnostics)
        warnings = sum(item.severity == "warning" for item in self.diagnostics)
        failed_skills = sorted({item.skill for item in self.diagnostics if item.severity == "error" and item.skill})
        warning_skills = sorted({item.skill for item in self.diagnostics if item.severity == "warning" and item.skill})
        checks: dict[str, str] = {}
        for check in sorted(self._checks_seen):
            severities = {item.severity for item in self.diagnostics if item.check == check}
            checks[check] = "fail" if "error" in severities else ("warn" if "warning" in severities else "pass")
        return {
            "schemaVersion": SCHEMA_VERSION,
            "root": str(self.root),
            "profile": self.profile,
            "profileSemantics": PROFILE_SEMANTICS[self.profile],
            "valid": errors == 0,
            "summary": {
                "skillsRegistered": len(entries),
                "skillsLoaded": len(self.skills),
                "errors": errors,
                "warnings": warnings,
                "diagnostics": len(self.diagnostics),
                "failedSkills": failed_skills,
                "warningSkills": warning_skills,
            },
            "checks": checks,
            "tooling": self._tooling,
            "diagnostics": [item.as_dict() for item in self.diagnostics],
        }


def _print_human(result: dict[str, Any]) -> None:
    summary = result["summary"]
    verdict = "PASS" if result["valid"] else "FAIL"
    print(
        f"{verdict} profile={result['profile']} skills={summary['skillsLoaded']}/{summary['skillsRegistered']} "
        f"errors={summary['errors']} warnings={summary['warnings']}"
    )
    for item in result["diagnostics"]:
        location = item["path"] + (f":{item['line']}" if "line" in item else "")
        print(f"{item['severity'].upper():7} {item['code']:32} {location} - {item['message']}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="forge repository root (default: parent of this script)",
    )
    parser.add_argument(
        "--profile",
        choices=("canonical", "codex-strict", "claude-ai-supplied-2026-08-11"),
        default="canonical",
        help="strict harness profiles make their restricted top-level-key profile blocking",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON only")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = ForgeValidator(args.root, args.profile).validate()
    if args.json:
        json.dump(result, sys.stdout, indent=2, ensure_ascii=False, sort_keys=True)
        sys.stdout.write("\n")
    else:
        _print_human(result)
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
