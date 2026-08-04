---
name: research
description: Investigate a question against high-trust primary sources and capture the findings as a cited Markdown file — every claim sourced or explicitly flagged unverified. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated. Differentiator - primary-source discipline with a hard sourced-or-flagged rule; DeepAPI is an optional backend, not a requirement.
---

# Research — sourced or flagged

The discipline is one rule: **every claim is either backed by a primary source or explicitly flagged as unverified.** No third category. A confident sentence with no source is the exact defect this island exists to prevent — an unverified claim laundered into a fact caps trust, and a report that mixes the two is worse than no report.

Follow the primary-source law: investigate against **official docs, source code, specs, first-party APIs** — not a secondary write-up of them. Follow every claim back to the source that owns it. Separate fact from inference — say which is which.

## The default path — delegate and keep working

Spin up a **background agent** to do the reading so you keep working while it reads:

1. Investigate the question against primary sources. Follow each claim to the source that owns it.
2. Write findings to a single Markdown file, **citing each claim's source** inline. Any claim you couldn't source gets marked `[UNVERIFIED]` in place — never dropped, never smoothed over.
3. Save it where the repo keeps such notes; match the existing convention, and if there's none, put it somewhere sensible and say where.

## Building the research prompt

One self-contained paragraph does the work:

- Lead with the **single question** + the decision or end-use it informs.
- Embed all context — no back-and-forth needed.
- Number **3–6 inline sub-questions**. One mission per prompt.
- State include/avoid constraints; prefer primary sources; separate fact from inference.

## Optional backend — DeepAPI

For deep source-backed runs, DeepAPI (`deepapi.co`) is an available backend — not a requirement; the discipline above stands whatever tool does the reading. If used:

```bash
[ -n "$DEEPAPI_API_KEY" ] || . ~/.deepapi/env      # do NOT `source ~/.zshrc` (breaks the shell, exit 126)
KEY=$DEEPAPI_API_KEY; BASE=${DEEPAPI_API_BASE_URL:-https://deepapi.co}
IDK=$(uuidgen)                                      # retries must reuse the SAME Idempotency-Key
jq -n --rawfile p /tmp/dr_prompt.txt '{query:$p, maxCostUsd:"0.20"}' > /tmp/dr_body.json
curl -s --max-time 120 "$BASE/v1/research/deep" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -H "Idempotency-Key: $IDK" -d @/tmp/dr_body.json > /tmp/dr_result.json
jq -r '.status, .output.answer' /tmp/dr_result.json
jq -r '.output.sources[]?.url'  /tmp/dr_result.json
```

One call caps at ~700 words; for a bigger topic, fire one call per numbered sub-question (each its own Idempotency-Key) and synthesize. Key missing → stop and ask; never print or log it. `402 insufficient_credits` → stop, user tops up, retry with the same key (replays don't double-charge). If `sources` is empty while the answer shows `[n]` markers, deliver the report but tell the user the citations didn't come back.

## Completion

**Done when** every claim in the saved file is either followed by its primary source or marked `[UNVERIFIED]`, and the file lists its citation URLs. Report the file path; report cost only if asked.

**No authority without evidence. Sourced or flagged — there is no third state.**
