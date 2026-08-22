#!/usr/bin/env python3
"""P0-G2: falsification tests for dogfood lane scoring — the scorer must be able to fail."""
import sys
sys.path.insert(0, "scripts")
from dogfood_lanes import compute

art = lambda i: [{"id": i, "path": "x", "sha256": "0"*64, "kind": "test-output"}]
checks = []
# 1. UI surface without runtime lane must cap at 4
b, _ = compute({"claimSurface": "ui", "claims": [{"claim": "c", "status": "verified", "evidenceRefs": ["a"]}],
                "lanes": {"static": {"artifacts": art("a"), "findings": []}}})
checks.append(("ui without runtime caps at <=4", b <= 4))
# 2. Full-lane ui bundle, no findings, must reach 5
full = {l: {"artifacts": art(l), "findings": []} for l in ["static", "runtime-journey", "visual", "recording", "resilience"]}
b, _ = compute({"claimSurface": "ui", "claims": [{"claim": "c", "status": "verified", "evidenceRefs": ["a"]}], "lanes": full})
checks.append(("full-lane ui reaches 5", b == 5))
# 3. unverified claim caps at 3
b, _ = compute({"claimSurface": "ui", "claims": [{"claim": "c", "status": "unverified", "evidenceRefs": []}], "lanes": full})
checks.append(("unverified caps at <=3", b <= 3))
# 4. falsified claim -> band 1
b, _ = compute({"claimSurface": "cli", "claims": [{"claim": "c", "status": "falsified", "evidenceRefs": []}], "lanes": full})
checks.append(("falsified -> band 1", b == 1))
# 5. open console-error finding caps at 3
bad = dict(full); bad["runtime-journey"] = {"artifacts": art("r"), "findings": ["console error: x"]}
b, _ = compute({"claimSurface": "ui", "claims": [{"claim": "c", "status": "verified", "evidenceRefs": ["a"]}], "lanes": bad})
checks.append(("open finding caps at <=3", b <= 3))
ok = True
for name, passed in checks:
    print(f"[{'PASS' if passed else 'FAIL'}] {name}")
    ok &= passed
sys.exit(0 if ok else 1)
