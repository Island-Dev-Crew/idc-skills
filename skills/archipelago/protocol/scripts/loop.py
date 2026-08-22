#!/usr/bin/env python3
"""ARCHIPELAGO P3/P4 — the loop orchestrator.

Walks the mission's phases, runs gate commands, records evidence, enforces the
Pulse Gate (G3), routes loopbacks (P4), and appends to the tamper-evident ledger.

Loopback routing table (P4): a failed gate returns to the earliest stage whose
output the failure falsifies. Defaults:
    G0->S0  G1->S1  G2->S2  G3->S3  G4->S2  G5->S4  G6->S6
Override per-failure with --route (e.g. --route S1 when a G4 failure falsifies the plan).

Usage:
  python3 scripts/loop.py status
  python3 scripts/loop.py run-gates <phaseId>          # run every pending gate in phase
  python3 scripts/loop.py fail <gateId> --reason "..." [--route S1]
  python3 scripts/loop.py advance <stage>              # S0..S7 with pulse-gate check
  python3 scripts/loop.py close-phase <phaseId>        # all gates passed + fresh -> done
All mutations: update state.json -> append ledger -> regenerate pulse (SOTU hook).
"""
import argparse, hashlib, html, json, os, re, stat, subprocess, sys, time
from pathlib import Path

STATE = Path("ops/mission/state.json")
LEDGER = Path("ops/mission/ledger.jsonl")
ROUTE = {"G0": "S0", "G1": "S1", "G2": "S2", "G3": "S3", "G4": "S2", "G5": "S4", "G6": "S6"}
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def snapshot_repo_file(raw, label):
    root = Path.cwd().resolve()
    candidate = Path(raw)
    if candidate.is_symlink():
        sys.exit(f"{label} must not be a symlink")
    try:
        path = candidate.resolve(strict=True)
        path.relative_to(root)
    except (OSError, ValueError):
        sys.exit(f"{label} must be a regular file inside the repository")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode):
        sys.exit(f"{label} must be a regular file inside the repository")
    data = path.read_bytes()
    after = path.stat()
    identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_size, item.st_mtime_ns)
    if identity(before) != identity(after) or len(data) != after.st_size:
        sys.exit(f"{label} changed during capture")
    return data

def sha256(data):
    return "sha256:" + hashlib.sha256(data).hexdigest()

def validate_lock_binding(state):
    arch = state.get("archipelago", {})
    idea_data = snapshot_repo_file(arch.get("ideaLock", ""), "idea.lock")
    plan_data = snapshot_repo_file(arch.get("planLock", ""), "plan.lock")
    if sha256(idea_data) != arch.get("ideaLockSHA256"):
        sys.exit("idea.lock differs from the kickoff digest")
    if sha256(plan_data) != arch.get("planLockSHA256"):
        sys.exit("plan.lock differs from the kickoff digest")
    try:
        plan = json.loads(plan_data)
    except json.JSONDecodeError:
        sys.exit("plan.lock is not valid JSON")
    expected = [
        (phase["id"], gate["id"], gate["title"], gate["command"])
        for phase in plan.get("phases", []) for gate in phase.get("gates", [])
    ]
    observed = [
        (phase["id"], gate["id"], gate["title"], gate["command"])
        for phase in state.get("phases", []) for gate in phase.get("gates", [])
    ]
    if observed != expected:
        sys.exit("mission gate commands differ from the approved plan.lock")

def load():
    state = json.loads(STATE.read_text())
    validate_lock_binding(state)
    return state

def ledger_append(event: dict):
    prev = "0" * 64
    if LEDGER.exists():
        lines = LEDGER.read_text().strip().splitlines()
        if lines:
            prev = json.loads(lines[-1])["entryHash"]
    body = {"at": now(), "prevHash": prev, **event}
    body["entryHash"] = hashlib.sha256(
        json.dumps(body, sort_keys=True).encode()).hexdigest()
    with LEDGER.open("a") as f:
        f.write(json.dumps(body) + "\n")
    return body["entryHash"]

def ledger_verify():
    prev = "0" * 64
    for i, line in enumerate(LEDGER.read_text().strip().splitlines(), 1):
        e = json.loads(line)
        if e["prevHash"] != prev:
            return False, f"chain break at entry {i}"
        h = e.pop("entryHash")
        if hashlib.sha256(json.dumps(e, sort_keys=True).encode()).hexdigest() != h:
            return False, f"tampered entry {i}"
        prev = h
    return True, "chain intact"

