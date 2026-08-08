---
name: data-source-map
description: Wire an external data source into a workspace with a markdown descriptor — describe where a SQL / BigQuery / Drive / Oracle store lives, what it holds, and what to ask it, so an agent queries it on demand instead of ingesting it into a vector store. Use when connecting a database or data service to an ICM workspace, or when the user mentions "OKF", "open knowledge format", "connect a database", "data source", "big query", or "describe my data for the AI". Differentiator - the external-data leaf of folder-workspace; the descriptor is a map to live data, not a copy of it.
---

# Data Source Map — describe the data, don't ingest it

The external-data leaf of the ICM cluster. [`folder-workspace`](../folder-workspace/SKILL.md) routes an agent through *files*; this island routes it to *live external data* — a SQL database, BigQuery, an Oracle warehouse, a Google Drive, a SharePoint. It fuses Jake Van Clief's **OKF (Open Knowledge Format)** move — describe a data source in a small markdown + YAML descriptor so the agent fetches from it on demand — with the forge's discipline: the descriptor is a *map to* the data, and a map is a claim the source must still satisfy.

The insight both OKF and RAG chase is the same — get the right data into the model's context as it generates. RAG answers it with a vector store you must build and sync. OKF answers it with a **description**: tell the agent where the data is, what it holds, and how to ask, and let the model's own weights navigate it. For most workspaces the description is enough, and it never goes stale the way an embedding index does.

## The descriptor

A data source is a leaf in the workspace, reached from the map's routing table like any room. Its `CONTEXT.md` is a descriptor, not a dump:

```markdown
# Data source: <name>
Kind: postgres | bigquery | oracle | sqlite | google-sheet | drive | sharepoint
Reach: <connection detail, or a pointer to where the credential lives — never the secret itself>
Holds: <what's in here, in the operator's own words — "orders, customers, refunds since 2019">
Ask it: <the query path, or for file-store kinds the folder + naming convention — "orders live in public.orders; join customers on customer_id" or "current MSAs live in Contracts/, one PDF per customer, named MSA_<customer>_<year>">
Freshness: <how current — live / nightly / a snapshot as of <date>>
Do not: <what's out of bounds — write access, PII columns, tables to leave alone>
```

The **Ask it** line is the whole point — it is the *request slip* in the library analogy: it saves the agent from ripping the schema apart to find where orders are. For a big warehouse you don't describe every table; you describe *where to look*, so a 10,000-table Oracle store becomes navigable from a paragraph.

## Wire it in

1. **Describe, don't ingest.** Write the descriptor from what the operator knows about their own data (they know it better than any crawler). Do not copy the data into markdown — point at it.
2. **Reach on demand.** The agent reads the descriptor only when the routing table sends it there, then queries the live source through the harness's own connector (a database MCP, a Drive integration) — no bespoke pipeline unless one is genuinely needed (ask [`job-to-be-done`](../job-to-be-done/SKILL.md) before building one).
3. **Guard the reach.** Agents connect **read-only** by default. For SQL/BigQuery/Oracle kinds, pair this with `agent-guardrails` layer 4 (a read-only DB role); for drive/sharepoint/google-sheet kinds, use a read-only OAuth scope or viewer-only share link instead. Where no such enforced scope exists, the `Do not` line is advisory only — say so in the descriptor. The credential is referenced, never written into the descriptor.

## The evidence weld

- **Enforced-vs-advisory:** the descriptor is **advisory** — nothing forces the live source to match what "Holds" and "Ask it" claim. The enforced check is a query that runs: for file-path kinds (drive, sharepoint, local), point [`workspace-audit`](../workspace-audit/SKILL.md) at the descriptor to confirm the named paths still exist, and list the folder to flag any file breaking a claimed naming convention. For SQL/BigQuery/Oracle kinds, workspace-audit has no connector — the confirming query runs through the harness's own connector, and its output is the evidence. A `Freshness` line that says "live" and a source that's actually a stale snapshot is drift.
- **Never launder.** If the descriptor is a guess (you haven't confirmed the schema), mark it `[UNVERIFIED]` until a query proves it — the same rule [`research`](../research/SKILL.md) holds for sourced claims.

**Done when** the descriptor states kind / reach / holds / ask-it / freshness / do-not, the credential is referenced (never inlined), the reach is read-only, and every table, join, or path the "Ask it" line names has been exercised — not just confirmed to exist — by a query or listing, with `Freshness` confirmed or marked unverifiable — or the whole line is marked `[UNVERIFIED]`.

**No authority without evidence. The descriptor is a map to the data; a query is what proves it.**
