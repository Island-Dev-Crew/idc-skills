#!/usr/bin/env bash
# self-contained-ship: STATIC egress scanner. Fails closed (exit 1) on any un-waived external
# reference, symlink, non-regular file, unreadable file, traversal error, OR binary in a
# deliverable. This is the static rung — necessary, not sufficient. Obfuscation and string-built
# URLs slip past a static matcher; the ENFORCED proof is the sealed-load runtime rung in SKILL.md.
# State that boundary; never imply this scan alone certifies containment.
#
# SECURE-BY-DEFAULT: a green result means "every file was scanned clean OR explicitly human-waived"
# — never "some files we could not look at." A symlink fails closed (bytes outside the tree); a
# non-regular file (FIFO/socket/device) fails closed and is NEVER read (reading a FIFO would hang);
# an UNREADABLE file fails closed (a glob waiver cannot launder bytes we never saw); a traversal
# error (an unreadable directory) fails closed (a clean-looking sibling cannot certify a tree we
# could not fully walk); a binary fails closed too — its strings are `grep -a`-scanned, an embedded
# URL is reported and fails EVEN IF the binary is glob-waived, and a URL-free binary fails as
# uncertifiable until reviewed and waived with `--allow-binary <glob>`.
#
# CONTENT CLASSIFICATION (exact boundary): a file is TEXT iff its first 8192 bytes contain NO NUL
# and NO C0/C1 control byte outside the text-whitespace set {tab, LF, VT, FF, CR}; high bytes
# 0x80-0xFF are treated as text so UTF-8 is never misflagged. A NUL-FREE binary that carries raw
# control bytes — e.g. a P6 Netpbm rawbits image whose pixel bytes include 0x01-0x08 — is therefore
# classified BINARY (and scanned/waived on the binary path), NOT clean text. This is stricter than a
# NUL-only heuristic (which such a file would slip past).
#
# The text egress scan is a WHOLE-FILE (multiline-aware) static parse, run by python3, so a fetching
# context split across lines (`src\n="//h"`, `fetch(\n"//h")`) and every srcset candidate are caught.
# Its JS, CSS, and HTML masks preserve original byte offsets while keeping comments and ordinary
# strings from impersonating executable grammar. python3 is REQUIRED for the text rung: if it is
# missing the scan cannot certify text files and FAILS CLOSED (exit 1), never open. `jq` is not used.
#
# TRUSTED COUNTS CHANNEL: the pass/fail gate is driven by a counts line python writes to a SEPARATE
# temp file — never parsed out of the findings stream. Finding text is attacker-influenced bytes
# (a NUL after the classification window can flip grep into "Binary file matches" mode and collapse
# an in-band trailer to zero -> false green). The counts line is STRICTLY validated (exactly three
# all-digit fields) and anything else FAILS CLOSED; finding lines are display-only, with control
# bytes sanitized so they can't carry terminal escapes either.
#
# HTML/SVG attribute matching is TAG-BOUNDED and HTML-comment/raw-text aware. A fetching attribute
# (`src=`, `srcset=`, ...) counts only INSIDE real markup, so a plain JS variable is not egress; the
# `data=` attribute fetches only on `<object>`. Attribute character references are decoded exactly
# once with a decoded-to-raw offset map: `&sol;&sol;host` is caught, while `&amp;#47;` is not recursively
# decoded. JS property assignments and DOM attribute setters stay caught by the JS grammar scanner.
#
# Documented residuals a static scan cannot close (keep the sealed-load runtime rung underneath):
#   - egress that string-concatenation / obfuscation / runtime code BUILDS after load
#   - a request issued by a service worker, a delayed timer, or an interaction the scan never runs
set -uo pipefail

# What a browser (or an XML/CSS/JS consumer) FETCHES. Absolute schemes http(s)/ws(s)/ftp — including
# backslash forms URL parsers normalize to slashes — and WebRTC stun/turn(s) match anywhere. A
# network-path authority is caught only in a fetching CONTEXT: HTML/SVG URL attributes (including
# decoded entities, nested iframe srcdoc markup, and every srcset candidate), inline/document CSS,
# JS network calls, static/dynamic modules, window.open/location navigation, fetching property
# assignments, DOM setAttribute/NS, or
# meta refresh. WHATWG-equivalent 3+ slash, mixed slash/backslash, userinfo, percent-decoded-host, and
# IPv6 forms are recognized; an invalid percent-decoded host is not. JS/HTML/CSS comments, a plain
# variable, and same-origin/data/blob targets are not flagged. Runtime-built URLs remain the disclosed
# residual rung 2 catches. The bash regex below is only the absolute-scheme set for BINARY scanning.
EGRESS_BIN='(https?|wss?|ftp):[/\\][/\\]|(^|[^a-z])(stun|turns?):[a-z0-9]'

usage() { echo "usage: scan-egress.sh [--allow-binary <glob>]... <file-or-dir> ..." >&2; exit 2; }

# Neutralize control bytes (NUL/ESC/LF/tab/DEL, all of C0 + 0x7F) in an UNTRUSTED path or diagnostic
# before it reaches the terminal, so a crafted filename can't forge output or inject escape sequences.
# High bytes (0x80-0xFF) are preserved so a legitimate UTF-8 name stays readable.
san_path() { LC_ALL=C printf '%s' "$1" | LC_ALL=C tr '\000-\037\177' '?'; }

