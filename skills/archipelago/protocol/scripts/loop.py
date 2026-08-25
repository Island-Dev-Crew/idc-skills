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
import argparse, hashlib, html, json, math, os, re, signal, stat, subprocess, sys, threading, time, unicodedata
from pathlib import Path

STATE = Path("ops/mission/state.json")
LEDGER = Path("ops/mission/ledger.jsonl")
ROUTE = {"G0": "S0", "G1": "S1", "G2": "S2", "G3": "S3", "G4": "S2", "G5": "S4", "G6": "S6"}
STAGES = ["S0", "S1", "S2", "S3", "S4", "S5", "S6", "S7"]
GATE_ID_RE = re.compile(r"^(P[0-9]{1,6})-(G[0-6])$")
MAX_GATE_OUTPUT_BYTES = 1024 * 1024
MAX_GATE_TIMEOUT_SECONDS = 300.0
GATE_TERMINATION_GRACE_SECONDS = 2.0

def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

def repo_path_without_symlinks(raw, label, allow_missing_final=False):
    path = Path(raw)
    if path.is_absolute() or ".." in path.parts:
        sys.exit(f"{label} must be a relative path inside the repository")
    candidate = Path()
    for index, part in enumerate(path.parts):
        candidate /= part
        try:
            mode = candidate.lstat().st_mode
        except FileNotFoundError:
            if allow_missing_final and index == len(path.parts) - 1:
                return candidate
            sys.exit(f"{label} does not exist inside the repository")
        if stat.S_ISLNK(mode):
            sys.exit(f"{label} must not have a symlink ancestor")
        if index < len(path.parts) - 1 and not stat.S_ISDIR(mode):
            sys.exit(f"{label} has a non-directory ancestor")
    return candidate

def snapshot_repo_file(raw, label):
    root = Path.cwd().resolve()
    candidate = repo_path_without_symlinks(raw, label)
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

def display_safe(value):
    text = str(value)
    return "".join(
        character
        for character in text
        if character in "\t\n" or unicodedata.category(character) not in {"Cc", "Cf"}
    )

def display_escape(value):
    return html.escape(display_safe(value))

def gate_timeout_seconds():
    raw = os.environ.get("IDC_ARCHIPELAGO_GATE_TIMEOUT_SECONDS")
    if raw is None:
        return MAX_GATE_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        sys.exit("IDC_ARCHIPELAGO_GATE_TIMEOUT_SECONDS must be a number")
    if not math.isfinite(value) or value <= 0 or value > MAX_GATE_TIMEOUT_SECONDS:
        sys.exit(
            "IDC_ARCHIPELAGO_GATE_TIMEOUT_SECONDS must be greater than zero and "
            f"at most {MAX_GATE_TIMEOUT_SECONDS:g}"
        )
    return value

def open_evidence_directory(evdir):
    directory_flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    if os.name == "posix":
        descriptors = []
        try:
            parent = os.open(".", directory_flags)
            descriptors.append(parent)
            for part in ("ops", "mission"):
                parent = os.open(part, directory_flags, dir_fd=parent)
                descriptors.append(parent)
            try:
                evidence_directory = os.open(
                    "evidence", directory_flags, dir_fd=parent
                )
            except FileNotFoundError:
                os.mkdir("evidence", mode=0o700, dir_fd=parent)
                evidence_directory = os.open(
                    "evidence", directory_flags, dir_fd=parent
                )
        except OSError as exc:
            sys.exit(f"evidence directory is not a safe in-repository directory: {exc}")
        finally:
            for descriptor in reversed(descriptors):
                os.close(descriptor)
    else:
        try:
            if evdir.is_symlink():
                raise OSError("evidence path is a symlink")
            evdir.mkdir(mode=0o700, parents=False, exist_ok=True)
            resolved = evdir.resolve(strict=True)
            resolved.relative_to(Path.cwd().resolve())
            if not evdir.is_dir():
                raise OSError("evidence path is not a directory")
            evidence_directory = os.open(evdir, directory_flags)
        except (OSError, ValueError) as exc:
            sys.exit(f"evidence directory is not a safe in-repository directory: {exc}")
    opened = os.fstat(evidence_directory)
    if not stat.S_ISDIR(opened.st_mode):
        os.close(evidence_directory)
        sys.exit("evidence directory is not a directory")
    return evidence_directory, (opened.st_dev, opened.st_ino, opened.st_mode)