def pulse(state):
    """G3 hook: regenerate the SOTU. Uses mission-control's render_sotu.mjs when present;
    otherwise writes a minimal deterministic pulse so the gate is never silently skipped."""
    state["mission"]["updated"] = now()
    STATE.write_text(json.dumps(state, indent=2))
    renderer = Path("ops/mission/render-sotu.mjs")
    outp = Path("ops/mission/state-of-the-union.html")
    if renderer.exists():
        node = Path(os.environ.get("IDC_ARCHIPELAGO_NODE", ""))
        expected = os.environ.get("IDC_ARCHIPELAGO_NODE_SHA256", "")
        if not node.is_absolute() or not node.is_file() or not os.access(node, os.X_OK):
            sys.exit("pulse renderer requires an absolute executable IDC_ARCHIPELAGO_NODE")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", expected) or sha256(node.read_bytes()) != expected:
            sys.exit("pulse renderer Node digest differs from IDC_ARCHIPELAGO_NODE_SHA256")
        rendered = subprocess.run([str(node), str(renderer)], check=False)
        if rendered.returncode != 0:
            sys.exit(f"pulse renderer failed with exit {rendered.returncode}")
    else:
        arch = state.get("archipelago", {})
        rows = "".join(
            f"<tr><td>{html.escape(str(p['id']))}</td><td>{html.escape(str(p['title']))}</td><td>{html.escape(str(p['status']))}</td>"
            f"<td>{sum(1 for g in p['gates'] if g['status']=='passed')}/{len(p['gates'])} gates</td></tr>"
            for p in state["phases"])
        mission_name = html.escape(str(state["mission"]["name"]))
        updated = html.escape(str(state["mission"]["updated"]))
        stage = html.escape(str(arch.get("loop",{}).get("stage","?")))
        outp.write_text(
            f"<!doctype html><meta charset='utf-8'><title>SOTU — {mission_name}</title>"
            f"<body style='background:#06070B;color:#E8EDF6;font-family:monospace;padding:40px'>"
            f"<h1 style='color:#00A3FF'>STATE OF THE UNION — {mission_name}</h1>"
            f"<p>updated {updated} · cycle {arch.get('loop',{}).get('cycle','?')} · "
            f"stage <b style='color:#FF7F00'>{stage}</b></p>"
            f"<table border=1 cellpadding=8 style='border-color:#1B2233'>{rows}</table>"
            f"<p>loopbacks: {len(arch.get('loop',{}).get('loopbacks',[]))} · "
            f"generated — never hand-edited</p></body>")
    return outp

def pulse_gate_ok(state):
    """G3: state must not be stale — every non-pending phase behind the active one is closed."""
    active = state["resume"].get("activePhase")
    seen_active = False
    for p in state["phases"]:
        if p["id"] == active:
            seen_active = True
        if not seen_active and p["status"] not in ("done",):
            return False, f"phase {p['id']} precedes active {active} but is '{p['status']}'"
    return True, "fresh"

def cmd_status(_):
    s = load()
    a = s["archipelago"]["loop"]
    print(f"mission {s['mission']['name']} · cycle {a['cycle']} · stage {a['stage']} · "
          f"loopbacks {len(a['loopbacks'])}")
    for p in s["phases"]:
        g = f"{sum(1 for x in p['gates'] if x['status']=='passed')}/{len(p['gates'])}"
        print(f"  {p['id']} [{p['status']:<11}] gates {g}  {p['title']}")
    if LEDGER.exists():
        ok, msg = ledger_verify()
        print(f"ledger: {msg} ({len(LEDGER.read_text().strip().splitlines())} entries)")
        if not ok:
            sys.exit(1)

def cmd_run_gates(args):
    s = load()
    phase = next(p for p in s["phases"] if p["id"] == args.phase)
    if phase["status"] == "pending":
        phase["status"] = "in_progress"
    evdir = Path("ops/mission/evidence"); evdir.mkdir(parents=True, exist_ok=True)
    all_pass = True
    for g in phase["gates"]:
        if g["status"] == "passed":
            continue
        print(f"gate {g['id']}: {g['command']}")
        r = subprocess.run(g["command"], shell=True, capture_output=True, text=True)
        evp = evdir / f"{g['id']}-{time.time_ns()}.txt"
        evp.write_text(f"$ {g['command']}\nexit {r.returncode}\n--- stdout ---\n{r.stdout}\n--- stderr ---\n{r.stderr}")
        g["evidence"] = str(evp); g["lastRun"] = now()
        g["status"] = "passed" if r.returncode == 0 else "failed"
        if g["status"] == "passed":
            for loopback in s["archipelago"]["loop"].get("loopbacks", []):
                if loopback.get("gate") == g["id"] and not loopback.get("resolvedAt"):
                    loopback["resolvedAt"] = now()
        sha = hashlib.sha256(evp.read_bytes()).hexdigest()
        ledger_append({"event": "gate-run", "gate": g["id"], "status": g["status"],
                       "command": g["command"], "evidence": str(evp), "evidenceSha256": sha})
        print(f"   -> {g['status']} (evidence {evp.name}, sha {sha[:12]}…)")
        if g["status"] == "failed":
            all_pass = False
    pulse(s)
    sys.exit(0 if all_pass else 1)

