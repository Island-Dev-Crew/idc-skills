---
name: self-contained-ship
description: Prove a deliverable — an HTML artifact, a report, a bundle — is fully self-contained before it ships, with zero external URLs, CDN links, remote fonts, or runtime requests, every asset inlined or vendored, failing closed on any egress. Use before shipping or publishing an artifact, when the user says "self-contained", "no external requests", "inline everything", "offline-safe", "vendor the assets", "does it phone home", or "zero-egress gate". Differentiator - the containment gate (phones home to nobody), where transport-complete proves liveness (prod serves the exact SHA) and evidence-packet ladders the results.
---

# Self-Contained Ship: phones home to nobody

The containment covenant: **a deliverable is not shippable until it reaches nothing.** No CDN script, no remote font, no `fetch` at load, no socket, no beacon; every byte it needs is inlined or vendored beside it. This is the sibling of [`transport-complete`](../transport-complete/SKILL.md), and the two must not be confused: transport proves **liveness** (does prod serve the exact SHA?); this proves **containment** (does the artifact call out to anyone?). A page can be perfectly live and still leak every viewer's IP to a font CDN. Both gates, or neither is done.

The trap this island exists to close: an artifact that *looks* offline-safe because the eye skims past a `//cdn` in an attribute or a `fetch` three functions down. The eye is not evidence. Two rungs are.

## Rung 1: the static scan (necessary, not sufficient)

[`scripts/scan-egress.sh`](scripts/scan-egress.sh) statically scans the deliverable for every egress vector and **fails closed (exit 1)** on any un-waived external reference, **symlink**, non-regular file, **unreadable** file, directory **traversal error**, or **binary**:

```bash
./scripts/scan-egress.sh path/to/artifact.html                 # a file
./scripts/scan-egress.sh path/to/dist/                          # or a whole bundle dir
./scripts/scan-egress.sh --allow-binary '*.woff2' path/to/dist/ # waive reviewed binary assets (glob, repeatable)
```

