#!/usr/bin/env python3
"""Render the public Forge 50 catalog deterministically from the registry."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Sequence


ROUTES: tuple[dict[str, Any], ...] = (
    {
        "name": "Build",
        "anchor": "build",
        "promise": "Turn an idea into a scoped, testable implementation without confusing motion with progress.",
        "skills": (
            "job-to-be-done",
            "idc-skill-authoring",
            "prototype",
            "spec-pipeline",
            "gauntlet-loop",
        ),
        "loop": "job-to-be-done → prototype → spec-pipeline → gauntlet-loop",
    },
    {
        "name": "Research",
        "anchor": "research",
        "promise": "Replace plausible answers with sourced findings and context that survives the session.",
        "skills": (
            "grill",
            "research",
            "video-analysis",
            "data-source-map",
            "productionize-opinion",
        ),
        "loop": "grill → research/video-analysis → data-source-map → productionize-opinion",
    },
    {
        "name": "Operate",
        "anchor": "operate",
        "promise": "Coordinate agents and recurring work without losing ownership or control-plane history.",
        "skills": (
            "console-as-code",
            "lane-claim",
            "worktree-fleet",
            "model-routing",
            "agent-schedule",
        ),
        "loop": "console-as-code → lane-claim → worktree-fleet/model-routing → agent-schedule",
    },
    {
        "name": "Verify & Ship",
        "anchor": "verify--ship",
        "promise": "Turn “it works” into recomputable evidence, independent review, and exact-revision transport proof.",
        "skills": (
            "computer-use-smoke",
            "evidence-packet",
            "cross-family-review",
            "self-contained-ship",
            "transport-complete",
        ),
        "loop": "computer-use-smoke → evidence-packet → cross-family-review → self-contained-ship → transport-complete",
    },
    {
        "name": "Architect",
        "anchor": "architect",
        "promise": "Shape repository, domain, and module boundaries so agents navigate an explicit system.",
        "skills": (
            "arch-survey",
            "deep-modules",
            "folder-workspace",
            "workspace-scaffold",
            "archipelago",
        ),
        "loop": "arch-survey → deep-modules → folder-workspace/workspace-scaffold → archipelago",
    },
)


class CatalogError(RuntimeError):
    """The registry cannot produce a trustworthy catalog."""


def load_registry(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"cannot read registry {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise CatalogError("registry must be a JSON object")
    return value


def registry_entries(registry: dict[str, Any]) -> tuple[list[str], dict[str, dict[str, Any]]]:
    order = registry.get("buildOrder")
    entries = registry.get("skills")
    if not isinstance(order, list) or not all(isinstance(name, str) for name in order):
        raise CatalogError("registry.buildOrder must be an array of names")
    if not isinstance(entries, list) or not all(isinstance(item, dict) for item in entries):
        raise CatalogError("registry.skills must be an array of objects")
    by_name: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise CatalogError("every registry skill requires a name")
        if name in by_name:
            raise CatalogError(f"duplicate registry skill: {name}")
        by_name[name] = entry
    if len(order) != 50 or len(by_name) != 50 or set(order) != set(by_name):
        raise CatalogError(
            f"catalog requires the same 50 skills in buildOrder and skills; "
            f"order={len(order)} records={len(by_name)}"
        )
    curated = [skill for route in ROUTES for skill in route["skills"]]
    if len(curated) != 25 or len(set(curated)) != 25:
        raise CatalogError("outcome routes must name 25 unique editorial starting points")
    missing = sorted(set(curated) - set(by_name))
    if missing:
        raise CatalogError(f"outcome routes reference missing skills: {missing}")
    return order, by_name


def render(registry: dict[str, Any]) -> str:
    order, by_name = registry_entries(registry)
    lines = [
        "# Forge 50 catalog",
        "",
        "This index is generated from [`skills/registry.json`](../skills/registry.json). "
        "The five outcome routes are editorial starting points—not popularity rankings, "
        "certifications, or an exhaustive taxonomy. Every skill remains independently "
        "addressable; successful execution is task-, dependency-, platform-, and harness-specific.",
        "",
        "## Choose an outcome",
        "",
    ]
    for route in ROUTES:
        skill_links = " · ".join(
            f"[`{name}`](#{name})" for name in route["skills"]
        )
        lines.extend(
            [
                f"### {route['name']}",
                "",
                route["promise"],
                "",
                f"**Start here:** {skill_links}",
                "",
                f"**Recommended loop:** `{route['loop']}`",
                "",
            ]
        )
    lines.extend(
        [
            "## All fifty islands",
            "",
            "Invocation values come from the registry. Provenance is reproduced as recorded; "
            "see [`provenance.json`](../provenance.json) and "
            "[`THIRD-PARTY-NOTICES.md`](../THIRD-PARTY-NOTICES.md) for source-level detail. "
            "The separate [validation record](report.html) includes historical evidence epochs "
            "and a named residual for each island; it is not a blanket current certification.",
            "",
        ]
    )
    for number, name in enumerate(order, start=1):
        entry = by_name[name]
        summary = entry.get("summary")
        invocation = entry.get("invocation")
        provenance = entry.get("provenance")
        path = entry.get("path")
        if not all(isinstance(value, str) and value for value in (summary, invocation, provenance, path)):
            raise CatalogError(f"{name}: path, invocation, provenance, and summary are required")
        lines.extend(
            [
                f'<a id="{name}"></a>',
                "",
                f"### {number:02d}. [{name}](../skills/{path}/SKILL.md)",
                "",
                summary,
                "",
                f"- **Invocation:** `{invocation}`",
                f"- **Recorded lineage:** {provenance}",
                "",
            ]
        )
    lines.extend(
        [
            "---",
            "",
            "Generated by `python3 -B scripts/render_catalog.py`. Edit the registry or the "
            "renderer, then regenerate; do not hand-edit this file.",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=root / "skills" / "registry.json")
    parser.add_argument("--output", type=Path, default=root / "docs" / "catalog.md")
    parser.add_argument("--check", action="store_true", help="fail unless output is current")
    args = parser.parse_args(argv)
    try:
        rendered = render(load_registry(args.registry))
        expected = rendered.encode("utf-8")
        if args.check:
            try:
                actual = args.output.read_bytes()
            except OSError as exc:
                raise CatalogError(f"cannot read catalog {args.output}: {exc}") from exc
            if actual != expected:
                raise CatalogError("catalog bytes differ from deterministic renderer output")
            print(f"CATALOG OK — skills=50 path={args.output}")
            return 0
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
        print(f"CATALOG RENDERED — skills=50 path={args.output}")
        return 0
    except CatalogError as exc:
        print(f"CATALOG FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
