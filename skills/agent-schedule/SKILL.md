---
name: agent-schedule
description: Schedule an unattended agent on a recurring wall-clock — cron, systemd timer, heartbeat, or while-sleep external clocks vs a runtime's own built-in scheduler — then verify the schedule actually fired before trusting it. Use when an agent must run every N minutes or hourly, "run on a schedule", "cron job", "heartbeat", "recurring agent", "run unattended", or "run every hour". Differentiator - the only island triggered by wall-clock time; the siblings all loop on a condition (a bar, a gate, a goal), and a created-but-unseen schedule stays unverified here until fire evidence proves it.
---

# Agent Schedule: recurring wall-clock, verified fire

Put an unattended agent on a **clock** so it runs by itself on a recurring interval. This is the one wall-clock island: `archipelago`, `gauntlet-loop`, and the `spec-pipeline` goal loop all iterate until a *condition* clears: a bar, a gate, a goal. Here the trigger is **time**, and the discipline is proving the schedule fired.

First question: does the agent runtime ship a **built-in scheduler** (rare → Camp B), or do you **own the clock** (most runtimes → Camp A)?

Universal floor: cron granularity is **1 minute** (5-field expression, no seconds) on every runtime. For sub-minute cadence use a `while …; sleep N; done` loop or an event hook, never cron. Never put an LLM on a tight timer: cost and rate limits punish it.

## Camp A: you own the clock (the common case)

The agent runs once and exits (amnesiac unless resumed). Invoke it non-interactively, then wrap that in an external clock. Flag names vary by runtime; the *shapes* are what matter:

```bash
# one-shot: pre-approve tools + machine-readable output, or an unattended run hangs on a prompt
agent -p "check X and report" --auto-approve --output json >> ~/agent.log 2>&1
```

```bash
# 1. cron — 1-minute floor, survives nothing on its own
*/10 * * * * cd /path/to/project && agent -p "check X" --auto-approve --output json >> ~/agent.log 2>&1
# 2. systemd timer (Linux) — survives reboot, real logging:  OnUnitActiveSec=10min
# 3. while-sleep — sub-minute cadence, or no cron/systemd available
while true; do agent -p "check X" --auto-approve; sleep 30; done
```

Three gotchas, each of which silently breaks an unattended run:
- **A permission prompt breaks the run; how depends on the tty.** With a controlling tty the prompt blocks forever waiting on input no one is there to give; with no controlling tty the runtime's `read()` hits EOF and the run exits early instead. Either way it never does the work: pass the non-interactive / auto-approve / allowed-tools flag or run fully non-interactively.
- **Emit machine-readable output** (JSON) so the wrapper parses results deterministically instead of scraping prose.
- **Runs are amnesiac.** Persist state to a file the next run reads (or use the runtime's resume), or every tick starts from zero.

## Camp B: a built-in scheduler

Some runtimes tick internally and run due jobs in fresh isolated sessions. Prefer it when present: it survives reboot, logs its own runs, and needs no external clock. State-check that the scheduler daemon is installed and running, create the job in the runtime's own cron/interval syntax, and remember **each run is a fresh session**: the prompt must carry all its own context. Loop safety: never schedule a new job from inside a scheduled run.

## Heartbeat pattern

One fast recurring tick gates many slower per-task checks: the tick reads a task list plus a per-task `last_run` timestamp and acts only on tasks that are **due**. Define active hours, and stay **silent when nothing is due**, with no empty noise. A watchdog tick is just a cheap command whose output is delivered as-is; keep it to one unauthenticated call and alert only on a non-ok result.

## Verify it fired: the evidence gate

A schedule you *created* is `unverified` until you have **watched it fire**. Never report "scheduled" as "running": the registration succeeding is not the run succeeding.

```bash
agent -p "check X" --auto-approve --output json; echo "exit=$?"   # run the wrapped command by hand: clean JSON, exit 0
```

- **Camp A:** confirm the log file grows after one full interval; confirm the non-interactive flag is actually present (the #1 silent failure is a hung permission prompt).
- **Camp B:** list scheduled jobs, confirm the job exists with a sane `next_run`, then trigger a run-now and confirm the output is delivered.
- **Heartbeat:** confirm a nothing-due tick stays silent, not just that a due one fires.

State each check `enforced` vs `advisory` and never imply it: the OS firing cron at the interval is *enforced* by the OS; "the agent did the useful work" is *advisory* unless the run writes a captured artifact a later check can recompute. A green cron log proves invocation, not outcome.

**No authority without evidence. A schedule is unverified until you have watched it fire.**