It enumerates by **content, not extension** (so an extensionless `deploy` with a shebang or an UPPERCASE `.SH` can't hide), NUL-safely (a newline in a filename can't split an entry). Content classification has an exact boundary: a file is **text** iff its first 8 KB hold no NUL and no C0/C1 control byte outside `{tab, LF, VT, FF, CR}`, with high bytes treated as text so UTF-8 is never misflagged — so a **NUL-free** binary carrying raw control bytes (a P6 Netpbm rawbits image) is classified binary, not clean text. A green result means **every file was scanned clean or explicitly waived** — never "some files we couldn't look at": a **symlink** fails closed (bytes outside the shipped tree); an **unreadable** file and a directory **traversal error** each fail closed (a glob waiver can't launder bytes we never saw, and a clean sibling can't certify a tree we couldn't finish walking); a **binary** fails closed too — its strings are scanned with `grep -a` (an embedded URL is reported and fails, a grep read-error fails closed, never waived) and even a URL-free binary fails as uncertifiable-by-static-scan, until you review it and waive it with `--allow-binary <glob>` (a deliberate human act — scope the glob tightly; `'*'` waives all and is an escape hatch).

The text scan is a **whole-file, multiline-aware** static parse (run by `python3`, which is **required** — if it is absent the text rung fails **closed**, never open), so a fetching context split across lines (`src` and its `="//h"` on separate lines, a `fetch(` whose URL literal is on the next line) and every `srcset` candidate are caught. Independent, offset-preserving HTML, CSS, and JS masks keep HTML/JS/CSS comments and code-shaped ordinary strings from impersonating executable grammar; every accepted context records the URL's explicit start offset, rather than deriving one from a regex's width. Its pass/fail counts travel on a **separate trusted channel** — a file only the scanner writes, validated as a **whole**: exactly one newline-terminated record of three **canonical** base-10 fields (literal `0` or no-leading-zero, each bounded to nine digits so bash arithmetic can't hit octal or 64-bit overflow), no NUL, no extra line, no trailing bytes — and **anything else fails closed**. The counts are never parsed out of the findings stream, so neither a crafted finding byte (a NUL late in an otherwise-text file) nor a faulting producer (a partial line, an overflowed field, a leading-zero field) can collapse the gate into a false green. Every finding line is display-only, and **every untrusted path** in a diagnostic — a symlink name, a binary path, a readlink target — has its control bytes (NUL/ESC/LF/tab) neutralized, so a crafted filename can't forge terminal output or inject escape sequences.

It catches, case-insensitively so `HTTPS://` can't bypass: absolute schemes `http(s)://` **and** `wss://` / `ws://` / `ftp://` — including backslash spellings URL parsers normalize — and WebRTC `stun:` / `turn(s):`; WHATWG network-path authorities including 3+ slash, mixed slash/backslash, userinfo, percent-decoded-host, and IPv6 forms (while rejecting an invalid percent-decoded host); the runtime APIs `fetch`, WebSocket/EventSource/beacon/worker/importScripts/service-worker registration, HTTP-method `.open`, dynamic `import`, `window.open`, dot/bracket/optional-chain `location` navigation, fetching property assignments, and DOM `setAttribute` / `setAttributeNS`; and comment-separated static-module forms including compact imports/exports. Dot and bracket spellings on direct `window` / `document` / `globalThis` / `self` / `top` / `parent` / `navigator` paths are treated as the same recognized API or navigation sink. A statically knowable JavaScript string argument or bracket property name is decoded before matching: simple, hex, four-digit/code-point Unicode, legacy octal, identity escapes, and physical line continuations are resolved with a source-offset map; four-digit/code-point Unicode escapes inside recognized API identifier tokens are normalized too. Consumed URL values receive URL-parser preprocessing that removes ASCII tab, LF, and CR anywhere and trims leading/trailing C0 controls plus space before scheme/authority recognition. Runtime concatenation, values returned by functions, assignment through aliases (including otherwise-static variable aliases), and other nonliteral construction remain rung-1 residuals; the scanner does not claim general JavaScript data-flow evaluation.

CSS `@import` / `url()` / `image-set()` and HTML/SVG fetching attributes are likewise covered. Attribute matching is **real-markup bounded** by a start/end-tag state machine (HTML comments, raw-text bodies, stray quote bytes, and malformed attributes cannot forge or hide a tag), `data=` fetches only on `<object>`, and HTML character references are decoded **exactly once only inside parsed attributes**, with a decoded-to-raw offset map: numeric references follow browser replacement semantics (interior C0 controls are preserved and the specified C1 values remap), named/hex/decimal references are caught, two `srcset` candidates remain two findings, and a double-encoded entity or entity text inside `<script>` stays inert. Decoded inline `style` and meta-refresh `content` are scanned in their actual CSS/URL contexts. A genuine XML namespace declaration (`xmlns=`/`xmlns:pfx=` inside a tag — every one in the tag, not just the first) is the one non-fetching URI suppressed, and only there: a bare `xmlns=` in JS source, or a `fetch(xmlns=…)`, is real egress.

Plain `src`/`data` variables, `new URL` construction alone, unrelated `db.open`, and same-origin targets are not flagged. An outer `data:` or `blob:` URL is local rather than egress by itself, but literal executable `data:` payloads at recognized HTML-navigation, script/worker/module, modulepreload, and stylesheet sinks are not trusted as opaque: they are URL-preprocessed, percent-decoded once, and recursively scanned under their declared HTML, JavaScript, or CSS grammar. JavaScript detection uses the complete WHATWG JavaScript MIME essence set; a literal data-URL fragment is excluded from the response body, while its literal query and percent-encoded `#` / `?` bytes remain payload. A literal `javascript:` URL is likewise percent-decoded once and scanned as classic JavaScript, but only at a recognized navigation sink (HTML navigation attributes/meta refresh, `window.open`, direct location calls/assignments, fetching `href`/`src` properties, and matching DOM setters), never merely because prose or an ordinary string names the scheme. Recursion beyond eight nested stages fails closed; an executable decoded `data:` or `javascript:` payload above 1 MiB and an executable `data:...;base64` payload whose bytes cannot retain an exact source map each fail closed at the outer target. Non-executable `data:` payloads remain local, and `blob:` stays local because its constructed bytes are not present in the URL for rung 1 to recurse into. An intentional call is waived only by a **bounded, case-sensitive, trailing** `# egress-ok` / `// egress-ok` / `/* egress-ok */` comment on that hit's source line, validated against a start-or-whitespace prefix and an end-of-line anchor, never a substring. Where the static parse slips, the enforced rung 2 (sealed load) still catches the egress.

Nested `iframe[srcdoc]` markup is parsed after the outer attribute's one-pass decode, with its own nested attribute decode mapped back to the outer source bytes; excessive recursive `srcdoc` nesting fails closed. Closed **and EOF-terminated** `<script>` / `<style>` bodies are scanned because browsers execute or parse an unclosed raw-text block through EOF. WHATWG host recognition uses the standard's forbidden-host boundary rather than a DNS-label allowlist, so request-capable punctuation-leading hosts cannot pass as “invalid.” A same-origin URL whose later path contains `//` remains same-origin — network-path recognition applies at the URL/candidate start, not to an arbitrary double slash inside a local path.

This rung is **advisory-leaning**: a static match cannot see egress that string-concatenation or obfuscation builds at runtime. It is the cheap first cut, not the certificate. Say so; never imply a green scan means contained.

## Rung 2: the sealed load (enforced for the states it exercises)

The check that could have failed is opening the artifact **offline with every request aborted** and asserting zero outbound. The generic probe below enforces the initial-load state plus a 1.5-second observation window; it does not cover delayed timers, service-worker behavior, later navigation, or interaction-triggered requests it never exercises. Add an artifact-specific interaction script and justified delay for every reachable state that could initiate network before calling the artifact fully sealed.

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
console.log("SEALED-LOAD PASS — no outbound attempt in initial-load probe");
' "$PWD/artifact.html"
```

Every non-`file:`/`data:`/`blob:` request the exercised states attempt is a violation; the rung exits non-zero when it observes one. Capture its stdout and the exact interaction/observation plan as the containment evidence. This is the rung that goes on the ladder when [`evidence-packet`](../evidence-packet/SKILL.md) bundles the change, discriminating red (an artifact with one CDN link) against green (the inlined build).

## Enforced vs advisory

- **Enforced:** rung 2's sealed offline observation for the exact states and time window the script exercises, and rung 1's exit code (any un-waived hit → non-zero). Both are commands that go red on egress they observe.
- **Advisory:** rung 1's *completeness*. The regex is a denylist of known vectors, not a proof of none. A clean grep with a failed sealed load is still a fail. When the artifact legitimately needs one endpoint, that is not a containment waiver; it is a **provenance** fact, mapped once via [`data-source-map`](../data-source-map/SKILL.md), and the sealed-load allow-list is widened deliberately, not silently.

**Done when** rung 1 exits 0 (or every hit carries a bounded trailing `egress-ok` with a stated reason) **and** rung 2 loads the artifact offline with zero outbound requests across the documented initial, delayed, navigation, service-worker, and relevant interaction states, with its output and interaction plan captured. If only the generic probe ran, report `initial-load sealed`; do not promote it to full-lifecycle containment.

**No authority without evidence. A grep is a hint; a sealed offline run proves only the states it actually exercised.**
