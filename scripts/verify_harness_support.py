#!/usr/bin/env python3
"""Verify the harness support contract without third-party dependencies or network I/O."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "docs" / "harness-support.json"
MARKDOWN_PATH = ROOT / "docs" / "harness-support.md"

TIERS = {
    "verified-native",
    "format-validated",
    "documented-adapter",
    "unsupported/unknown",
}
PROBE_STATUSES = {"unrun", "partial", "passed", "failed"}
REQUESTED_TARGETS = {
    "openai-codex",
    "claude-code",
    "claude-ai-upload",
    "cursor",
    "github-copilot-vscode",
    "amp",
    "kimi-code-cli",
    "google-antigravity-ide",
    "google-antigravity-cli",
    "openclaw",
    "grok-build-cli",
    "grok-bot",
    "buzz",
    "pi",
    "hermes-native-windows",
}
STRICT_FIELDS = {
    "name",
    "description",
    "license",
    "compatibility",
    "metadata",
    "allowed-tools",
}
AMP_PATHS = (
    "~/.config/agents/skills",
    "~/.agents/skills",
    "~/.config/amp/skills",
    ".agents/skills",
    ".claude/skills",
    "~/.claude/skills",
    "~/.claude/plugins/cache",
    "amp.skills.path",
    "built-in skills",
    "personal skills repository",
    "active workspace skills repository",
)


class ContractError(AssertionError):
    """Raised for a contract verification failure."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def frontmatter(text: str, path: Path) -> str:
    lines = text.lstrip("\ufeff").splitlines()
    require(lines and lines[0].strip() == "---", f"missing frontmatter start: {path}")
    try:
        end = next(index for index, line in enumerate(lines[1:], 1) if line.strip() == "---")
    except StopIteration as exc:
        raise ContractError(f"missing frontmatter end: {path}") from exc
    return "\n".join(lines[1:end])


def scalar_field(metadata: str, field: str, path: Path) -> str:
    match = re.search(rf"(?m)^{re.escape(field)}:\s*(.*)$", metadata)
    require(match is not None, f"missing {field}: {path}")
    value = match.group(1).strip()
    if value in {">", ">-", ">+", "|", "|-", "|+"}:
        remaining = metadata[match.end() :].splitlines()
        block: list[str] = []
        for line in remaining:
            if line and not line[0].isspace():
                break
            block.append(line.strip())
        value = ("\n" if value.startswith("|") else " ").join(block).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1]
    return value


def verify_pack_facts(contract: dict) -> None:
    facts = contract["packFacts"]
    skill_dirs = sorted(
        path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")
    )
    registry = load_json(ROOT / facts["registry"])
    registry_names = sorted(item["name"] for item in registry["skills"])
    sidecars = list((ROOT / "skills").glob("*/agents/openai.yaml"))
    disabled: list[str] = []
    hinted: list[str] = []
    lengths: list[int] = []

    for name in skill_dirs:
        path = ROOT / "skills" / name / "SKILL.md"
        metadata = frontmatter(path.read_text(encoding="utf-8"), path)
        if re.search(r"(?m)^disable-model-invocation:", metadata):
            disabled.append(name)
        if re.search(r"(?m)^argument-hint:", metadata):
            hinted.append(name)
        lengths.append(len(scalar_field(metadata, "description", path)))

    require(skill_dirs == registry_names, "registry names differ from skill directories")
    require(len(skill_dirs) == facts["skillCount"] == 50, "skill count must be 50")
    require(len(sidecars) == facts["openaiSidecarCount"] == 50, "sidecar count must be 50")
    require(
        disabled == sorted(facts["extendedFields"]["disable-model-invocation"]["skills"]),
        "disable-model-invocation inventory differs from contract",
    )
    require(len(disabled) == facts["extendedFields"]["disable-model-invocation"]["count"] == 13, "user-only count must be 13")
    require(
        hinted == sorted(facts["extendedFields"]["argument-hint"]["skills"]),
        "argument-hint inventory differs from contract",
    )
    require(len(hinted) == facts["extendedFields"]["argument-hint"]["count"] == 5, "argument-hint count must be 5")
    snapshot = facts["claudeAiUploadSnapshot"]
    require(min(lengths) == snapshot["measuredDescriptionMin"] == 106, "description minimum must be 106")
    require(max(lengths) == snapshot["measuredDescriptionMax"] == 749, "description maximum must be 749")
    require(sum(length > 200 for length in lengths) == snapshot["descriptionsOverDocumentedMax"] == 48, "over-200 description count must be 48")
    require(set(facts["strictSpecTopLevelFields"]) == STRICT_FIELDS, "strict field inventory differs")


