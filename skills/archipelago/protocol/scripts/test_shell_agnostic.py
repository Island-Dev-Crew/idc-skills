#!/usr/bin/env python3
"""Grep-loop probe: the enforceable invariant behind the PowerShell 5.1 claim —
no gate command in plan.lock or state.json uses shell-conjunction operators."""
import json, sys
from pathlib import Path
bad = []
for f in ["ops/mission/plan.lock.json", "ops/mission/state.json"]:
    d = json.loads(Path(f).read_text())
    for ph in d.get("phases", []):
        for g in ph.get("gates", []):
            cmd = g.get("command", "")
            if "&&" in cmd or "||" in cmd or ";" in cmd:
                bad.append(f"{f}:{g['id']}: {cmd}")
if bad:
    print("[FAIL] shell-conjunction operators found:"); [print("  -", b) for b in bad]; sys.exit(1)
print("[PASS] all gate commands shell-agnostic (PowerShell 5.1 / cmd / POSIX safe)")