def precreate_gate_evidence(evdir, evidence_directory, gate_id):
    file_flags = (
        os.O_RDWR
        | os.O_CREAT
        | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    for attempt in range(16):
        suffix = f"{time.time_ns()}" if attempt == 0 else f"{time.time_ns()}-{attempt}"
        name = f"{gate_id}-{suffix}.txt"
        path = evdir / name
        try:
            if os.name == "posix":
                descriptor = os.open(
                    name, file_flags, 0o600, dir_fd=evidence_directory
                )
            else:
                descriptor = os.open(path, file_flags, 0o600)
            opened = os.fstat(descriptor)
            if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
                os.close(descriptor)
                sys.exit(f"evidence for gate {gate_id} is not a private regular file")
            return path, name, os.fdopen(descriptor, "w+b")
        except FileExistsError:
            continue
        except OSError as exc:
            sys.exit(f"cannot precreate evidence for gate {gate_id}: {exc}")
    sys.exit(f"cannot allocate a unique evidence path for gate {gate_id}")

def hash_gate_evidence(evidence, evdir, evidence_directory, directory_identity, name):
    evidence.flush()
    os.fsync(evidence.fileno())
    before = os.fstat(evidence.fileno())
    file_identity = lambda item: (
        item.st_dev,
        item.st_ino,
        item.st_mode,
        item.st_nlink,
        item.st_size,
        item.st_mtime_ns,
        item.st_ctime_ns,
    )
    try:
        current_directory = os.fstat(evidence_directory)
        visible_directory = evdir.lstat()
        if os.name == "posix":
            named = os.stat(name, dir_fd=evidence_directory, follow_symlinks=False)
        else:
            named = (evdir / name).lstat()
    except OSError as exc:
        sys.exit(f"gate evidence custody changed before hashing: {exc}")
    if (
        (current_directory.st_dev, current_directory.st_ino, current_directory.st_mode)
        != directory_identity
        or (visible_directory.st_dev, visible_directory.st_ino, visible_directory.st_mode)
        != directory_identity
        or not stat.S_ISDIR(visible_directory.st_mode)
        or file_identity(named) != file_identity(before)
        or not stat.S_ISREG(before.st_mode)
        or before.st_nlink != 1
    ):
        sys.exit("gate evidence custody changed before hashing")
    evidence.seek(0)
    digest = hashlib.sha256()
    for block in iter(lambda: evidence.read(128 * 1024), b""):
        digest.update(block)
    after = os.fstat(evidence.fileno())
    if file_identity(before) != file_identity(after):
        sys.exit("gate evidence changed during hashing")
    return digest.hexdigest()

def stream_gate_pipe(pipe, name, evidence, lock, budget, stats):
    try:
        while True:
            chunk = pipe.read(64 * 1024)
            if not chunk:
                break
            with lock:
                stats[name]["seen"] += len(chunk)
                remaining = MAX_GATE_OUTPUT_BYTES - budget["written"]
                if remaining <= 0:
                    continue
                prefix = f"\n--- {name} ---\n".encode("ascii")
                framed = prefix + chunk
                accepted = framed[:remaining]
                evidence.write(accepted)
                evidence.flush()
                budget["written"] += len(accepted)
                stats[name]["kept"] += max(0, len(accepted) - len(prefix))
    except (OSError, ValueError) as exc:
        with lock:
            stats[name]["error"] = display_safe(exc)[:1024]
    finally:
        try:
            pipe.close()
        except OSError:
            pass

def terminate_gate_process(process):
    if process.poll() is not None:
        return True
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGTERM)
        else:
            process.terminate()
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=GATE_TERMINATION_GRACE_SECONDS)
        return True
    except subprocess.TimeoutExpired:
        pass
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (OSError, ProcessLookupError):
        pass
    try:
        process.wait(timeout=GATE_TERMINATION_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        return False
    return True

def execute_gate(command, evidence, timeout_seconds):
    stats = {
        "stdout": {"seen": 0, "kept": 0, "error": ""},
        "stderr": {"seen": 0, "kept": 0, "error": ""},
    }
    budget = {"written": 0}
    lock = threading.Lock()
    popen_options = {}
    if os.name == "posix":
        popen_options["start_new_session"] = True
    elif os.name == "nt":
        popen_options["creationflags"] = getattr(
            subprocess, "CREATE_NEW_PROCESS_GROUP", 0
        )
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            **popen_options,
        )
    except OSError as exc:
        return 127, False, True, stats, display_safe(exc)[:1024]
    threads = [
        threading.Thread(
            target=stream_gate_pipe,
            args=(process.stdout, "stdout", evidence, lock, budget, stats),
            daemon=True,
        ),
        threading.Thread(
            target=stream_gate_pipe,
            args=(process.stderr, "stderr", evidence, lock, budget, stats),
            daemon=True,
        ),
    ]
    for thread in threads:
        thread.start()
    timed_out = False
    terminated = True
    try:
        process.wait(timeout=timeout_seconds)
    except subprocess.TimeoutExpired:
        timed_out = True
        terminated = terminate_gate_process(process)
    for thread in threads:
        thread.join(timeout=GATE_TERMINATION_GRACE_SECONDS)
    for stream, thread in zip((process.stdout, process.stderr), threads):
        if thread.is_alive():
            try:
                stream.close()
            except OSError:
                pass
            thread.join(timeout=GATE_TERMINATION_GRACE_SECONDS)
    returncode = 124 if timed_out else process.returncode
    if returncode is None:
        returncode = 125
    return returncode, timed_out, terminated, stats, ""

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
    for phase in plan.get("phases", []):
        for gate in phase.get("gates", []):
            gate_id = gate.get("id")
            if not isinstance(gate_id, str) or GATE_ID_RE.fullmatch(gate_id) is None:
                sys.exit(f"approved plan.lock contains unsafe gate id: {gate_id!r}")
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
    try:
        state = json.loads(snapshot_repo_file(STATE, "state.json"))
    except json.JSONDecodeError:
        sys.exit("state.json is not valid JSON")
    validate_lock_binding(state)
    return state