def verify_harnesses(contract: dict, markdown: str) -> None:
    require(set(contract["classificationDefinitions"]) == TIERS, "classification vocabulary differs")
    require(set(contract["probeEvidenceStatusDefinitions"]) == PROBE_STATUSES, "probe evidence vocabulary differs")
    harnesses = contract["harnesses"]
    ids = [item["id"] for item in harnesses]
    require(len(ids) == len(set(ids)), "duplicate harness id")
    require(set(ids) == REQUESTED_TARGETS, "requested harness coverage differs")

    for harness in harnesses:
        harness_id = harness["id"]
        require(harness["classification"] in TIERS, f"unknown tier: {harness_id}")
        require(harness["sources"], f"missing sources: {harness_id}")
        require(harness["loader"], f"missing loader statement: {harness_id}")
        require(harness["probe"]["command"].strip(), f"missing probe command: {harness_id}")
        require(harness["probe"]["passCriteria"].strip(), f"missing pass criteria: {harness_id}")
        require("observed" not in harness["probe"], f"binary observed field is forbidden: {harness_id}")
        status = harness["probe"].get("evidenceStatus")
        require(status in PROBE_STATUSES, f"invalid probe evidence status: {harness_id}")
        require(harness["probe"]["observation"].strip(), f"missing probe observation: {harness_id}")
        if status == "passed":
            require("not run" not in harness["probe"]["observation"].lower(), f"passing probe says it was not run: {harness_id}")
        require(
            f"| {harness['name']} | `{harness['classification']}` |" in markdown,
            f"Markdown matrix differs for {harness_id}",
        )

        for source in harness["sources"]:
            parsed = urlparse(source["url"])
            require(parsed.scheme == "https" and parsed.netloc, f"invalid source URL: {source['url']}")
            require(source["claims"] and all(str(claim).strip() for claim in source["claims"]), f"source lacks positive claim mapping: {source['url']}")
            require(source["url"] in markdown, f"JSON source is absent from Markdown: {source['url']}")


def verify_key_contracts(contract: dict, markdown: str) -> None:
    require(contract["schema"] == "idc.harness-support/v1.1", "unexpected contract schema")
    require(contract["contractVersion"] == "1.1.0", "unexpected contract version")
    require(contract["asOf"] == "2026-08-11", "unexpected evidence date")
    strict_url = contract["packFacts"]["strictSpecSource"]
    parsed_strict_url = urlparse(strict_url)
    require(parsed_strict_url.scheme == "https" and parsed_strict_url.netloc, "invalid strict-spec URL")
    require(strict_url in markdown, "strict-spec source is absent from Markdown")
    for text in (
        "Contract schema: `idc.harness-support/v1.1`",
        "Contract version: `1.1.0`",
        "Evidence date: `2026-08-11`",
        "Forge release inspected: `2.0.0` (50 skill islands)",
        "48 of the Forge's 50 descriptions exceed 200",
        "YAML-parsed range: 106–749",
    ):
        require(text in markdown, f"Markdown key fact missing: {text}")

    by_id = {item["id"]: item for item in contract["harnesses"]}
    claude_ai = by_id["claude-ai-upload"]
    format_contract = claude_ai["formatContract"]
    require(set(format_contract["acceptedTopLevelFields"]) == STRICT_FIELDS, "claude.ai six-key schema differs")
    require(format_contract["rejectsOtherTopLevelFields"] is True, "claude.ai must fail closed on extra fields")
    require(format_contract["descriptionMaxCharacters"] == 200, "claude.ai description maximum differs")
    archive = format_contract["archiveLayout"]
    require(archive["topLevelEntry"] == "<skill-name>/", "claude.ai ZIP root differs")
    require(archive["entrypoint"] == "<skill-name>/SKILL.md", "claude.ai ZIP entrypoint differs")
    require(archive["filesDirectlyAtArchiveRootAllowed"] is False, "claude.ai files-at-root must be false")
    require(archive["extraWrapperDirectoryAllowed"] is False, "claude.ai wrapper directory must be false")
    require("dependencies" in format_contract["documentedTension"], "claude.ai dependencies documentation tension missing")
    claude_urls = {source["url"] for source in claude_ai["sources"]}
    require("https://code.claude.com/docs/en/skills" in claude_urls, "current Anthropic six-key authority missing")
    require("https://support.claude.com/en/articles/12512198-how-to-create-custom-skills" in claude_urls, "Anthropic ZIP/description authority missing")

    amp = by_id["amp"]
    require(tuple(item["path"] for item in amp["loader"]) == AMP_PATHS, "Amp loader precedence differs")
    require("amp skills list --json" in amp["probe"]["command"], "Amp shell inventory command differs")
    require("skills: list" in amp["probe"]["command"], "Amp palette inventory command differs")
    require("skill: list" not in markdown and "skill: list" not in json.dumps(contract), "obsolete Amp command remains")


def main() -> int:
    contract = load_json(CONTRACT_PATH)
    markdown = MARKDOWN_PATH.read_text(encoding="utf-8")
    verify_pack_facts(contract)
    verify_harnesses(contract, markdown)
    verify_key_contracts(contract, markdown)
    print(
        "harness support contract verified: "
        f"{len(contract['harnesses'])} harness surfaces, "
        f"{contract['packFacts']['skillCount']} skills, "
        f"schema {contract['schema']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ContractError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(f"harness support contract verification failed: {error}", file=sys.stderr)
        raise SystemExit(1)