def cmd_fail(args):
    s = load()
    matches = [
        gate
        for phase in s["phases"]
        for gate in phase["gates"]
        if gate["id"] == args.gate
    ]
    if len(matches) != 1:
        sys.exit(f"unknown or duplicate gate id: {args.gate}")
    match = re.search(r"(?:^|-)G([0-6])(?:$|-)", args.gate)
    if match is None:
        sys.exit(f"gate id has no G0-G6 family: {args.gate}")
    gate_family = f"G{match.group(1)}"
    to_stage = args.route or ROUTE.get(gate_family, "S2")
    matches[0]["status"] = "failed"
    lb = {"gate": args.gate, "fromGate": gate_family, "toStage": to_stage, "reason": args.reason, "at": now()}
    s["archipelago"]["loop"]["loopbacks"].append(lb)
    s["archipelago"]["loop"]["stage"] = to_stage
    ledger_append({"event": "loopback", **lb})
    pulse(s)
    print(f"[LOOPBACK] {gate_family} -> {to_stage}: {args.reason}")

def cmd_advance(args):
    s = load()
    ok, why = pulse_gate_ok(s)
    if not ok:
        print(f"[HALT] G3 pulse gate: {why} — undocumented progress is unverified progress")
        sys.exit(1)
    cur = s["archipelago"]["loop"]["stage"]
    if STAGES.index(args.stage) < STAGES.index(cur):
        # moving backward is a loopback, use `fail`
        sys.exit(f"use 'fail' to move backward ({cur} -> {args.stage})")
    s["archipelago"]["loop"]["stage"] = args.stage
    if args.stage == "S0":
        s["archipelago"]["loop"]["cycle"] += 1
    ledger_append({"event": "stage-advance", "from": cur, "to": args.stage})
    pulse(s)
    print(f"[ADVANCE] {cur} -> {args.stage}")

def cmd_close_phase(args):
    s = load()
    phase = next(p for p in s["phases"] if p["id"] == args.phase)
    bad = [g["id"] for g in phase["gates"] if g["status"] != "passed"]
    if bad:
        sys.exit(f"cannot close {args.phase}: gates not passed: {bad}")
    gate_ids = {gate["id"] for gate in phase["gates"]}
    open_loopbacks = [
        item.get("gate")
        for item in s["archipelago"]["loop"].get("loopbacks", [])
        if item.get("gate") in gate_ids and not item.get("resolvedAt")
    ]
    if open_loopbacks:
        sys.exit(f"cannot close {args.phase}: unresolved loopbacks: {open_loopbacks}")
    phase["status"] = "done"
    nxt = next((p["id"] for p in s["phases"] if p["status"] != "done"), None)
    s["resume"]["activePhase"] = nxt
    ledger_append({"event": "phase-close", "phase": args.phase, "next": nxt})
    pulse(s)
    print(f"[CLOSE] {args.phase} done -> active {nxt}")

def cmd_verify_ledger(_):
    ok, msg = ledger_verify()
    print(f"[{'PASS' if ok else 'FAIL'}] ledger: {msg}")
    sys.exit(0 if ok else 1)

def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    r = sub.add_parser("run-gates"); r.add_argument("phase")
    f = sub.add_parser("fail"); f.add_argument("gate"); f.add_argument("--reason", required=True); f.add_argument("--route")
    a = sub.add_parser("advance"); a.add_argument("stage", choices=STAGES)
    c = sub.add_parser("close-phase"); c.add_argument("phase")
    sub.add_parser("verify-ledger")
    args = ap.parse_args()
    {"status": cmd_status, "run-gates": cmd_run_gates, "fail": cmd_fail,
     "advance": cmd_advance, "close-phase": cmd_close_phase,
     "verify-ledger": cmd_verify_ledger}[args.cmd](args)

if __name__ == "__main__":
    main()
