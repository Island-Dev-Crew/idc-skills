#!/usr/bin/env python3
"""Verify Forge provenance, vendored protocol hashes, and tool disclosures."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence


REPO = Path(__file__).resolve().parents[1]
ALLOWED_TOOL_STATUS = {
    "required-version-floor",
    "required-external-pinned",
    "required-evidence-pinned",
    "conditional-evidence-pinned",
    "conditional-lockfile-pinned",
    "conditional-operator-tool",
    "test-only-evidence-pinned",
}


class ProvenanceError(RuntimeError):
    pass


def digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load(relative: str) -> dict[str, Any]:
    value = json.loads((REPO / relative).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ProvenanceError(f"{relative} must be an object")
    return value


def verify() -> dict[str, Any]:
    provenance = load("provenance.json")
    registry = load("skills/registry.json")
    dependencies = load("executable-dependencies.json")
    upstream = load("skills/archipelago/protocol/UPSTREAM.json")

    sources = provenance.get("sources")
    if not isinstance(sources, list) or len(sources) != 4:
        raise ProvenanceError("exactly four source-family records are required")
    source_map = {item.get("id"): item for item in sources if isinstance(item, dict)}
    if set(source_map) != {
        "ondrej-skills",
        "pocock-skills",
        "icm-architect",
        "archipelago-protocol",
    }:
        raise ProvenanceError("source ids differ")
    for source_id in ("ondrej-skills", "pocock-skills", "archipelago-protocol"):
        commit = source_map[source_id].get("commit")
        if not isinstance(commit, str) or len(commit) != 40:
            raise ProvenanceError(f"{source_id} is not pinned to a full commit")
        if source_map[source_id].get("license") != "MIT":
            raise ProvenanceError(f"{source_id} license differs")
    icm = source_map["icm-architect"]
    if icm.get("commit") is not None or "UNPINNED" not in icm.get(
        "historical_commit_status", ""
    ):
        raise ProvenanceError("ICM historical gap was laundered or hidden")
    remaining = provenance.get("remaining_to_full_lock")
    if not isinstance(remaining, list) or not any("ICM" in item for item in remaining):
        raise ProvenanceError("ICM residual is absent from remaining lock work")

    skills = registry.get("skills")
    if not isinstance(skills, list) or len(skills) != 50:
        raise ProvenanceError("registry must contain exactly 50 skills")
    for item in skills:
        if not isinstance(item, dict) or not isinstance(item.get("provenance"), str) or not item["provenance"].strip():
            raise ProvenanceError("every registered skill needs a non-empty provenance statement")

    arch_source = source_map["archipelago-protocol"]
    if upstream.get("schema") != "idc-vendored-protocol/v1":
        raise ProvenanceError("vendored protocol schema differs")
    if upstream.get("source", {}).get("commit") != arch_source.get("commit"):
        raise ProvenanceError("vendored protocol commit differs from root provenance")
    protocol = REPO / "skills/archipelago/protocol"
    checked = 0
    for relative, expected in upstream.get("unchangedFiles", {}).items():
        if digest(protocol / relative) != expected:
            raise ProvenanceError(f"unchanged vendored file drifted: {relative}")
        checked += 1
    for record in upstream.get("modifiedFiles", []):
        relative = record.get("path")
        if not isinstance(relative, str) or digest(protocol / relative) != record.get(
            "resultSHA256"
        ):
            raise ProvenanceError(f"modified vendored file drifted: {relative}")
        if not record.get("changes") or not record.get("upstreamSHA256"):
            raise ProvenanceError(f"modified vendored file lacks review provenance: {relative}")
        checked += 1
    if digest(protocol / "LICENSE") != upstream.get("license", {}).get("sha256"):
        raise ProvenanceError("vendored protocol license drifted")

    if dependencies.get("schema") != "idc-executable-dependencies/v1":
        raise ProvenanceError("executable dependency schema differs")
    tools = dependencies.get("dependencies")
    if not isinstance(tools, list) or len(tools) < 10:
        raise ProvenanceError("executable dependency inventory is incomplete")
    names: set[str] = set()
    for item in tools:
        if not isinstance(item, dict) or set(item) != {
            "name",
            "pinMechanism",
            "status",
            "surfaces",
        }:
            raise ProvenanceError("invalid executable dependency record")
        if item["name"] in names or item["status"] not in ALLOWED_TOOL_STATUS:
            raise ProvenanceError(f"duplicate or unresolved executable dependency: {item['name']}")
        if not item["pinMechanism"] or not item["surfaces"]:
            raise ProvenanceError(f"unbounded executable dependency: {item['name']}")
        names.add(item["name"])

    material = provenance.get("shipped_test_material")
    if not isinstance(material, list) or len(material) != 1:
        raise ProvenanceError("shipped test material disclosure differs")
    test_record = material[0]
    test_path = REPO / test_record["path"]
    if digest(test_path).removeprefix("sha256:") != test_record.get("sha256"):
        raise ProvenanceError("self-contained scanner test material digest differs")
    if len(test_path.read_text(encoding="utf-8").splitlines()) != test_record.get("lines"):
        raise ProvenanceError("self-contained scanner test line count differs")

    notices = (REPO / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    for name in ("David Ondrej", "Matt Pocock", "Jake Van Clief", "Archipelago"):
        if name not in notices:
            raise ProvenanceError(f"third-party notice is missing {name}")
    return {
        "schema": "idc-provenance-report/v1",
        "pass": True,
        "registrySkills": len(skills),
        "sources": len(sources),
        "vendoredProtocolFiles": checked + 1,
        "toolFamilies": len(tools),
    }


def main(argv: Sequence[str] | None = None) -> int:
    if argv:
        print("PROVENANCE REFUSED - arguments are not accepted", file=sys.stderr)
        return 2
    try:
        report = verify()
    except (OSError, json.JSONDecodeError, ProvenanceError) as exc:
        print(f"PROVENANCE REFUSED - {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
