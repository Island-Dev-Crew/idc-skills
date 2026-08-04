---
name: diagnose
description: A disciplined loop for hard bugs and performance regressions — build a tight red-capable feedback loop first, reproduce and minimise, hypothesise, instrument, fix with a regression test, then post-mortem. Use when the user says "diagnose", "debug this", or reports something broken, throwing, failing, or slow. Differentiator - the feedback loop comes before any theory, and performance is judged by operation counts, not wall-clock.
---

# Diagnose — the loop before the theory

A discipline for hard bugs. The whole skill is Phase 1; everything after is mechanical. **If you catch yourself reading code to build a theory before a red-capable loop exists, stop — jumping to a hypothesis is the exact failure this prevents.** Skip a phase only with explicit justification. Read `CONTEXT.md` (if present) for the mental model, and check ADRs in the area you touch.

Two leading words: a **tight** loop (fast, deterministic, sharp) and a loop that goes **red** on *this* bug (not merely "runs without erroring").

## Phase 1 — Build a feedback loop (this is the skill)

Get a pass/fail signal that goes **red on this exact bug** and green once it's fixed. With one, bisection and hypothesis-testing just consume it; without one, no amount of staring at code will save you. **Be aggressive, be creative, refuse to give up.** Try these in roughly this order:

1. **Failing test** at whatever seam reaches the bug.
2. **Curl / HTTP script** against a running dev server.
3. **CLI invocation** with a fixture, diffing stdout against a known-good snapshot.
4. **Headless browser script** (Playwright/Puppeteer) — asserts on DOM/console/network.
5. **Replay a captured trace** — save a real request/payload/event log, replay it through the path in isolation.
6. **Throwaway harness** — minimal subset of the system exercising the bug path in one call.
7. **Property / fuzz loop** — for "sometimes wrong", run 1000 random inputs.
8. **Bisection harness** — automate "boot at state X, check, repeat" for `git bisect run`.
9. **Differential loop** — same input through old vs new (or two configs), diff outputs.
10. **HITL bash script** — last resort; if a human must click, drive them so the loop stays structured.

**Tighten the loop** — treat it as a product: faster (cache setup, narrow scope), sharper (assert the specific symptom, not "didn't crash"), more deterministic (pin time, seed RNG, isolate FS, freeze network). A 2-second deterministic loop is a superpower; a 30-second flaky one is barely a loop. For non-deterministic bugs the goal isn't a clean repro but a **higher reproduction rate** — loop 100×, parallelise, add stress, narrow timing until it's debuggable.

**Completion criterion:** name **one command** you have **already run at least once** (paste the invocation and its output) that is red-capable (drives the real bug path, asserts the user's *exact* symptom), deterministic, fast, and agent-runnable. No such command, no Phase 2.

## Phase 2 — Reproduce + minimise

Run the loop; watch it go red. Confirm it produces the failure mode the **user** described (not a nearby one — wrong bug, wrong fix), reproducibly. Then **minimise**: shrink to the smallest scenario that still goes red, cutting inputs/callers/config/data **one at a time**, re-running after each cut. Done when every remaining element is load-bearing — removing any one makes it green. Don't proceed until reproduced *and* minimised.

## Phase 3 — Hypothesise

Generate **3–5 ranked, falsifiable hypotheses before testing any** (single-hypothesis generation anchors on the first plausible idea). Each states its prediction: *"If X is the cause, then changing Y makes the bug disappear."* No prediction = a vibe; discard or sharpen it. Show the ranked list to the user before testing — domain knowledge re-ranks instantly ("we just deployed #3") — but don't block if they're AFK.

## Phase 4 — Instrument

Each probe maps to a specific prediction. **Change one variable at a time.** Prefer a debugger/REPL (one breakpoint beats ten logs), then targeted logs at the boundaries that distinguish hypotheses — never "log everything and grep." Tag every debug log with a unique prefix (`[DEBUG-a4f2]`) so cleanup is one grep.

**Performance branch — operation counts, not wall-clock.** For a regression, logs and stopwatches lie: wall-clock is noisy across machines and loads. Measure the thing that's deterministic — **operation counts** (queries issued, allocations, callgrind instruction counts, bytes scanned) — establish a baseline, then bisect. A regression proven by "it got slower on my machine" is a claim; one proven by "N queries became N×M queries" is a finding. Measure first, fix second.

## Phase 5 — Fix + regression test

Write the regression test **before the fix** — but only if a **correct seam** exists (one exercising the real bug pattern as it occurs at the call site). A too-shallow seam gives false confidence; **if no correct seam exists, that itself is the finding** — note it; the architecture is preventing the bug from being locked down. With a correct seam: turn the minimised repro into a failing test, watch it fail, apply the fix, watch it pass, then re-run the Phase 1 loop against the original un-minimised scenario.

## Phase 6 — Cleanup + post-mortem

- [ ] Original repro no longer reproduces (re-run the loop)
- [ ] Regression test passes (or the absence of a seam is documented)
- [ ] All `[DEBUG-...]` instrumentation removed (grep the prefix); throwaway harnesses deleted
- [ ] The hypothesis that proved correct is stated in the commit/PR — so the next debugger learns

**Then ask: what would have prevented this?** If the answer is architectural (no good seam, tangled callers, hidden coupling), hand the specifics to the `deep-modules` island — *after* the fix is in, when you know more than you did at the start. Findings worth keeping become `finding-register` entries; the loop command is the entry's recomputable `command`.

**No authority without evidence. The loop that goes red is the evidence; the theory is not.**