# A CANONICAL base-10 count: literal "0", or a 1-9 leading digit with up to 8 more (< 10^9). Rejecting
# leading zeros kills bash octal ambiguity (`08` -> "value too great for base"); the 9-digit ceiling
# keeps the later `$(())` well inside 64-bit range so no silent overflow-wrap can reach the gate.
is_canon_count() {
  case "$1" in
    0) return 0 ;;
    ''|*[!0-9]*) return 1 ;;                        # empty or a non-digit byte
    0*) return 1 ;;                                 # leading zero (and not the literal "0")
    ?|??|???|????|?????|??????|???????|????????|?????????) return 0 ;;  # 1..9 digits
    *) return 1 ;;                                  # >= 10 digits -> reject (overflow risk)
  esac
}

# Validate the trusted counts side-channel as a WHOLE: the file must be EXACTLY one newline-terminated
# record "<v> <w> <b>\n" with three canonical fields and nothing else — no NUL, no non-ASCII, no extra
# line, no trailing bytes. Echoes "v w b" and returns 0 only then; every producer/runtime fault (a
# crash mid-write, a partial line, an overflowed field) returns non-zero so the caller FAILS CLOSED.
validate_counts_file() {
  local f="$1"
  # (a) reject any byte outside the canonical alphabet {0-9, space, LF} — catches NUL / ESC / UTF-8.
  [ "$(LC_ALL=C tr -d '0-9 \n' < "$f" 2>/dev/null | wc -c | tr -cd '0-9')" = "0" ] || return 1
  # (b) exactly one newline in the file AND it is the final byte (one terminated record, no more).
  [ "$(LC_ALL=C wc -l < "$f" 2>/dev/null | tr -cd '0-9')" = "1" ] || return 1
  [ "$(LC_ALL=C tail -c 1 "$f" 2>/dev/null | od -An -tu1 | tr -cd '0-9')" = "10" ] || return 1
  # (c) the single line is exactly three space-separated canonical integers.
  local line; line="$(head -n 1 "$f")"
  set -f
  # shellcheck disable=SC2086  # intentional word split of the already-charset-validated line
  set -- $line
  set +f
  [ "$#" -eq 3 ] || return 1
  is_canon_count "$1" && is_canon_count "$2" && is_canon_count "$3" || return 1
  printf '%s %s %s' "$1" "$2" "$3"
}

# --- args: collect --allow-binary globs, then scan targets ---
targets=()
allow=()
while [ "$#" -gt 0 ]; do
  case "$1" in
    --allow-binary) shift; [ "$#" -ge 1 ] || usage; allow+=("$1"); shift ;;
    --allow-binary=*) allow+=("${1#*=}"); shift ;;
    --) shift; while [ "$#" -gt 0 ]; do targets+=("$1"); shift; done ;;
    -*) echo "scan-egress: unknown option: $1" >&2; usage ;;
    *) targets+=("$1"); shift ;;
  esac
done
[ "${#targets[@]}" -ge 1 ] || usage

# Enumerate by CONTENT, not extension (closes extensionless / UPPERCASE / novel extensions), NUL-safely
# (`find -print0` + `read -d ''`) so a filename with an embedded newline can't split or hide an entry.
# A non-regular file (FIFO/socket/device) is tracked separately and NEVER read; an unreadable file and a
# find/traversal error each fail closed.
files=()
symlinks=()
binaries=()
specials=()
unreadable=()
traversal_err=0
classify_file() {  # <path> -> files (text/empty) | binaries | specials | unreadable
  if [ ! -f "$1" ]; then specials+=("$1"); return; fi       # FIFO/socket/device -> never grep (would hang)
  if [ ! -r "$1" ]; then unreadable+=("$1"); return; fi      # bytes we cannot see -> fail closed, no waiver
  if [ ! -s "$1" ]; then files+=("$1"); return; fi           # empty file: no content, benign
  # TEXT iff no non-whitespace control byte survives (see CONTENT CLASSIFICATION header). tr deletes
  # printable, text-whitespace, and high (UTF-8) bytes; anything left is NUL or a C0/C1 control -> binary.
  local nt
  nt="$(head -c 8192 "$1" 2>/dev/null | LC_ALL=C tr -d '[:print:][:space:]\200-\377' | wc -c | tr -cd '0-9')"
  if [ "${nt:-1}" -gt 0 ]; then binaries+=("$1"); else files+=("$1"); fi
}
scan_tree() {  # <dir>: enumerate; any find stderr (e.g. an unreadable dir) fails the tree closed.
  local p="$1" ef; ef="$(mktemp)"
  while IFS= read -r -d '' f; do symlinks+=("$f"); done < <(find "$p" -type l -print0 2>"$ef")
  [ -s "$ef" ] && traversal_err=1; : > "$ef"
  while IFS= read -r -d '' f; do classify_file "$f"; done < <(find "$p" -type f -print0 2>"$ef")
  [ -s "$ef" ] && traversal_err=1; : > "$ef"
  while IFS= read -r -d '' f; do specials+=("$f"); done < <(find "$p" \( -type p -o -type s -o -type b -o -type c \) -print0 2>"$ef")
  [ -s "$ef" ] && traversal_err=1
  rm -f "$ef"
}
for p in "${targets[@]}"; do
  if [ -L "$p" ]; then
    symlinks+=("$p")
  elif [ -d "$p" ]; then
    scan_tree "$p"
  elif [ -e "$p" ]; then
    classify_file "$p"
  else
    echo "scan-egress: no such path: $(san_path "$p")" >&2; exit 2
  fi
