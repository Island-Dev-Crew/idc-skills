# Matt Pocock current-repo gap analysis — 2026-08-19

## Binding and method

- Upstream: <https://github.com/mattpocock/skills>
- Current upstream head observed: `885e2ca4d842d139e9aef4e48d366c63cb1b8013`
- Package version: `1.2.3`
- Historical Forge source archive commit: `2ab958093e83e0ec752e6c1c5932da465bf23e0c` (`1.1.0` in that tree)
- Archive-to-commit proof: every retained ZIP entry matched the historical Git blob tree, 167/167.
- Comparison command: `git diff 2ab958093e83e0ec752e6c1c5932da465bf23e0c 885e2ca4d842d139e9aef4e48d366c63cb1b8013 -- skills`
- Observed skill-surface delta: 41 historical `SKILL.md` files to 35 current; 83 skill-tree files changed, +845/-1459. Whole-repo delta: 143 files, +2990/-2165.

The comparison is source-to-source. It does not assume that a newer upstream file is automatically better than its fused Forge counterpart.

## Improvements that earned fusion

| Upstream change | Forge gap | 2.0.2 action | Result |
|---|---|---|---|
| `diagnosing-bugs` now requires secret redaction before showing commands, outputs, HAR/log/core artifacts, and asks for a redacted artifact when needed. | Forge `diagnose` had evidence discipline but no mandatory secret/PII boundary. | Added mandatory redaction before display or persistence. | Fused; no new seat. |
| `domain-modeling` explicitly routes active `CONTEXT.md` work and treats ADR creation as part of domain-model decisions. | Forge trigger was broad enough to attract arbitrary ADR work while its body allowed only term-derived decisions. | Added `CONTEXT.md`/ubiquitous-language routing and narrowed ADR jurisdiction to domain-term decisions. | Fused; registry trigger updated. |
| Current upstream continues to separate user-invoked/model-invoked semantics and uses richer phase-boundary guidance. | Forge already has explicit invocation parity, `wayfinder`, `handoff`, `model-routing`, and cross-family review. | Retained Forge composition; no duplicate import. | Covered. |

## Useful upstream ideas that did not earn direct adoption

- `ask-matt` is a helpful router, but the Forge already has a registry, explicit trigger phrases, and an archipelago-wide composition map. Importing it would duplicate routing authority.
- Current code-review and design material uses parallel sub-agents well, but the Forge's `cross-family-review` adds exact-head binding, family separation, and void-on-move. The upstream material is a reference, not a seat replacement.
- Current `wayfinder` fires research sub-agents in parallel. The Forge retained the idea but added depth/round/token limits and operator approval for paid backends; uncapped delegation did not survive the security review.
- Several upstream deprecated/personal/in-progress skills disappeared between 41 and 35 files. Deletion upstream is not evidence that a fused Forge capability should be removed; every Forge seat is evaluated on its own cases.

## No challenger nominated

No upstream candidate was nominated for a formal `skill-duel` against a Forge incumbent. The meaningful changes screened as narrow improvements to existing islands, not challengers with a distinct capability suitable for an identical case set. This is an advisory nomination decision, not a mechanical duel verdict. The 50-seat cap remains intact.

## Net assessment

Pocock's repository remains a high-value research upstream, particularly for concise triggers, active domain vocabulary, red-capable diagnosis, and phase-boundary thinking. The Forge is stronger where it adds evidence provenance, exact-head review, authority boundaries, signed supply-chain control, installation parity, and cross-harness honesty. Release 2.0.2 takes the two clear upstream improvements without importing its unbounded or overlapping orchestration patterns.