def ledger_append(event: dict):
    ledger_path = repo_path_without_symlinks(
        LEDGER, "ledger.jsonl", allow_missing_final=True
    )
    flags = (
        os.O_RDWR
        | os.O_APPEND
        | os.O_CREAT
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        descriptor = os.open(ledger_path, flags, 0o600)
    except OSError as exc:
        sys.exit(f"ledger.jsonl cannot be opened safely: {exc}")
    prev = "0" * 64
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            sys.exit("ledger.jsonl must be a private regular file")
        with os.fdopen(descriptor, "r+", encoding="utf-8", closefd=False) as handle:
            try:
                lines = handle.read().strip().splitlines()
                if lines:
                    prev = json.loads(lines[-1])["entryHash"]
            except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
                sys.exit("ledger.jsonl has an invalid tip entry")
            if os.fstat(descriptor).st_size != opened.st_size:
                sys.exit("ledger.jsonl changed before append")
            body = {"at": now(), "prevHash": prev, **event}
            body["entryHash"] = hashlib.sha256(
                json.dumps(body, sort_keys=True).encode()).hexdigest()
            handle.write(json.dumps(body) + "\n")
            handle.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return body["entryHash"]

def ledger_verify():
    prev = "0" * 64
    ledger_data = snapshot_repo_file(LEDGER, "ledger.jsonl")
    try:
        ledger_text = ledger_data.decode("utf-8")
    except UnicodeDecodeError:
        return False, "ledger is not UTF-8"
    for i, line in enumerate(ledger_text.strip().splitlines(), 1):
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
            f"<tr><td>{display_escape(p['id'])}</td><td>{display_escape(p['title'])}</td><td>{display_escape(p['status'])}</td>"
            f"<td>{sum(1 for g in p['gates'] if g['status']=='passed')}/{len(p['gates'])} gates</td></tr>"
            for p in state["phases"])
        mission_name = display_escape(state["mission"]["name"])
        updated = display_escape(state["mission"]["updated"])
        stage = display_escape(arch.get("loop",{}).get("stage","?"))
        cycle = display_escape(arch.get("loop",{}).get("cycle","?"))
        outp.write_text(
            f"<!doctype html><meta charset='utf-8'><title>SOTU — {mission_name}</title>"
            f"<body style='background:#06070B;color:#E8EDF6;font-family:monospace;padding:40px'>"
            f"<h1 style='color:#00A3FF'>STATE OF THE UNION — {mission_name}</h1>"
            f"<p>updated {updated} · cycle {cycle} · "
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
    evdir = Path("ops/mission/evidence")
    evidence_directory, directory_identity = open_evidence_directory(evdir)
    timeout_seconds = gate_timeout_seconds()
    all_pass = True
    for g in phase["gates"]:
        if g["status"] == "passed":
            continue
        if not isinstance(g.get("id"), str) or GATE_ID_RE.fullmatch(g["id"]) is None:
            sys.exit(f"unsafe gate id: {g.get('id')!r}")
        print(f"gate {g['id']}: {g['command']}")
        evp, evidence_name, evidence = precreate_gate_evidence(
            evdir, evidence_directory, g["id"]
        )
        with evidence:
            header = (
                f"$ {g['command']}\n"
                f"startedAt {now()}\n"
                f"timeoutSeconds {timeout_seconds:g}\n"
                f"outputLimitBytes {MAX_GATE_OUTPUT_BYTES}\n"
            ).encode("utf-8", errors="backslashreplace")
            evidence.write(header)
            evidence.flush()
            os.fsync(evidence.fileno())
            start_hash = ledger_append({
                "event": "gate-start",
                "gate": g["id"],
                "status": "started",
                "command": g["command"],
                "evidence": str(evp),
                "timeoutSeconds": timeout_seconds,
                "outputLimitBytes": MAX_GATE_OUTPUT_BYTES,
            })
            returncode, timed_out, terminated, stream_stats, launch_error = execute_gate(
                g["command"], evidence, timeout_seconds
            )
            seen = sum(item["seen"] for item in stream_stats.values())
            kept = sum(item["kept"] for item in stream_stats.values())
            truncated = seen > kept
            footer = (
                f"\n--- completion ---\n"
                f"exit {returncode}\n"
                f"timedOut {str(timed_out).lower()}\n"
                f"terminated {str(terminated).lower()}\n"
                f"outputBytesSeen {seen}\n"
                f"outputBytesKept {kept}\n"
                f"truncated {str(truncated).lower()}\n"
            )
            if launch_error:
                footer += f"launchError {launch_error}\n"
            for stream_name, item in stream_stats.items():
                if item["error"]:
                    footer += f"{stream_name}ReadError {item['error']}\n"
            evidence.write(footer.encode("utf-8", errors="backslashreplace"))
            evidence.flush()
            os.fsync(evidence.fileno())
            sha = hash_gate_evidence(
                evidence,
                evdir,
                evidence_directory,
                directory_identity,
                evidence_name,
            )
        g["evidence"] = str(evp); g["lastRun"] = now()
        g["status"] = "passed" if returncode == 0 else "failed"
        if g["status"] == "passed":
            for loopback in s["archipelago"]["loop"].get("loopbacks", []):
                if loopback.get("gate") == g["id"] and not loopback.get("resolvedAt"):
                    loopback["resolvedAt"] = now()
        ledger_append({"event": "gate-run", "gate": g["id"], "status": g["status"],
                       "command": g["command"], "evidence": str(evp), "evidenceSha256": sha,
                       "startedEntryHash": start_hash, "returncode": returncode,
                       "timedOut": timed_out, "terminated": terminated,
                       "outputBytesSeen": seen, "outputBytesKept": kept,
                       "outputTruncated": truncated})
        print(f"   -> {g['status']} (evidence {evp.name}, sha {sha[:12]}…)")
        if g["status"] == "failed":
            all_pass = False
    os.close(evidence_directory)
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
    match = GATE_ID_RE.fullmatch(args.gate)
    if match is None:
        sys.exit(f"unsafe gate id: {args.gate}")
    gate_family = match.group(2)
    to_stage = args.route or ROUTE.get(gate_family, "S2")
    current_stage = s["archipelago"]["loop"].get("stage")
    if current_stage not in STAGES:
        sys.exit(f"mission loop has invalid current stage: {current_stage!r}")
    if to_stage not in STAGES:
        sys.exit(f"invalid loopback stage: {to_stage!r}")
    if STAGES.index(to_stage) > STAGES.index(current_stage):
        sys.exit(f"failed gate cannot move forward ({current_stage} -> {to_stage})")
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
    f = sub.add_parser("fail"); f.add_argument("gate"); f.add_argument("--reason", required=True); f.add_argument("--route", choices=STAGES)
    a = sub.add_parser("advance"); a.add_argument("stage", choices=STAGES)
    c = sub.add_parser("close-phase"); c.add_argument("phase")
    sub.add_parser("verify-ledger")
    args = ap.parse_args()
    {"status": cmd_status, "run-gates": cmd_run_gates, "fail": cmd_fail,
     "advance": cmd_advance, "close-phase": cmd_close_phase,
     "verify-ledger": cmd_verify_ledger}[args.cmd](args)

if __name__ == "__main__":
    main()
