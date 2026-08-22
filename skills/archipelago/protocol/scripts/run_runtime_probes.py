#!/usr/bin/env python3
"""ARCHIPELAGO P2 — runtime evidence probe runner (dogfood-readiness v2, Lanes B/C/D).

Wraps Playwright, runs declared journeys, and normalizes artifacts into the
evidence-bundle lane shape (schemas/evidence-bundle.schema.json).

Usage:
  python3 scripts/run_runtime_probes.py --journeys ops/probes/journeys.json --out ops/mission/evidence/runtime
  python3 scripts/run_runtime_probes.py --self-test --out ops/mission/evidence/runtime

Journey file shape:
  [{"id": "j1", "url": "https://... or file://...", "steps": [
      {"action": "goto"} | {"action": "click", "selector": "..."} |
      {"action": "fill", "selector": "...", "value": "..."} |
      {"action": "expect_visible", "selector": "..."} |
      {"action": "expect_text", "selector": "...", "text": "..."}]}]

Honesty rules (enforced, not advisory):
  - Any console error during a journey => automatic finding.
  - If Playwright/Chromium is unavailable, lanes are reported as
    "skipped-environment" with a finding — NEVER silently passed.
  - Each journey runs RUNS times (default 3); disagreement => quarantined finding
    (resilience lane), not a pass.
  - trace.zip / screenshots prove the app worked in THIS run on THIS machine. No more.
"""
import argparse, hashlib, json, sys, time
from pathlib import Path

RUNS = 3

def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()

def artifact(aid: str, path: Path, kind: str) -> dict:
    return {"id": aid, "path": str(path), "sha256": sha256(path), "kind": kind}

def playwright_available():
    try:
        from playwright.sync_api import sync_playwright  # noqa
        return True
    except Exception:
        return False

def run_journey(pw, journey: dict, outdir: Path, run_idx: int):
    """Returns (passed: bool, console_errors: list, shots: [Path], trace: Path|None)."""
    from playwright.sync_api import expect
    browser = pw.chromium.launch()
    ctx = browser.new_context(record_video_dir=str(outdir / "video"))
    ctx.tracing.start(screenshots=True, snapshots=True)
    page = ctx.new_page()
    console_errors = []
    page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: console_errors.append(str(e)))
    shots, passed, err = [], True, None
    try:
        for i, step in enumerate(journey["steps"]):
            a = step["action"]
            if a == "goto":
                page.goto(journey["url"], wait_until="load")
            elif a == "click":
                page.click(step["selector"], timeout=8000)
            elif a == "fill":
                page.fill(step["selector"], step["value"], timeout=8000)
            elif a == "expect_visible":
                expect(page.locator(step["selector"])).to_be_visible(timeout=8000)
            elif a == "expect_text":
                expect(page.locator(step["selector"])).to_contain_text(step["text"], timeout=8000)
            else:
                raise ValueError(f"unknown action {a}")
            shot = outdir / f"{journey['id']}-r{run_idx}-s{i}.png"
            page.screenshot(path=str(shot), full_page=True)
            shots.append(shot)
    except Exception as e:
        passed, err = False, str(e)[:300]
    trace = outdir / f"{journey['id']}-r{run_idx}-trace.zip"
    ctx.tracing.stop(path=str(trace))
    ctx.close(); browser.close()
    if err:
        console_errors.append(f"journey-exception: {err}")
    return passed, console_errors, shots, trace

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--journeys")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--out", default="ops/mission/evidence/runtime")
    ap.add_argument("--runs", type=int, default=RUNS)
    args = ap.parse_args()
    outdir = Path(args.out); outdir.mkdir(parents=True, exist_ok=True)

    if args.self_test:
        # Real journey against a local page — no network, still a genuine browser run.
        test_page = outdir / "selftest.html"
        test_page.write_text("""<!doctype html><html><body>
          <h1 id="title">ARCHIPELAGO probe target</h1>
          <button id="go" onclick="document.getElementById('msg').textContent='crossed'">cross gate</button>
          <p id="msg"></p></body></html>""")
        journeys = [{"id": "selftest", "url": test_page.resolve().as_uri(), "steps": [
            {"action": "goto"},
            {"action": "expect_visible", "selector": "#title"},
            {"action": "click", "selector": "#go"},
            {"action": "expect_text", "selector": "#msg", "text": "crossed"},
        ]}]
    else:
        journeys = json.loads(Path(args.journeys).read_text())

    lanes = {"runtime-journey": {"artifacts": [], "findings": []},
             "visual": {"artifacts": [], "findings": []},
             "recording": {"artifacts": [], "findings": []},
             "resilience": {"artifacts": [], "findings": []}}
    env_ok = playwright_available()
    if not env_ok:
        msg = "skipped-environment: playwright/chromium unavailable — runtime lanes NOT satisfied"
        for l in lanes.values():
            l["findings"].append(msg)
        result = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "environment": "unavailable", "lanes": lanes, "journeys": []}
        (outdir / "runtime-lanes.json").write_text(json.dumps(result, indent=2))
        print("[SKIP] runtime lanes: environment unavailable (finding recorded, not a pass)")
        sys.exit(2)

    from playwright.sync_api import sync_playwright
    summary = []
    with sync_playwright() as pw:
        for j in journeys:
            outcomes = []
            for r in range(1, args.runs + 1):
                passed, cerrs, shots, trace = run_journey(pw, j, outdir, r)
                outcomes.append(passed)
                if r == 1:  # hash run-1 artifacts as the canonical set
                    jr = outdir / f"{j['id']}-journey.json"
                    jr.write_text(json.dumps({"journey": j, "passed": passed,
                                              "consoleErrors": cerrs}, indent=2))
                    lanes["runtime-journey"]["artifacts"].append(artifact(f"{j['id']}-journey", jr, "journey-json"))
                    for s in shots:
                        lanes["visual"]["artifacts"].append(artifact(s.stem, s, "screenshot"))
                    lanes["recording"]["artifacts"].append(artifact(f"{j['id']}-trace", trace, "trace-zip"))
                for c in cerrs:
                    lanes["runtime-journey"]["findings"].append(f"{j['id']} r{r}: console error: {c}")
            if len(set(outcomes)) > 1:
                lanes["resilience"]["findings"].append(
                    f"{j['id']}: FLAKE quarantine — outcomes across {args.runs} runs: {outcomes}")
            summary.append({"id": j["id"], "outcomes": outcomes,
                            "stable_pass": all(outcomes)})
    result = {"generatedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "environment": "chromium", "runsPerJourney": args.runs,
              "journeys": summary, "lanes": lanes}
    out = outdir / "runtime-lanes.json"
    out.write_text(json.dumps(result, indent=2))
    ok = all(j["stable_pass"] for j in summary) and not lanes["runtime-journey"]["findings"]
    print(f"[{'PASS' if ok else 'FAIL'}] {len(summary)} journey(s) x{args.runs} runs -> {out}")
    for j in summary:
        print(f"   - {j['id']}: {j['outcomes']}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
