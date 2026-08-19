---
name: exposure-audit
description: Read-only exposure audit of any target machine or repo against a NAMED advisory - a CVE, breach, malicious package, or supply-chain alert - enumerating what is actually installed and reachable, deciding affected-or-not on captured evidence, and writing a structured report. Use when someone shares an advisory and asks "am I affected", "scan my system for X", "does this breach touch us", "are we exposed to this package", or requests a vulnerability or supply-chain exposure audit of a machine or repo. Differentiator - the verdict is decided by enumeration output that could have gone either way, never a claim; strictly read-only, never remediates (contrast agent-guardrails, which blocks commands, and diagnose, which chases a live bug).
---

# Exposure Audit: verdict on evidence, never on a claim

One concern: against a **named** advisory, enumerate what the target actually has installed and exposed, decide **affected-or-not on captured output**, and write a structured report. It never remediates; that authority belongs to a human. An *Affected* verdict is a check that could have said *Not affected* and didn't. Parameterize both paths, nothing hardcoded to a machine: `TARGET` (machine root or repo path, default the current repo / `$HOME`) and `REPORT_DIR` (default `$TARGET/security-audits/`).

## Hard rules: read-only, `enforced` only where a guard exists

- **Read-only.** No installs, removes, upgrades, restarts, outbound network calls, or writes outside `REPORT_DIR`. This is **advisory** here, the skill's own discipline, not a hook. To make it `enforced` at the machine level, install [`agent-guardrails`](../agent-guardrails/SKILL.md) (its shell denylist is the mechanical floor beneath this prompt).
- **No `sudo`.** Never.
- **A state-changing check is not run**: record it as `not checked (would change state)`. It never becomes evidence, and it never collapses into *Not affected*.
- **One report per invocation**, always written, even a *Not affected* verdict, because the audit trail is the deliverable.

## Workflow

1. **Scope the advisory.** Extract the package/binary name, affected version range, platform, and attack vector (supply-chain / RCE / local / network). No named subject → ask for one; this island audits against a name, not a vibe.
2. **Enumerate in parallel.** Pick the relevant checks below (one ecosystem, not all), run them in one batch of Bash calls against `TARGET`.
3. **Build the evidence table as you go.** Each row is one check plus its **concrete captured result**: a version string, a path, `None`, `N/A`. A row with no output backing it is not a row.
4. **Decide on the evidence.** Map captured results to the verdict wording below. The presence of a vulnerable version is not enough; it must also be *reachable* by the vector.
5. **Write the report** to `REPORT_DIR/YYYY-MM-DD-<kebab-slug>.md` (today's date from the environment). One-line verdict back to the user plus the path.

## Check menu (pick what the advisory needs; `<pkg>` = the named subject)

```bash
# --- Node / npm (supply-chain) ---
command -v npm pnpm yarn; npm ls -g --depth=0 2>/dev/null | grep -i "<pkg>"
find "$TARGET" -maxdepth 8 \( -name package-lock.json -o -name pnpm-lock.yaml -o -name yarn.lock \) 2>/dev/null \
  | xargs grep -l "<pkg>" 2>/dev/null                      # direct + transitive
# --- Python ---
command -v python3 pip pipx uv; pip list 2>/dev/null | grep -i "<pkg>"
find "$TARGET" -maxdepth 6 \( -name "requirements*.txt" -o -name pyproject.toml -o -name uv.lock -o -name poetry.lock \) 2>/dev/null | xargs grep -l "<pkg>" 2>/dev/null
# --- System binary / package manager (brew | apt | dnf | pacman — pick the platform's) ---
command -v "<binary>" && "<binary>" --version 2>/dev/null
brew list --versions "<formula>" 2>/dev/null || dpkg -l "<pkg>" 2>/dev/null || rpm -q "<pkg>" 2>/dev/null
# --- Running / listening (RCE + network CVEs) ---
pgrep -lf "<binary>"; lsof -iTCP -sTCP:LISTEN -P -n 2>/dev/null | grep "<port>"
# --- Autostart / persistence (systemd units, cron, launch agents) ---
systemctl list-units --type=service 2>/dev/null | grep -i "<vendor>"; crontab -l 2>/dev/null | grep -i "<vendor>"
```

For any ecosystem not shown (cargo, Go modules, gems, Docker images), apply the same shape: **global install path + manifest grep + running process**.

## Verdict wording, and the line you never cross

- **Not affected.** Subject absent, or present but patched past the range, or present but unreachable by the vector. Cite the output that proves it.
- **Affected.** A vulnerable version is present **and** reachable by the attack vector. Both halves need a captured row.
- **Partially affected.** Present but mitigated (installed yet not running; listener bound to loopback only). Spell out the mitigation.

`not checked` is not `Not affected`. Reporting an unrun check as clear is laundering `unverified` into `verified`, the one move the discipline forbids. If the verdict is *Affected*, the remediation command goes in **Follow-ups** and stops there; the human runs it.

## Report template

```markdown
# <Subject> — Exposure Audit
**Date:** YYYY-MM-DD  **Target:** <TARGET>

## Advisory in scope
- **<ID / source> "<name>"** — <one-line description>. <affected range>.

## Audit results
| Check | Captured result |
|---|---|
| <check> | <version / path / None / not checked (would change state)> |

## Verdict
**<Not affected. | Affected. | Partially affected.>**
- <rationale bound to a row above>

## Action taken
None — read-only, no files modified outside REPORT_DIR.

## Follow-ups
- <remediation for the human to run, or "None">
```

**No authority without evidence. An *Affected* verdict is a check that could have said otherwise. A claim is not an audit.**
