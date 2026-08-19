---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a cited Markdown file — every claim sourced or explicitly flagged unverified. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated. Differentiator - primary-source discipline with a hard sourced-or-flagged rule; DeepAPI is an optional backend, not a requirement.
---

# Research: sourced or flagged

The discipline is one rule: **every claim is either backed by a primary source or explicitly flagged as unverified.** No third category. A confident sentence with no source is the exact defect this island exists to prevent: an unverified claim laundered into a fact caps trust, and a report that mixes the two is worse than no report.

Follow the primary-source law: investigate against **official docs, source code, specs, first-party APIs**, not a secondary write-up of them. Follow every claim back to the source that owns it. Separate fact from inference; say which is which. A primary source you found but couldn't open (paywall, fetch-size limit, tool failure) is still unread: the claim stays `[UNVERIFIED]`, annotated with the URL and the retrieval failure. Secondary sources describing what it says never upgrade it.

Boundary: the bare word "research" is wide, so route the specialist cases to their island. A bug investigation is [`diagnose`](../diagnose/SKILL.md) (build a red-capable loop, don't write a report); domain setup is [`domain-wire`](../domain-wire/SKILL.md); multi-session learning with source-gathering is [`teach`](../teach/SKILL.md), which is **user-invoked**, so you cannot start it yourself; tell the human to invoke it. This island is for investigating a question or topic against external docs, APIs, or specs and producing one cited file. A single request can span islands, so split it: route the diagnostic half to `diagnose` explicitly (name the handoff in your output), research only the part answerable from external sources. Cited generic documentation about what an error means is not a diagnosis of why *your* system just failed.

## The default path: delegate and keep working

If the harness offers a background research-delegation tool, spin one up to do the reading so you keep working while it reads. If it doesn't, do the reading yourself, synchronously. Delegation is a throughput optimization, not the requirement; the numbered discipline below applies either way:

1. Investigate the question against primary sources. Follow each claim to the source that owns it.
2. Write findings to a single Markdown file, **citing each claim's source** inline. Any claim you couldn't source gets marked `[UNVERIFIED]` in place, never dropped, never smoothed over.
3. Save it where the repo keeps such notes; match the existing convention, and if there's none, put it somewhere sensible and say where.

## Building the research prompt

One self-contained paragraph does the work:

- Lead with the **single question** + the decision or end-use it informs.
- Embed all context; no back-and-forth needed.
- Number **3 to 6 inline sub-questions**. One mission per prompt.
- State include/avoid constraints; prefer primary sources; separate fact from inference.

## Optional backend: DeepAPI

For deep source-backed runs, DeepAPI (`deepapi.co`) is an available backend, not a requirement; the discipline above stands whatever tool does the reading. It is paid external egress: a cost cap is not spend authorization, so obtain explicit operator approval (or a pre-authorized enforced budget) before calling it. Keep the endpoint fixed; do not source a shell profile or honor an environment-overridden base URL, either of which can turn research into arbitrary code execution or credential exfiltration. Retrieve the credential from the approved password manager into process memory only, never an env file, shell history, repository file, or chat. If used with 1Password CLI, adapt the item reference without exposing the value:

```bash
umask 077
command -v op >/dev/null || { echo "password-manager CLI unavailable" >&2; exit 1; }
KEY="$(op read 'op://Private/DeepAPI/credential')" || exit 1
[ -n "$KEY" ] || { echo "DeepAPI credential unavailable" >&2; exit 1; }
TMP="$(mktemp -d "${TMPDIR:-/tmp}/deepapi-research.XXXXXXXX")"
trap 'unset KEY; rm -rf "$TMP"' EXIT
IDK=$(uuidgen)                                      # retries must reuse the SAME Idempotency-Key
jq -n --rawfile p "$TMP/prompt.txt" '{query:$p, maxCostUsd:"0.20"}' > "$TMP/body.json"
curl --fail-with-body --silent --show-error --max-time 120 "https://deepapi.co/v1/research/deep" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDK" -d @"$TMP/body.json" > "$TMP/result.json"
unset KEY
jq -r '.status, .output.answer' "$TMP/result.json"
jq -r '.output.sources[]?.url'  "$TMP/result.json"
```

Create `"$TMP/prompt.txt"` with the approved research prompt before the call. One call caps at ~700 words; for a bigger topic, use only the approved number of calls, one per numbered sub-question (each its own Idempotency-Key), and synthesize. Key missing → stop and ask the user to save it in the password manager; never ask them to paste it into chat and never print or log it. `402 insufficient_credits` → stop; any top-up or additional spend belongs to the operator. If `sources` is empty while the answer shows `[n]` markers, deliver the report but tell the user the citations didn't come back.

## Completion

**Done when** every claim in the saved file is either followed by its primary source or marked `[UNVERIFIED]`, and the file lists its citation URLs. Report the file path; report cost only if asked.

**No authority without evidence. Sourced or flagged: there is no third state.**
