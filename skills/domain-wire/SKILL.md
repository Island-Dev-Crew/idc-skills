---
name: domain-wire
description: Wire a domain the IDC way — the three-lane model (story / product / AI-native), one canonical per venture with siblings 308-redirecting to it, automatic graduation when a brand deed exists, and canonicals moving in the same commit. Use when connecting a domain, setting up DNS for a venture, deciding a canonical, adding a redirect shield, or when the user mentions "wire a domain", "graduate a domain", "308 redirect", "apex record", or "domain doctrine". Differentiator - IDC-native; encodes the lane model and the six governance rules, not generic DNS.
---

# Domain Wire — deeds first, dreams second

Wire a domain per the IDC **domain doctrine**. This island encodes the *method* — the lane model, the governance rules, the wiring order. The private registry of deeds (which venture owns which `.tld`) is the operator's own doctrine file, supplied at run time; this skill never hardcodes it. The one rule under all of it: **no link before it resolves** — a domain appears in code only after DNS answers.

## The three-lane model

Every venture answers two questions: *who is it for?* and *does it own its own brand deed yet?* Until it owns a live brand deed it rides the parent lanes; the moment it does, it **graduates**.

| Lane | Purpose | Rule |
|---|---|---|
| **story** (`parent.com`) | marketing, the venture map — humans **learn** here | uses **paths, not subdomains** (`parent.com/venture`); everything points back |
| **product** (`parent.app`) | working apps with no brand deed yet — humans **use** it | `venture.parent.app` until the deed exists, then graduate |
| **AI-native** (`parent.ai`) | agent-facing endpoints, specs — agents **consume** it | `name.parent.ai`; APIs always at `api.*` |
| **own-brand `.tld`** | the graduates — venture owns its deed | one **primary** per venture; every sibling **308**s to it |

## The six governance rules

1. **No link before it resolves.** A domain appears in production only after DNS answers. The doctrine registry is the allow-list; incubating deeds stay out of production HTML.
2. **One primary per venture.** Every family elects exactly one canonical; siblings 308 to it. Split traffic is split equity. *Exception: the parent's own three lane domains (`.com`/`.app`/`.ai`) are co-equal live surfaces by design, not siblings of one another — this rule governs each venture family riding the lanes or graduated onto its own deed. The parent's own shields (typo/variant domains) still 308 to its story domain.*
3. **Graduation is automatic when the deed exists.** Own brand + live product → connecting them outranks new feature work.
4. **Canonicals move in the same commit.** A domain flip carries OG tags, sitemaps, redirects, and cross-links together. The old `*.vercel.app` URL stays alive as a 308.
5. **Clients and family never ride IDC lanes.** Kept fully separate.
6. **Renewal is a security boundary.** Auto-renew on estate-wide; audit annually.

These rules are **advisory** — this skill ships no hook, so nothing mechanically blocks a violation. The `dig`/`whois` checks in §1 are the evidence that makes each rule real at run time: a rule holds only when the check for it passes. State that rather than implying the doctrine enforces itself.

## Wiring a domain

### 1. Confirm the deed, in order

**Gate A — registry membership.** Is the deed in the operator's doctrine registry, or has it been seen live inside the operator's own registrar account? If not, it rides a lane — full stop, regardless of what DNS says (rule 1). Do **not** put a bare brand domain in code on the strength of "I bought it."

**Gate B — resolution and corroboration.**

```bash
dig +short <domain> A                          # does anything answer, and to what?
whois <domain> | grep -iE 'registrar|expir'    # corroboration only — NOT ownership proof
```

WHOIS redaction means whois can only name the registrar company, never the account holder — a resolving domain on a shared registrar is not evidence of ownership. Ownership is confirmed only by seeing the deed listed inside the operator's registrar account (a human dashboard trip — hand it to the [`wizard`](../wizard/SKILL.md) island, same as the record entry in §3) or by its presence in the doctrine registry. A domain resolving to someone else's infrastructure is evidence *against* ownership, not for it.

Before wiring anything in a family, run Gate B against every domain the registry claims is live or shielded. Any domain whose observed state (parking IP, missing 308, wrong host) contradicts the registry is drift — record it and treat that entry as unverified until reconciled. Wire against observed DNS, never against the registry's description of it.

### 2. Pick the lane, or graduate

- **No brand deed yet** → ride a lane: product app at `venture.parent.app`, story at a **path** `parent.com/venture` (never a story subdomain), agent/API at `api.parent.ai`.
- **Brand deed owned + product live** → **graduate** (rule 3): elect one primary, point it at the live deploy, 308 every sibling to it, and move canonicals in the same commit (rule 4).

### 3. Set the records (Vercel-hosted deploys)

```
# apex → Vercel
@     A       76.76.21.21
# www and any subdomain → Vercel
www   CNAME   cname.vercel-dns.com
```

Verify the exact required values against the current Vercel dashboard before entering them — platforms change IPs. Entering them in the Namecheap/Vercel dashboards is a human-only dashboard trip: hand that to the [`wizard`](../wizard/SKILL.md) island, which opens each page and captures what's needed.

### 4. Shields — 308 the siblings

Every non-primary sibling (`.net`, `.store`, misspellings, the old `*.vercel.app`) 308-redirects to the primary — via a Namecheap URL-redirect record or a tiny Vercel redirect project. A shield that resolves to its own content is split equity (rule 2).

### 5. Move the canonical in one commit (rule 4)

When flipping a venture from a lane to its graduated primary, one commit carries: the canonical `<link rel="canonical">`, OG/Twitter tags, `sitemap.xml`, `robots.txt`, any Stripe/redirect URLs, and every internal cross-link. Point Search Console at a **verified property with real traffic** — keep the old vercel.app alive as a 308 so nothing 404s mid-flip.

**Done when** DNS answers for the primary, every sibling 308s to it, and the canonical + OG + sitemap + cross-links all name the primary in the same commit.

**No authority without evidence. No link before it resolves.**
