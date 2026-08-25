#!/usr/bin/env python3
"""ARCHIPELAGO P2 — dogfood-readiness v2 lane scoring.

Computes the internal merge-confidence band from an evidence bundle, enforcing:
  - claimSurface 'ui' with no runtime-journey artifacts  => band caps at 4
  - any 'falsified' claim                                => band 1 (blocked)
  - any 'unverified' claim                               => band caps at 3 (partial)
  - open runtime findings (console errors, flakes)       => band caps at 3
  - lane weights (informational score 0-100, band derives from it + caps):
      static 0.50 (0.35 for ui) · runtime-journey 0.25 · visual 0.15 (0.25 ui)
      recording 0.15 · resilience 0.10
Fusion with an external reviewer stays min() at the gate (see evidence bundle).

Usage:
  python3 scripts/dogfood_lanes.py ops/mission/evidence/bundle.json
  python3 scripts/dogfood_lanes.py bundle.json --write   # writes fusion.internalBand back
"""
import json, sys
from pathlib import Path

def band_from_score(score: float) -> int:
    return 5 if score >= 95 else 4 if score >= 80 else 3 if score >= 60 else 2 if score >= 40 else 1

def compute(bundle: dict):
    caps, notes = [5], []
    claims = bundle.get("claims", [])
    if any(c["status"] == "falsified" for c in claims):
        return 1, ["falsified claim present -> blocked (band 1)"]
    if any(c["status"] == "unverified" for c in claims):
        caps.append(3); notes.append("unverified claim(s) -> cap 3")
    lanes = bundle.get("lanes", {})
    surface = bundle.get("claimSurface", "lib")
    def lane_ok(name):
        l = lanes.get(name) or {}
        return bool(l.get("artifacts")), l.get("findings", [])
    weights = ({"static": .35, "runtime-journey": .25, "visual": .25, "recording": .15}
               if surface == "ui" else
               {"static": .50, "runtime-journey": .25, "visual": .15, "recording": .10})
    score, findings_open = 0.0, []
    for name, w in weights.items():
        ok, findings = lane_ok(name)
        findings_open += [f"{name}: {f}" for f in findings]
        if ok and not findings:
            score += w * 100
        elif ok:
            score += w * 50
    rok, rfind = lane_ok("resilience")
    findings_open += [f"resilience: {f}" for f in rfind]
    if rok and not rfind:
        score = min(100.0, score + 10)
    if surface == "ui" and not lane_ok("runtime-journey")[0]:
        caps.append(4); notes.append("ui surface without runtime-journey artifacts -> cap 4")
    if findings_open:
        caps.append(3); notes.append(f"{len(findings_open)} open runtime finding(s) -> cap 3")
    band = min(min(caps), band_from_score(score))
    notes.append(f"lane score {score:.0f}/100 -> raw band {band_from_score(score)}; caps {sorted(set(caps))}")
    return band, notes

def main():
    p = Path(sys.argv[1])
    bundle = json.loads(p.read_text())
    band, notes = compute(bundle)
    print(f"internal merge-confidence band: {band}/5")
    for n in notes:
        print(f"  - {n}")
    if "--write" in sys.argv:
        bundle.setdefault("fusion", {})["internalBand"] = band
        ext = bundle["fusion"].get("externalReview", {}).get("score")
        mode = bundle["fusion"].get("mode", "min")
        bundle["fusion"]["mergeConfidence"] = min(band, ext) if (ext and mode == "min") else band
        p.write_text(json.dumps(bundle, indent=2))
        print(f"  -> wrote fusion.internalBand={band}, mergeConfidence={bundle['fusion']['mergeConfidence']}")
    sys.exit(0 if band >= 5 else 1)

if __name__ == "__main__":
    main()