done
if [ $(( ${#files[@]} + ${#symlinks[@]} + ${#binaries[@]} + ${#specials[@]} + ${#unreadable[@]} )) -lt 1 ] && [ "$traversal_err" -eq 0 ]; then
  echo "scan-egress: no scannable files under: $(san_path "${targets[*]}")" >&2; exit 2
fi

violations=0
waived=0
benign=0

# --- text files: whole-file, multiline-aware static match in python3 (fails closed if absent) ---
# The file list is passed via a temp-file path in the environment and the program via a heredoc on
# stdin — NEVER as `$(python3 - <<PY ...)`, because a heredoc carrying parens/backticks inside a
# command substitution breaks bash's parser (same residual the git guard documents). python3 stdout
# is captured to a temp file; a non-zero python exit (a crash) FAILS CLOSED.
if [ "${#files[@]}" -gt 0 ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    echo "scan-egress: python3 not found; cannot certify text files — FAIL CLOSED" >&2
    exit 1
  fi
  sc_in="$(mktemp)"; sc_out="$(mktemp)"; sc_err="$(mktemp)"; sc_cnt="$(mktemp)"
  printf '%s\0' "${files[@]}" > "$sc_in"
  SCAN_EGRESS_FILELIST="$sc_in" SCAN_EGRESS_COUNTS="$sc_cnt" python3 - >"$sc_out" 2>"$sc_err" <<'PY'
import re, os, bisect, html

paths = [p for p in open(os.environ["SCAN_EGRESS_FILELIST"], "rb").read().split(b"\0") if p]

# Waiver: a BOUNDED, case-sensitive, TRAILING comment on the hit's own line. The delimiter must sit
# at line-start or after whitespace, so a URL-internal `//` can't act as the comment delimiter.
WAIVER = re.compile(r'(?:^|[ \t])(?:#|//|/\*)[ \t]*egress-ok(?:[ \t]*\*/)?[ \t]*$')

# URL recognition is separated from grammar recognition. A grammar matcher identifies the literal
# value a browser consumes; this routine then applies WHATWG-style authority rules to that value.
# In particular, 3+ slash forms, mixed slash/backslash forms, userinfo, and a percent-decoded host
# are external. A percent-decoded forbidden host byte (e.g. `%2f`) is invalid, not an authority.
# Every matcher returns the URL's EXPLICIT start offset — no fixed-width `m.end()-N` arithmetic.
ABS = re.compile(r'(?i)(?:https?|wss?|ftp):(?P<slashes>[/\\]{2,})')
STUN = re.compile(r'(?i)(?:^|[^a-z])(stun|turns?):[a-z0-9\[]')
SLASH_RUN = re.compile(r'[/\\]{2,}')
FORBIDDEN_HOST = re.compile(r'[\x00-\x20\x7f#/:<>?@\[\\\]\^|]')


def percent_decode_once(s):
    out = []
    i = 0
    while i < len(s):
        if s[i] != "%":
            out.append(s[i])
            i += 1
            continue
        if i + 2 >= len(s) or not re.match(r'^[0-9a-fA-F]{2}$', s[i + 1:i + 3]):
            return None
        out.append(chr(int(s[i + 1:i + 3], 16)))
        i += 3
    return "".join(out)


def valid_authority(value, run_end):
    # Read exactly the URL authority. Only URL delimiters end it: WHATWG accepts punctuation such as
    # apostrophe, bang, dollar, ampersand, star, comma, semicolon, parens, and braces in a special
    # host. Treating source-language punctuation as an authority delimiter would launder those hosts.
    end = run_end
    while end < len(value) and value[end] not in '/\\?# \t\r\n':
        end += 1
    raw = value[run_end:end]
    if not raw:
        return False
    # Split userinfo BEFORE host percent-decoding. WHATWG permits percent-encoded `/` and other
    # delimiters in userinfo (`//u%2F:p@host`); decoding the whole authority first would reject that
    # valid credential and accidentally hide the real host after `@`.
    raw_hostport = raw.rsplit("@", 1)[-1]
    hostport = percent_decode_once(raw_hostport)
    if hostport is None:
        return False
    if not hostport:
        return False
    if hostport.startswith("["):
        close = hostport.find("]")
        if close < 2:
            return False
        host = hostport[1:close]
        rest = hostport[close + 1:]
        if rest and not re.match(r'^:[0-9]*$', rest):
            return False
        return bool(re.match(r'^[0-9a-fA-F:.vV-]+$', host))
    if hostport.count(":") > 1:
        return False
    if ":" in hostport:
        host, port = hostport.rsplit(":", 1)
        if not re.match(r'^[0-9]*$', port):
            return False
    else:
        host = hostport
    if not host or FORBIDDEN_HOST.search(host):
        return False
    return True


def network_start_allowed(value, start, allow_multiple):
    prefix = value[:start]
    if not prefix.strip():                         # one URL literal, optional leading whitespace
        return True
    if allow_multiple:
        comma = prefix.rfind(",")                  # next srcset/image-set candidate
        return (comma >= 0 and not prefix[comma + 1:].strip()) or prefix[-1:].isspace()
    return False


def external_offsets(value, allow_multiple=False):
    found = {}
    absolute_slashes = []
    for m in ABS.finditer(value):
        if valid_authority(value, m.end("slashes")):
            found[m.start()] = 1
            absolute_slashes.append((m.start("slashes"), m.end("slashes")))
    for m in STUN.finditer(value):
        found[m.start(1)] = 1
    for m in SLASH_RUN.finditer(value):
        # Do not double-report the slash run belonging to an absolute special-scheme URL.
        if any(a <= m.start() < b for a, b in absolute_slashes):
            continue
        if m.start() > 0 and value[m.start() - 1] == ":":
            continue
        if not network_start_allowed(value, m.start(), allow_multiple):
            continue
        if valid_authority(value, m.end()):
            found[m.start()] = 1
    return sorted(found)

# HTML/SVG fetching attributes are TAG-BOUNDED: an attribute only fetches inside a real `<tag ...>`
# span (quote-aware, so a `>` inside a quoted value doesn't end the span; DOTALL, so a multiline tag
# still matches; an unclosed tag at EOF still counts). A bare `src=`/`data=` in plain JS source is a
# variable, not markup, and is NOT matched here (JSPROP covers dot-prefixed property assignments).
# `data` fetches ONLY on <object>; on any other element it is inert markup.
TAGSPAN = re.compile(r'(?is)<([a-z][a-z0-9:-]*)((?:"[^"]*"|\'[^\']*\'|[^<>"\'])*)>?')
ATTR = re.compile(r'(?is)(?<![\w:.-])([a-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'>]+))')
FETCH_ATTRS = {
    "imagesrcset", "srcset", "src", "xlink:href", "href", "formaction", "action",
    "poster", "background", "cite", "ping", "manifest", "data"
}
SET_ATTRS = FETCH_ATTRS - {"data", "manifest"}

# A genuine namespace such as `<svg xmlns="http://www.w3.org/2000/svg">` is an identifier, not a
# fetch. Only a parsed `xmlns`/`xmlns:*` attribute receives that suppression in the loop below.
CTRL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')     # body sanitizer (keeps tab; body is single-line)
PATHCTRL = re.compile(r'[\x00-\x1f\x7f]')          # path sanitizer: strip ALL controls incl NUL/LF/tab


def sanp(p):                                       # an untrusted path must not forge terminal output
    return PATHCTRL.sub("?", p)


def mask_range(chars, start, end):
    for i in range(start, min(end, len(chars))):
        if chars[i] != "\n":
            chars[i] = " "


def mask_html_comments(source):
    chars = list(source)
    ranges = []
    for m in re.finditer(r'(?s)<!--.*?(?:-->|$)', source):
        ranges.append((m.start(), m.end()))
        mask_range(chars, m.start(), m.end())
    return "".join(chars), ranges


RAWTEXT_OPEN = re.compile(
    r'(?is)<(script|style|title|textarea)\b((?:"[^"]*"|\'[^\']*\'|[^<>"\'])*)>'
)


def rawtext_blocks(source):
    # Browsers parse an unclosed script/style through EOF. Yield both closed and EOF-terminated raw
    # blocks; the opening offset lets a mixed-source caller reject an opening tag inside a JS string.
    pos = 0
    while True:
        opened = RAWTEXT_OPEN.search(source, pos)
        if not opened:
            return
        tag = opened.group(1).lower()
        closed = re.compile(r'(?is)</' + re.escape(tag) + r'\s*>').search(source, opened.end())
        body_end = closed.start() if closed else len(source)
        yield tag, opened.start(), opened.end(), body_end
        if not closed:
            return
        pos = closed.end()


def html_markup_mask(source):
    # HTML comments and raw-text/RCDATA element bodies are not markup. Mask them without changing
    # length/newline positions so a tag-shaped JS string or escaped example cannot become a tag.
    masked, _ = mask_html_comments(source)
    chars = list(masked)
    for _, _, body_start, body_end in rawtext_blocks(masked):
        mask_range(chars, body_start, body_end)
    return "".join(chars)


ENTITY = re.compile(r'&(?:#[xX][0-9a-fA-F]+;?|#[0-9]+;?|[a-zA-Z][a-zA-Z0-9]+;)')


def decode_html_attr_once(raw, origin):
    # Decode one HTML character-reference pass ONLY for a parsed attribute. Each decoded character
    # points back to the first raw byte of its entity, keeping diagnostics, waiver lines, and dedup
    # byte-stable. `&amp;#47;` therefore becomes literal `&#47;`, never a second-pass slash.
    out = []
    mapping = []
    i = 0
    while i < len(raw):
        raw_off = origin + i if isinstance(origin, int) else origin[i]
        m = ENTITY.match(raw, i)
        if m:
            token = m.group(0)
            decoded = html.unescape(token)
            if decoded != token:
                out.extend(decoded)
                mapping.extend([raw_off] * len(decoded))
                i = m.end()
                continue
        out.append(raw[i])
        mapping.append(raw_off)
        i += 1
    return "".join(out), mapping


def map_offset(mapping, off):
    if mapping is None:                             # original source: identity byte/character map
        return off
    if off < 0 or off >= len(mapping):
        return None
    return mapping[off]


def add_value_hits(value, mapping, hits, allow_multiple=False):
    for off in external_offsets(value, allow_multiple):
        raw = map_offset(mapping, off)
        if raw is not None:
            hits[raw] = 1


def lex_source(source, line_comments):
    # Produce an offset-preserving CODE mask plus literal spans. Comments and literal bodies become
    # spaces (newlines retained). Grammar regexes operate only on CODE; a matched API then consumes
    # its adjacent literal from the original span. This prevents comments/ordinary strings from
    # impersonating executable fetch grammar without losing the URL inside a real argument.
    chars = list(source)
    spans = []
    opaque = []
    i = 0
    n = len(source)
    while i < n:
        if line_comments and source.startswith("<!--", i):
            end = source.find("\n", i)
            end = n if end < 0 else end
            opaque.append((i, end))
            mask_range(chars, i, end)
            i = end
            continue
        if source.startswith("/*", i):
            end = source.find("*/", i + 2)
            end = n if end < 0 else end + 2
            opaque.append((i, end))
            mask_range(chars, i, end)
            i = end
            continue
        if line_comments and source.startswith("//", i):
            end = source.find("\n", i + 2)
            end = n if end < 0 else end
            opaque.append((i, end))
            mask_range(chars, i, end)
            i = end
            continue
        if source[i] in "\"'`":
            quote = source[i]
            start = i
            i += 1
            content = i
            while i < n:
                if source[i] == "\\":
                    i = min(n, i + 2)
                    continue
                if source[i] == quote:
                    break
                i += 1
            content_end = i
            if i < n:
                i += 1
            span = {"start": start, "content": content, "content_end": content_end, "end": i,
                    "value": source[content:content_end]}
            spans.append(span)
            opaque.append((start, i))
            mask_range(chars, start, i)
            continue
        i += 1
    return "".join(chars), spans, opaque


def in_ranges(pos, ranges):
    return any(a <= pos < b for a, b in ranges)


def next_literal(mask, spans, pos, limit=None):
    limit = len(mask) if limit is None else limit
    for span in spans:
        if span["start"] < pos:
            continue
        if span["start"] >= limit:
            return None
        if mask[pos:span["start"]].strip():
            return None
        return span
    return None


def literal_segment(mask, spans, start, end):
    inside = [s for s in spans if start <= s["start"] and s["end"] <= end]
    if len(inside) != 1:
        return None
    span = inside[0]
    if mask[start:span["start"]].strip() or mask[span["end"]:end].strip():
        return None
    return span


def call_args(mask, spans, open_pos):
    # Return [(segment_start, segment_end, literal-or-None), ...] for one call. Delimiters inside
    # comments/strings are already spaces, so nested syntax cannot split a top-level argument.
    args = []
    seg = open_pos + 1
    depth = 0
    i = seg
    while i < len(mask):
        ch = mask[i]
        if ch in "([{":
            depth += 1
        elif ch == ")":
            if depth == 0:
                args.append((seg, i, literal_segment(mask, spans, seg, i)))
                return args, i
            depth -= 1
        elif ch in "]}":
            if depth:
                depth -= 1
        elif ch == "," and depth == 0:
            args.append((seg, i, literal_segment(mask, spans, seg, i)))
            seg = i + 1
        i += 1
    return [], None


def span_value_hits(span, mapping, hits, allow_multiple=False):
    for rel in external_offsets(span["value"], allow_multiple):
        source_off = span["content"] + rel
        raw = map_offset(mapping, source_off)
        if raw is not None:
            hits[raw] = 1


def scan_js(source, mapping, hits):
    code, spans, _ = lex_source(source, True)

    call = re.compile(
        r'(?i)\b(?:fetch|import|importScripts|WebSocket|EventSource|sendBeacon|Worker|SharedWorker)'
        r'\s*(?:\?\.\s*)?\('
    )
    for m in call.finditer(code):
        args, _ = call_args(code, spans, m.end() - 1)
        if args and args[0][2]:
            span_value_hits(args[0][2], mapping, hits)

    for rx in (
        re.compile(r'(?i)\bserviceWorker\s*\.\s*register\s*\('),
        re.compile(r'(?i)\bwindow\s*\.\s*open\s*\('),
        re.compile(r'(?i)\blocation\s*\.\s*(?:assign|replace)\s*\('),
    ):
        for m in rx.finditer(code):
            args, _ = call_args(code, spans, m.end() - 1)
            if args and args[0][2]:
                span_value_hits(args[0][2], mapping, hits)

    # XHR-like `.open("METHOD", URL)`, while leaving an unrelated one-argument `db.open(URL)` clean.
    for m in re.finditer(r'(?i)\.\s*open\s*\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        if len(args) >= 2 and args[0][2] and args[1][2]:
            method = args[0][2]["value"].upper()
            if method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}:
                span_value_hits(args[1][2], mapping, hits)

    # Static import/export: comments are blank space in CODE, literals are separate spans. The
    # bounded clause cannot cross `=`, `;`, `(`, `.`, or a string into a distant `from`.
    mod_from = re.compile(r'(?is)\b(?:import|export)\b[\w$*{},\s]*?\bfrom\b')
    for m in mod_from.finditer(code):
        span = next_literal(code, spans, m.end())
        if span:
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)\bimport\b', code):
        p = m.end()
        span = next_literal(code, spans, p)
        if span:  # bare side-effect import; import.meta/import(...) contain visible punctuation
            span_value_hits(span, mapping, hits)

    # Dot property assignments and location.href/direct location assignments.
    prop = r'(?:srcset|src|href|action|formaction|poster|background|cite|ping)'
    for m in re.finditer(r'(?i)\.\s*' + prop + r'\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)(?<![.\w])location\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)\b(?:window|document)\s*\.\s*location\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            span_value_hits(span, mapping, hits)

    # Bracket navigation: location["href"] = URL (including window.location[...]).
    for m in re.finditer(r'(?i)\blocation\s*\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name or name["value"].lower() != "href":
            continue
        tail = re.match(r'\s*=', code[close + 1:])
        if not tail:
            continue
        span = next_literal(code, spans, close + 1 + tail.end())
        if span:
            span_value_hits(span, mapping, hits)

    # Bracketed global APIs/properties: window["fetch"](URL), window["open"](URL), and
    # window/document["location"] = URL. The property-name literal is grammar, not a URL.
    for m in re.finditer(r'(?i)\b(window|document)\s*\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name:
            continue
        prop_name = name["value"]
        if prop_name.lower() == "location":
            tail = re.match(r'\s*=', code[close + 1:])
            if tail:
                span = next_literal(code, spans, close + 1 + tail.end())
                if span:
                    span_value_hits(span, mapping, hits)
            else:
                chained = re.match(r'\s*\[', code[close + 1:])
                if chained:
                    open2 = close + 1 + chained.end()
                    close2 = code.find("]", open2)
                    member = literal_segment(code, spans, open2, close2) if close2 >= 0 else None
                    assign = re.match(r'\s*=', code[close2 + 1:]) if close2 >= 0 else None
                    if member and member["value"].lower() == "href" and assign:
                        span = next_literal(code, spans, close2 + 1 + assign.end())
                        if span:
                            span_value_hits(span, mapping, hits)
            continue
        tail = re.match(r'\s*(?:\?\.\s*)?\(', code[close + 1:])
        if not tail:
            continue
        if prop_name.lower() in {"fetch", "open", "websocket", "eventsource", "sendbeacon",
                                "worker", "sharedworker", "importscripts"}:
            args, _ = call_args(code, spans, close + 1 + tail.end() - 1)
            if args and args[0][2]:
                span_value_hits(args[0][2], mapping, hits)

    # DOM setters: setAttribute(name, value) and setAttributeNS(ns, name, value).
    for m in re.finditer(r'(?i)\.\s*(setAttributeNS|setAttribute)\s*\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        name_i, value_i = (1, 2) if m.group(1).lower() == "setattributens" else (0, 1)
        if len(args) <= value_i or not args[name_i][2] or not args[value_i][2]:
            continue
        name = args[name_i][2]["value"].lower()
        if name in SET_ATTRS:
            span_value_hits(args[value_i][2], mapping, hits, name in {"srcset", "imagesrcset", "ping"})


def scan_css(source, mapping, hits):
    css_code, spans, _ = lex_source(source, False)
    _, _, js_opaque = lex_source(source, True)
    calls = re.compile(r'(?i)(?<![\w$.])(?:url|image-set|image)\s*\(')
    for m in calls.finditer(css_code):
        # A CSS-shaped token inside a JS comment/string is inert. A real `url("//h")` begins before
        # its quoted URL, and a real unquoted `url(//h)` begins before JS would see `//` as a comment.
        if in_ranges(m.start(), js_opaque):
            continue
        if re.search(r'(?i)\bnew\s*$', css_code[:m.start()]):
            continue
        args, close = call_args(css_code, spans, m.end() - 1)
        if close is None:
            continue
        for start, end, span in args:
            if span:
                span_value_hits(span, mapping, hits)
            else:
                # image-set candidates commonly append a density/type descriptor after the URL
                # literal, so the whole comma segment is not a literal-only JS-style argument.
                candidates = [s for s in spans if start <= s["start"] and s["end"] <= end and
                              not css_code[start:s["start"]].strip()]
                if candidates:
                    for candidate in candidates:
                        span_value_hits(candidate, mapping, hits)
                    continue
                left = start
                while left < end and source[left].isspace():
                    left += 1
                right = end
                while right > left and source[right - 1].isspace():
                    right -= 1
                for rel in external_offsets(source[left:right]):
                    raw = map_offset(mapping, left + rel)
                    if raw is not None:
                        hits[raw] = 1
    for m in re.finditer(r'(?i)@import\b', css_code):
        if in_ranges(m.start(), js_opaque):
            continue
        span = next_literal(css_code, spans, m.end())
        if span:
            span_value_hits(span, mapping, hits)


def scan_srcdoc(source, mapping, hits, depth=0):
    # `iframe[srcdoc]` is parsed as a new HTML document after the outer attribute is decoded. Walk
    # that real second parsing stage with the outer decoded-to-raw map, including another one-pass
    # decode for each nested attribute. Excessive recursive srcdoc nesting fails closed.
    if depth > 8:
        raise RuntimeError("srcdoc nesting exceeds scanner safety bound")
    masked, _ = mask_html_comments(source)
    markup = html_markup_mask(source)

    for raw_tag, _, body_start, body_end in rawtext_blocks(masked):
        body = source[body_start:body_end]
        body_map = mapping[body_start:body_end]
        if raw_tag == "script":
            scan_js(body, body_map, hits)
        elif raw_tag == "style":
            scan_css(body, body_map, hits)

    for tm in TAGSPAN.finditer(markup):
        tag = tm.group(1).lower()
        by_name = {}
        for am in ATTR.finditer(tm.group(2)):
            name = am.group(1).lower()
            gi = next((g for g in (2, 3, 4) if am.group(g) is not None), None)
            if gi is None:
                continue
            base = tm.start(2) + am.start(gi)
            raw_value = source[base:base + len(am.group(gi))]
            value, value_map = decode_html_attr_once(raw_value, mapping[base:base + len(raw_value)])
            if name not in by_name:
                by_name[name] = (value, value_map)
            if name == "xmlns" or name.startswith("xmlns:"):
                continue
            if name in FETCH_ATTRS and not (name == "data" and tag != "object"):
                add_value_hits(value, value_map, hits, name in {"srcset", "imagesrcset", "ping"})
            elif name == "srcdoc" and tag == "iframe":
                scan_srcdoc(value, value_map, hits, depth + 1)
            elif name == "style":
                scan_css(value, value_map, hits)
            elif name.startswith("on"):
                scan_js(value, value_map, hits)
        if tag == "meta" and "http-equiv" in by_name and "content" in by_name:
            if by_name["http-equiv"][0].strip().lower() == "refresh":
                content, content_map = by_name["content"]
                url = re.search(r'(?i)\burl\s*=', content)
                if url:
                    add_value_hits(content[url.end():], content_map[url.end():], hits)


def likely_js_literal(source, span):
    # A tag-shaped substring inside a normal JS literal is not markup. Restrict this heuristic to
    # literals introduced by unmistakable expression punctuation/keywords so an apostrophe in HTML
    # prose (`don't <img ...>`) cannot hide the following real tag.
    pos = span["start"] - 1
    while pos >= 0 and source[pos].isspace():
        pos -= 1
    if pos >= 0 and source[pos] in "=(:,[!+?":
        return True
    return bool(re.search(r'(?i)\b(?:return|throw|yield|case)\s*$', source[:span["start"]]))


def tag_is_js_literal(tag_start, source, spans):
    for span in spans:
        if span["start"] < tag_start < span["end"]:
            return likely_js_literal(source, span)
        if span["start"] > tag_start:
            break
    return False


violations = waived = benign = 0
for pb in paths:
    path = os.fsdecode(pb)
    try:
        with open(pb, "rb") as fh:
            text = fh.read().decode("latin-1")     # latin-1: byte<->char 1:1, stable offsets, no decode err
    except OSError:
        violations += 1
        print("UNREADABLE %s (could not read during scan — fail closed)" % sanp(path))
        continue

    starts = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            starts.append(i + 1)

    def loc(off):
        idx = bisect.bisect_right(starts, off) - 1
        st = starts[idx]
        en = text.find("\n", st)
        if en < 0:
            en = len(text)
        return idx + 1, text[st:en]

    hits = {}
    comment_masked, _ = mask_html_comments(text)
    markup = html_markup_mask(text)
    _, document_strings, _ = lex_source(comment_masked, True)
    tags = [tm for tm in TAGSPAN.finditer(markup)
            if not tag_is_js_literal(tm.start(), comment_masked, document_strings)]
    document_like = bool(tags)

    # Absolute special-scheme and WebRTC URLs remain conservative anywhere in source. Grammar-
    # sensitive network-path references are added only by a fetching HTML/CSS/JS context below.
    for m in ABS.finditer(text):
        hits[m.start()] = 1
    for m in STUN.finditer(text):
        hits[m.start(1)] = 1

    # A standalone source file is scanned as JS/CSS. Once real markup is present, body prose is not
    # executable; scan only script/style bodies and event/style attributes so an HTML example like
    # `<p>fetch("//docs")</p>` cannot impersonate code.
    if not document_like:
        scan_js(comment_masked, None, hits)
        scan_css(comment_masked, None, hits)
    # Scan raw script/style bodies independently too. Prose outside the element may contain quotes
    # meaningful to neither language; it must not be able to extend a heuristic JS/CSS literal mask
    # across the element and hide a real request. `range` is an O(1) identity-to-source offset map.
    for raw_tag, opening, body_start, body_end in rawtext_blocks(comment_masked):
        if tag_is_js_literal(opening, comment_masked, document_strings):
            continue
        body = comment_masked[body_start:body_end]
        body_map = range(body_start, body_end)
        if raw_tag == "script":
            scan_js(body, body_map, hits)
        elif raw_tag == "style":
            scan_css(body, body_map, hits)

    ns = []
    for tm in tags:
        tag = tm.group(1).lower()
        by_name = {}
        for am in ATTR.finditer(tm.group(2)):
            name = am.group(1).lower()
            gi = next((g for g in (2, 3, 4) if am.group(g) is not None), None)
            if gi is None:
                continue
            base = tm.start(2) + am.start(gi)
            raw_value = text[base:base + len(am.group(gi))]
            value, value_map = decode_html_attr_once(raw_value, base)
            if name not in by_name:                 # HTML duplicate-attribute semantics: first wins
                by_name[name] = (value, value_map)

            if name == "xmlns" or name.startswith("xmlns:"):
                ns.append((base, base + len(raw_value)))
                continue
            if name in FETCH_ATTRS and not (name == "data" and tag != "object"):
                add_value_hits(value, value_map, hits, name in {"srcset", "imagesrcset", "ping"})
            elif name == "srcdoc" and tag == "iframe":
                scan_srcdoc(value, value_map, hits)
            elif name == "style":
                scan_css(value, value_map, hits)
            elif name.startswith("on"):
                scan_js(value, value_map, hits)

        # Meta refresh fetches its decoded `content` URL. Decode/scan only after confirming the
        # tag's first `http-equiv` attribute is actually refresh.
        if tag == "meta" and "http-equiv" in by_name and "content" in by_name:
            if by_name["http-equiv"][0].strip().lower() == "refresh":
                content, content_map = by_name["content"]
                url = re.search(r'(?i)\burl\s*=', content)
                if url:
                    add_value_hits(content[url.end():], content_map[url.end():], hits)

    def in_ns(off):
        return any(a <= off < b for a, b in ns)

    for off in sorted(hits):
        ln, body = loc(off)
        verdict, cls = ("NSURI ", "benign") if in_ns(off) else \
                       (("WAIVED", "waived") if WAIVER.search(body) else ("EGRESS", "violations"))
        if cls == "benign":
            benign += 1
        elif cls == "waived":
            waived += 1
        else:
            violations += 1
        print("%s %s:%d:%s" % (verdict, sanp(path), ln, CTRL.sub("?", body)))

# counts go to a SEPARATE trusted file, never in-band with (attacker-influenced) finding text.
with open(os.environ["SCAN_EGRESS_COUNTS"], "w") as cf:
    cf.write("%d %d %d\n" % (violations, waived, benign))
PY
  sc_rc=$?
  if [ "$sc_rc" -ne 0 ]; then
    echo "scan-egress: text-scan interpreter error (rc=$sc_rc) — FAIL CLOSED" >&2
    sed 's/^/  py: /' "$sc_err" >&2 || true
    rm -f "$sc_in" "$sc_out" "$sc_err" "$sc_cnt"
    exit 1
  fi
  cat "$sc_out"                                     # findings: display-only, control bytes sanitized
  # Fold in the counts from the trusted side channel, validating the WHOLE file (not just line 1) as
  # one canonical record. Anything a faulting producer could emit — a leading-zero/octal field, an
  # overflowed field, a NUL, an extra line, an unterminated line — is rejected and FAILS CLOSED, so
  # arbitrary/fault bytes can never zero the gate into a false PASS.
  if ! counts_line="$(validate_counts_file "$sc_cnt")"; then
    echo "scan-egress: counts channel invalid — FAIL CLOSED" >&2
    rm -f "$sc_in" "$sc_out" "$sc_err" "$sc_cnt"
    exit 1
  fi
  set -f
  # shellcheck disable=SC2086  # counts_line is three validated canonical integers
  set -- $counts_line
  set +f
  violations=$((violations + $1))
  waived=$((waived + $2))
  benign=$((benign + $3))
  rm -f "$sc_in" "$sc_out" "$sc_err" "$sc_cnt"
fi

# Symlinks break self-containment: the referenced bytes live outside the shipped tree. Both the path
# and the readlink target are untrusted → sanitized so a crafted name can't forge terminal output.
for s in ${symlinks[@]+"${symlinks[@]}"}; do
  violations=$((violations + 1))
  echo "SYMLINK $(san_path "$s") -> $(san_path "$(readlink "$s" 2>/dev/null || echo '?')") (breaks self-containment)"
done

# Non-regular files can't be scanned (and reading a FIFO would hang) — fail closed.
for sp in ${specials[@]+"${specials[@]}"}; do
  violations=$((violations + 1))
  echo "SPECIAL $(san_path "$sp") (non-regular file: FIFO/socket/device — unscannable, fail closed)"
done

# Unreadable regular files: we never saw the bytes, so no glob waiver may launder them — fail closed.
for u in ${unreadable[@]+"${unreadable[@]}"}; do
  violations=$((violations + 1))
  echo "UNREADABLE $(san_path "$u") (regular file not readable — cannot certify, fail closed)"
done

# A traversal error (an unreadable directory) means the walk was incomplete; a clean sibling can't
# certify what we couldn't reach — fail the whole tree closed.
if [ "$traversal_err" -ne 0 ]; then
  violations=$((violations + 1))
  echo "TRAVERSAL (find could not fully walk a target directory — incomplete enumeration, fail closed)"
fi

# Binaries: `grep -a` their strings for ABSOLUTE-scheme URLs. Three outcomes, kept distinct so a
# read error can never be laundered into a waiver:
#   grep rc>=2 (unreadable / grep error) -> fail closed, NEVER waived
#   a hit                                 -> fail ALWAYS (a --allow-binary glob must not launder a live URL)
#   no hit                               -> waivable with --allow-binary <glob>, else fail as uncertifiable
is_waived_binary() {  # <path>
  local b="$1" pat
  for pat in ${allow[@]+"${allow[@]}"}; do
    # shellcheck disable=SC2053  # intentional glob match of the path against the waiver pattern
    [[ "$b" == $pat ]] && return 0
  done
  return 1
}
waived_bin=0
review_bin=0
for b in ${binaries[@]+"${binaries[@]}"}; do
  raw="$(LC_ALL=C grep -aoiE -- "$EGRESS_BIN" "$b" 2>/dev/null)"; grc=$?
  if [ "$grc" -ge 2 ]; then
    violations=$((violations + 1)); echo "UNREADABLE(binary) $(san_path "$b") (grep error rc=$grc — cannot certify, fail closed)"
  elif [ -n "$raw" ]; then
    # both the path and the grep-extracted string come from untrusted bytes -> sanitize both.
    hits="$(printf '%s' "$raw" | head -5 | tr '\n' ' ')"
    hits="$(san_path "$hits")"
    violations=$((violations + 1)); echo "EGRESS(binary) $(san_path "$b") :: $hits"
  elif is_waived_binary "$b"; then
    waived_bin=$((waived_bin + 1)); echo "WAIVED-BINARY $(san_path "$b")"
  else
    review_bin=$((review_bin + 1))
    violations=$((violations + 1))
    echo "UNSCANNED(binary) $(san_path "$b") (static scan cannot certify; --allow-binary <glob> to waive a reviewed asset)"
  fi
done

echo "--- scan-egress: $violations un-waived, $waived waived, $benign non-fetching URI(s), ${#files[@]} text file(s), ${#symlinks[@]} symlink(s), ${#specials[@]} special, ${#unreadable[@]} unreadable, $review_bin binary fail(s), $waived_bin binary waived ---"
if [ "$violations" -ne 0 ]; then
  echo "scan-egress: FAIL — un-waived external reference(s), symlink(s), non-regular/unreadable file(s), traversal error, or binary file(s)" >&2
  exit 1
fi
echo "scan-egress: PASS — every file scanned clean or explicitly waived"
exit 0
