#!/usr/bin/env python3
"""Build the deterministic 31-record G0 ledger from preserved Kimi artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

try:
    from .validate_evidence import SourceBundle
except ImportError:  # direct ``python scripts/build_kimi_evidence.py`` execution
    from validate_evidence import SourceBundle  # type: ignore[no-redef]


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "ops/mission/evidence/2.0.4"
RELEASE = "26b9285c1fe11a3ef875a34ff30faa0275eddf24"
ROSTER = "source/kimi/round3-calibration.md"
SOURCE_BUNDLE = "source/kimi/KIMI-K3-IDC-SKILLS-2.0.3-PENTEST.tar.gz"
SOURCE_BUNDLE_SHA256 = "6b471d41a3d7adec021690ceb007e949140ec05061a165674709d6511628e81d"
SOURCE_BUNDLE_PREFIX = "KIMI-K3-IDC-SKILLS-2.0.3-PENTEST/evidence/"
E = "source/kimi/lanes/evidence/"
L = "source/kimi/lanes/"


def sha(relative: str) -> str:
    return hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()


def location(path: str, start: int, end: int) -> list[dict[str, object]]:
    return [{"revision": RELEASE, "path": path, "startLine": start, "endLine": end}]


ROWS: list[dict[str, object]] = [
    {"id":"K3-203-001","title":"In-band first-contact trust anchors permit a fully self-consistent forged release","source":location("integrity/README.md",14,18),"fixture":E+"K3-0-challenge-c1/forged-install.json","output":E+"K3-0-challenge-c1/genuine-vs-forged.json","status":"confirmed","rationale":"Two independent Kimi forgeries reached attacker-controlled authority when the first trust value was learned in-band; a genuinely pinned launcher rejected them."},
    {"id":"K3-203-002","title":"Attached or mid-command redirection bypasses guarded Git subcommands","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",165,170),"fixture":E+"K3-8-p2-gitguard/verdicts.txt","output":E+"K3-4-redir/proofs.txt","status":"confirmed","rationale":"The preserved guard verdicts and real-Git proofs show dangerous operations executed while the 2.0.3 classifier allowed them."},
    {"id":"K3-203-003","title":"Invoked bang alias composes with call-site arguments","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",1058,1092),"fixture":E+"K3-8-p2-gitguard/verdicts.txt","output":E+"K3-4-bangargs/proofs.txt","status":"confirmed","rationale":"The 2.0.3 alias model discarded decisive call-site arguments; the preserved proof demonstrates the composed Git execution."},
    {"id":"K3-203-004","title":"A leading data or blob candidate suppresses later external candidates","source":location("skills/self-contained-ship/scripts/scan-egress.sh",2518,2528),"fixture":E+"K3-5-c1-srcset/fixture.html","output":E+"K3-5-c1-srcset/scan.out","status":"confirmed","rationale":"The exact scanner-green fixture and Chromium request log demonstrate later srcset/imagesrcset/ping candidates were live."},
    {"id":"K3-203-005","title":"Bare semicolon meta refresh network paths are missed","source":location("skills/self-contained-ship/scripts/scan-egress.sh",2951,2960),"fixture":E+"K3-5-c2-meta/m.html","output":E+"K3-5-c2-meta/scan.out","status":"confirmed","rationale":"The preserved meta fixture passed the 2.0.3 scanner while the runtime navigation was observed."},
    {"id":"K3-203-006","title":"Binary waivers launder browser-active wide or control-byte markup","source":location("skills/self-contained-ship/scripts/scan-egress.sh",3062,3088),"fixture":E+"K3-5-c3-utf16/u16.html","output":E+"K3-5-c3-utf16/hits.log","status":"confirmed","rationale":"The UTF-16 fixture was waivable as binary even though Chromium attempted its script request."},
    {"id":"K3-203-007","title":"Literal JavaScript markup-injection sinks are unmodeled","source":location("skills/self-contained-ship/scripts/scan-egress.sh",2328,2337),"fixture":E+"K3-5-c4-domwrite/d.js","output":E+"K3-5-c4-domwrite/hits.log","status":"confirmed","rationale":"Preserved document.write and innerHTML fixtures passed statically and produced runtime requests."},
    {"id":"K3-203-008","title":"Artifact-local waiver suppresses the scanner uncertainty tripwire","source":[{"revision":RELEASE,"path":"skills/self-contained-ship/scripts/scan-egress.sh","startLine":191,"endLine":191},{"revision":RELEASE,"path":"skills/self-contained-ship/scripts/scan-egress.sh","startLine":2969,"endLine":2980}],"fixture":E+"K3-5-c7-waiver/u2.ts","output":E+"K3-5-c7-waiver/scan.out","status":"confirmed","rationale":"The corrected binding uses u2.ts, whose exact bytes appear in the preserved scan output and show UNCERT converted to WAIVED with rc=0."},
    {"id":"K3-203-009","title":"Hook payload extraction accepts the first skill field without cross-checking all fields","source":location("scripts/pretooluse-skill-integrity.py",30,41),"fixture":E+"K3-8-hook/NOTES.txt","output":E+"K3-3-E9/summary.txt","status":"theoretical","rationale":"Mechanics reproduce with conflicting fields, but no supported harness payload with attacker-controlled duplicates was observed."},
    {"id":"K3-203-010","title":"PreToolUse installed-skill verification omits POSIX mode and xattrs","source":location("scripts/skill_integrity.py",1286,1310),"fixture":L+"K3-3.md","output":E+"K3-3-E7/summary.txt","status":"confirmed","rationale":"The released hook compared the signed skill file map at byte-record scope and approved a mode-flipped installed executable."},
    {"id":"K3-203-011","title":"Broken stderr changes intended hook BLOCK exit 2 into exit 120","source":location("scripts/pretooluse-skill-integrity.py",133,145),"fixture":E+"K3-3-E10/failopen.txt","output":E+"K3-3-E10/summary.txt","status":"confirmed","rationale":"The preserved broken-pipe experiment records the noncanonical but still fail-closed interpreter exit."},
    {"id":"K3-203-012","title":"Direct non-launcher hook routing honors Python path shadowing","source":location("scripts/pretooluse-skill-integrity.py",1,24),"fixture":L+"K3-3.md","bundleMember":SOURCE_BUNDLE_PREFIX+"K3-203-012/stdout.txt","status":"theoretical","rationale":"Direct invocation inherits Python startup semantics; the externally pinned isolated launcher remains the authoritative path."},
    {"id":"K3-203-013","title":"Incomplete HTTP body exception escapes freshness fetch normalization","source":location("bootstrap/idc_verify_fresh.py",756,775),"fixture":E+"K3-2-attacks/scen_g456.py","output":E+"K3-2-attacks/scen_g456.log","status":"confirmed","rationale":"The preserved mock response raises IncompleteRead outside the released catch tuple; execution still fails closed with a traceback."},
    {"id":"K3-203-014","title":"Unexpected consumer exception escapes freshness main normalization","source":location("bootstrap/idc_verify_fresh.py",1557,1575),"fixture":E+"K3-2-attacks/scen_g7plus.py","output":E+"K3-2-attacks/scen_g7plus.log","status":"confirmed","rationale":"The preserved consumer runner raises RuntimeError outside the released catch list; no ready state is emitted."},
    {"id":"K3-203-015","title":"clean.requireForce false enables deletion without a force flag","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",110,140),"fixture":E+"K3-4-cleanreqforce/proofs.txt","output":E+"K3-4-cleanreqforce/proofs.txt","status":"confirmed","rationale":"A disposable repository proves untracked files were deleted while the advisory classifier allowed the command."},
    {"id":"K3-203-016","title":"Plumbing ref rewrites and forced tags are outside the released guard surface","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",110,140),"fixture":E+"K3-4-updateref/proofs.txt","output":E+"K3-4-updateref/proofs.txt","status":"confirmed","rationale":"The preserved update-ref and tag-force proofs mutate disposable refs under an allow verdict."},
    {"id":"K3-203-017","title":"Bash brace expansion executes outside the lexical Git claim","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",628,650),"fixture":E+"K3-4-brace/proofs.txt","output":E+"K3-4-brace/proofs.txt","status":"confirmed","rationale":"The shell expands git {push,} into an executable Git command the released classifier did not model."},
    {"id":"K3-203-018","title":"Prefixed webkit image-set candidates are not scanned","source":location("skills/self-contained-ship/scripts/scan-egress.sh",2590,2640),"fixture":E+"K3-5-c5-webkit/w.css","output":E+"K3-5-c5-webkit/hits.log","status":"confirmed","rationale":"The CSS fixture passed statically and supporting Chromium fetched the preserved external candidate."},
    {"id":"K3-203-019","title":"XML stylesheet processing instructions are invisible","source":location("skills/self-contained-ship/scripts/scan-egress.sh",2670,2730),"fixture":E+"K3-5-c6-xmlstylesheet/x.xml","output":E+"K3-5-c6-xmlstylesheet/scan.out","status":"confirmed","rationale":"The released scanner returned green for the exact XML stylesheet fixture."},
    {"id":"K3-203-020","title":"Archipelago references runnable protocol scripts that are not vendored","source":location("skills/archipelago/SKILL.md",45,55),"fixture":L+"K3-6.md","bundleMember":SOURCE_BUNDLE_PREFIX+"K3-203-020/stdout.txt","status":"confirmed","rationale":"The released skill names executable protocol paths absent from its signed island and discloses the upstream prose pin."},
    {"id":"K3-203-021","title":"Self-contained-ship executable fixture matrix is undisclosed in its skill body","source":location("skills/self-contained-ship/SKILL.md",14,24),"fixture":L+"K3-6.md","output":E+"K3-6-functional/functional-checks.txt","status":"confirmed","rationale":"The 2.0.3 skill links the scanner but not its executable 2,067-line regression matrix; the file is nevertheless signed."},
    {"id":"K3-203-022","title":"Dangerous-Git guard documents compatibility fail-open on missing runtime inputs","source":location("skills/agent-guardrails/scripts/block-dangerous-git.sh",63,94),"fixture":L+"K3-7.md","output":E+"K3-7-bash/guard-failopen.txt","status":"confirmed","rationale":"Missing payload/interpreters produce an announced allow in the released advisory mode; it was explicitly documented as non-authoritative."},
    {"id":"K3-203-023","title":"In-tree verifier resolves ssh-keygen through inherited PATH","source":location("scripts/skill_integrity.py",790,920),"fixture":L+"K3-7.md","bundleMember":SOURCE_BUNDLE_PREFIX+"K3-203-023/stdout.txt","status":"confirmed","rationale":"Bare ssh-keygen subprocess arguments are present in the released in-tree verifier; the external launcher pins the authoritative executable separately."},
    {"id":"K3-203-024","title":"Minimum Python runtime is undocumented and 3.9 fails incidentally","source":location("scripts/install.py",280,290),"fixture":L+"K3-7.md","output":E+"K3-7-python39/summary.txt","status":"confirmed","rationale":"The preserved Python 3.9 run fails on APIs introduced in 3.10 while the 3.12 control passes."},
    {"id":"K3-203-025","title":"Extended per-island lineage is not fully represented in top-level provenance notices","source":location("provenance.json",1,63),"fixture":L+"K3-6.md","output":E+"K3-6-scans/extref-parity-notes.txt","status":"confirmed","rationale":"The preserved comparison distinguishes locked repositories from additional registry-level idea and vocabulary lineage; it does not assert a license violation."},
    {"id":"K3-203-026","title":"Staged consumer tree is not rehashed immediately before consumer execution","source":location("bootstrap/idc_verify_fresh.py",1347,1387),"fixture":E+"K3-2-attacks/scen_g7plus.py","output":E+"K3-2-attacks/scen_g7plus.log","status":"theoretical","rationale":"A same-UID consumer-runner mutation can alter staged bytes after content verification; this is a documented same-authority residual, not a demonstrated external attacker path."},
    {"id":"K3-203-027","title":"Forgeable handoff marker and inert NaN fields do not grant authority","source":location("scripts/install.py",65,80),"fixture":E+"K3-3-E2/marker.txt","output":E+"K3-3-E2/install-forged.json","status":"false-positive","rationale":"The marker only unlocks routing and all five signed content checks still run; launcher parsing rejects the NaN-bearing form."},
    {"id":"K3-203-028","title":"Research skill paid API and password-manager access are explicitly gated behavior","source":location("skills/research/SKILL.md",33,52),"fixture":L+"K3-6.md","output":E+"K3-6-scans/k3-6-independent-url-scan.txt","status":"false-positive","rationale":"The fixed endpoint, separate spend approval, and process-memory credential custody are disclosed controls for an operator-invoked capability, not evidence of malice."},
    {"id":"K3-203-029","title":"Video analysis downloads the user-supplied media URL by design","source":location("skills/video-analysis/scripts/grab.sh",14,58),"fixture":L+"K3-6.md","bundleMember":SOURCE_BUNDLE_PREFIX+"K3-203-029/stdout.txt","status":"confirmed","rationale":"The reviewed script intentionally invokes yt-dlp on the requested URL with no-playlist, bounded media quality, scratch-output, and fail-closed checks."},
    {"id":"K3-203-030","title":"Public release prose contains stale lineage and candidate-state references","source":location("CHANGELOG.md",3,13),"fixture":L+"K3-7.md","output":E+"K3-7-publication/release.json","status":"confirmed","rationale":"Three cited staging commits and some PR/CI identifiers are not resolvable from the public repository, and the shipped tag retains pre-promotion candidate wording."},
    {"id":"K3-203-031","title":"Windows mode ownership and ssh-keygen fallback claims lacked a real Windows seat","source":[{"revision":RELEASE,"path":"scripts/skill_integrity.py","startLine":540,"endLine":615},{"revision":RELEASE,"path":"bootstrap/idc_verify_fresh.py","startLine":207,"endLine":215}],"fixture":L+"K3-7.md","output":E+"K3-7-filemode/nofm2.json","status":"unverified","rationale":"Linux simulation established fail-closed mode behavior, but the named Windows NTFS/OpenSSH dependencies were not executed in the Kimi engagement."}
]


BUNDLE_CAPTURES = {
    str(row["id"]): str(row["bundleMember"])
    for row in ROWS
    if "bundleMember" in row
}

# Every sentinel names decisive text in the bound UTF-8 bytes. Generic scanner-green
# observations also bind a fixture-specific token so a sibling green output cannot be
# substituted without losing the semantic leg.
SEMANTIC_ASSERTIONS: dict[str, list[dict[str, str]]] = {
    "K3-203-001": [{"target": "capture", "contains": "public-key fingerprint mismatch"}],
    "K3-203-002": [{"target": "capture", "contains": "EXECUTED=YES"}],
    "K3-203-003": [{"target": "capture", "contains": "bang-alias call-site args"}],
    "K3-203-004": [
        {"target": "capture", "contains": "scan-egress: PASS"},
        {"target": "fixture", "contains": "srcset-leak.png"},
    ],
    "K3-203-005": [
        {"target": "capture", "contains": "scan-egress: PASS"},
        {"target": "fixture", "contains": "meta-bare"},
    ],
    "K3-203-006": [{"target": "capture", "contains": "/utf16-leak.js"}],
    "K3-203-007": [{"target": "capture", "contains": "/innerhtml-leak.png"}],
    "K3-203-008": [{"target": "capture", "contains": "WAIVED /tmp/K3-5/t/c11/u2.ts"}],
    "K3-203-009": [{"target": "capture", "contains": "first match wins"}],
    "K3-203-010": [{"target": "capture", "contains": "chmod 644 on installed"}],
    "K3-203-011": [{"target": "capture", "contains": "BROKEN PIPE"}],
    "K3-203-012": [{"target": "capture", "contains": "shadow-json-took-over"}],
    "K3-203-013": [{"target": "capture", "contains": "IncompleteRead mid-body"}],
    "K3-203-014": [{"target": "capture", "contains": "consumer raises RuntimeError"}],
    "K3-203-015": [{"target": "capture", "contains": "gone1 exists=NO"}],
    "K3-203-016": [{"target": "capture", "contains": "update-ref move x"}],
    "K3-203-017": [{"target": "capture", "contains": "EXECUTED=YES"}],
    "K3-203-018": [{"target": "capture", "contains": "/webkit-imageset.png"}],
    "K3-203-019": [
        {"target": "capture", "contains": "scan-egress: PASS"},
        {"target": "fixture", "contains": "xml-stylesheet"},
    ],
    "K3-203-020": [
        {
            "target": "capture",
            "contains": "referenced runnable scripts absent from the signed closure",
        }
    ],
    "K3-203-021": [{"target": "capture", "contains": "test-scan-egress.sh: RESULT"}],
    "K3-203-022": [{"target": "capture", "contains": "guard OPEN"}],
    "K3-203-023": [{"target": "capture", "contains": "caller PATH"}],
    "K3-203-024": [{"target": "capture", "contains": "3.12: 101/101 OK"}],
    "K3-203-025": [
        {"target": "capture", "contains": "manifest enumerates 12 external references"}
    ],
    "K3-203-026": [{"target": "capture", "contains": "[GAP-OBSERVED]"}],
    "K3-203-027": [{"target": "capture", "contains": '"authority": "content-only"'}],
    "K3-203-028": [
        {
            "target": "capture",
            "contains": "research/SKILL.md:44:https://deepapi.co/v1/research/deep",
        }
    ],
    "K3-203-029": [
        {
            "target": "capture",
            "contains": "video-analysis/SKILL.md:20:https://youtu.be/ID",
        }
    ],
    "K3-203-030": [{"target": "capture", "contains": '"tag_name": "2.0.3"'}],
    "K3-203-031": [
        {"target": "capture", "contains": "repositoryFiles differs from the signed manifest"}
    ],
}


def main() -> int:
    if sha(SOURCE_BUNDLE) != SOURCE_BUNDLE_SHA256:
        raise RuntimeError("pinned Kimi source bundle SHA-256 differs")
    bundle = SourceBundle(
        ROOT,
        {"path": SOURCE_BUNDLE, "sha256": SOURCE_BUNDLE_SHA256},
    )
    findings = []
    for row in ROWS:
        fixture = str(row["fixture"])
        fixture_digest = sha(fixture)
        finding_id = str(row["id"])
        status = str(row["status"])
        assertions = SEMANTIC_ASSERTIONS[finding_id]
        if finding_id in BUNDLE_CAPTURES:
            member = BUNDLE_CAPTURES[finding_id]
            capture_bytes = bundle.read(member, f"{finding_id}.capture.member")
            capture_source = {"type": "bundle-member", "member": member}
        else:
            output = str(row["output"])
            capture_bytes = (ROOT / output).read_bytes()
            capture_source = {"type": "local", "path": output}
        fixture_bytes = (ROOT / fixture).read_bytes()
        for assertion in assertions:
            target = capture_bytes if assertion["target"] == "capture" else fixture_bytes
            target.decode("utf-8")
            if assertion["contains"].encode("utf-8") not in target:
                raise RuntimeError(
                    f"semantic sentinel for {finding_id} is absent: {assertion!r}"
                )
        findings.append({
            "id": finding_id,
            "title": row["title"],
            "sourceLocations": row["source"],
            "fixture": {
                "anchor": "candidate-preserved",
                "path": fixture,
                "sha256": fixture_digest,
            },
            "capture": {
                "kind": "preserved-observation",
                "source": capture_source,
                "sha256": hashlib.sha256(capture_bytes).hexdigest(),
                "fixtureSha256": fixture_digest,
            },
            "semanticBinding": {
                "description": "The listed exact sentinel occurs in the named preserved UTF-8 bytes; this is byte emission, not a claim that a command was executed.",
                "assertions": assertions,
            },
            "discriminator": {
                "description": "The release source range resolves, the candidate-preserved fixture and preserved capture digest-match, and each semantic sentinel is present. Candidate regression tests are separate downstream gates.",
                "passed": status not in {"theoretical", "unverified"},
            },
            "disposition": {"status": status, "rationale": row["rationale"]},
        })
    package = {
        "schema": "idc.security-evidence/v2",
        "releaseRevision": RELEASE,
        "sourceBundle": {
            "path": SOURCE_BUNDLE,
            "sha256": SOURCE_BUNDLE_SHA256,
        },
        "sourceRoster": {"path": ROSTER, "sha256": sha(ROSTER)},
        "expectedFindingIds": [str(row["id"]) for row in ROWS],
        "findings": findings,
    }
    destination = ROOT / "evidence.json"
    destination.write_text(json.dumps(package, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {destination} records={len(findings)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
