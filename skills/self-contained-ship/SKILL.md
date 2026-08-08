---
name: self-contained-ship
description: Prove a deliverable — an HTML artifact, a report, a bundle — is fully self-contained before it ships, with zero external URLs, CDN links, remote fonts, or runtime requests, every asset inlined or vendored, failing closed on any egress. Use before shipping or publishing an artifact, when the user says "self-contained", "no external requests", "inline everything", "offline-safe", "vendor the assets", "does it phone home", or "zero-egress gate". Differentiator - the containment gate (phones home to nobody), where transport-complete proves liveness (prod serves the exact SHA) and evidence-packet ladders the results.
---

# Self-Contained Ship — phones home to nobody

The containment covenant: **a deliverable is not shippable until it reaches nothing.** No CDN script, no remote font, no `fetch` at load, no socket, no beacon — every byte it needs is inlined or vendored beside it. This is the sibling of [`transport-complete`](../transport-complete/SKILL.md), and the two must not be confused: transport proves **liveness** (does prod serve the exact SHA?); this proves **containment** (does the artifact call out to anyone?). A page can be perfectly live and still leak every viewer's IP to a font CDN. Both gates, or neither is done.

The trap this island exists to close: an artifact that *looks* offline-safe because the eye skims past a `//cdn` in an attribute or a `fetch` three functions down. The eye is not evidence. Two rungs are.

## Rung 1 — the static scan (necessary, not sufficient)

[`scripts/scan-egress.sh`](scripts/scan-egress.sh) greps the deliverable for every egress vector and **fails closed (exit 1)** on any un-waived hit:

```bash
./scripts/scan-egress.sh path/to/artifact.html      # a file
./scripts/scan-egress.sh path/to/dist/               # or a whole bundle dir
```

It catches, case-insensitively so `HTTPS://` can't bypass: absolute schemes `http(s)://` **and** `wss://` / `ws://` / `ftp://`; the runtime tokens `fetch(`, `new WebSocket`, `XMLHttpRequest`, `EventSource`, `navigator.sendBeacon`; a dynamic `import(` of a URL; `@import` of a URL; `url(http|//)` in CSS; and `src=`/`href=` to `http|//` (covering `<link href=http`, `<script src=http`). An intentional call is waived only by a **bounded, case-sensitive, trailing** `# egress-ok` / `// egress-ok` / `/* egress-ok */` comment on that line — validated per hit against a start-or-whitespace prefix and an end-of-line anchor, never a substring, so a marker inside a URL (`…?egress-ok-not-really=1`) and even a URL-terminal `…//egress-ok` at end of line can't act as the comment delimiter and launder a real hit; the delimiter must follow a space or line-start. And where the regex ever slipped, the enforced rung 2 (sealed load) still catches the egress.

This rung is **advisory-leaning**: a regex cannot see egress that string-concatenation or obfuscation builds at runtime. It is the cheap first cut, not the certificate. Say so — never imply a green grep means contained.

## Rung 2 — the sealed load (the enforced evidence)

The check that could have failed is opening the artifact **offline with every request aborted** and asserting zero outbound. This is the enforced runtime rung — real evidence that the thing phones home to nobody:

```bash
node --input-type=module -e '
import { chromium } from "playwright";
const b = await chromium.launch();
const ctx = await b.newContext(); await ctx.setOffline(true);
const out = [];
await ctx.route("**", r => {                       // seal the network
  const u = r.request().url();
  if (!/^(file|data|blob|about):/.test(u)) out.push(u);
  r.abort();
});
const p = await ctx.newPage();
await p.goto("file://" + process.argv[1], { waitUntil: "load" }).catch(() => {});
await p.waitForTimeout(1500); await b.close();
if (out.length) { console.error("SEALED-LOAD FAIL — outbound attempts:\n" + out.join("\n")); process.exit(1); }
console.log("SEALED-LOAD PASS — phones home to nobody");
' "$PWD/artifact.html"
```

Every non-`file:`/`data:`/`blob:` request the page attempts is a violation; the rung exits non-zero on the first one. Capture its stdout as the containment evidence — this is the rung that goes on the ladder when [`evidence-packet`](../evidence-packet/SKILL.md) bundles the change, discriminating red (an artifact with one CDN link) against green (the inlined build).

## Enforced vs advisory

- **Enforced:** rung 2 (sealed offline load, zero outbound) and rung 1's exit code (any un-waived hit → non-zero). Both are commands that go red on real egress.
- **Advisory:** rung 1's *completeness* — the regex is a denylist of known vectors, not a proof of none. A clean grep with a failed sealed load is still a fail. When the artifact legitimately needs one endpoint, that is not a containment waiver — it is a **provenance** fact, mapped once via [`data-source-map`](../data-source-map/SKILL.md), and the sealed-load allow-list is widened deliberately, not silently.

**Done when** rung 1 exits 0 (or every hit carries a bounded trailing `egress-ok` with a stated reason) **and** rung 2 loads the artifact offline with zero outbound requests, its output captured. A green rung 1 alone is not done.

**No authority without evidence. A grep is a hint; the sealed offline load is the proof it phones home to nobody.**
