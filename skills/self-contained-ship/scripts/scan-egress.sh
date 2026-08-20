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
EGRESS_BIN='(https?|wss?|ftp):[/\\]*[^/\\?#[:space:][:cntrl:]]|(^|[^a-z])(stun|turns?):[a-z0-9]'

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
import re, os, bisect, html, hashlib, stat

paths = [p for p in open(os.environ["SCAN_EGRESS_FILELIST"], "rb").read().split(b"\0") if p]

# Filled by the read-only prepass after every parser helper is defined. Classic scripts in one HTML
# document share a global lexical environment, and loose .js inputs in one scanned deliverable
# have no provable load order. One ambiguous document binding therefore disables createElement
# identity narrowing throughout that scanned tree. It can only make the static result more
# conservative; it never suppresses a finding.
TREE_DOCUMENT_AMBIGUOUS = False

# Waiver: a BOUNDED, case-sensitive, TRAILING comment on the hit's own line. The delimiter must sit
# at line-start or after whitespace, so a URL-internal `//` can't act as the comment delimiter.
WAIVER = re.compile(r'(?:^|[ \t])(?:#|//|/\*)[ \t]*egress-ok(?:[ \t]*\*/)?[ \t]*$')

# URL recognition is separated from grammar recognition. A grammar matcher identifies the literal
# value a browser consumes; this routine then applies WHATWG-style authority rules to that value.
# In particular, 3+ slash forms, mixed slash/backslash forms, userinfo, and a percent-decoded host
# are external. A percent-decoded forbidden host byte (e.g. `%2f`) is invalid, not an authority.
# Every matcher returns the URL's EXPLICIT start offset — no fixed-width `m.end()-N` arithmetic.
ABS = re.compile(r'(?ai)(?:https?|wss?|ftp):(?P<slashes>[/\\]*)')
STUN = re.compile(r'(?ai)(?:^|[^a-z])(stun|turns?):[a-z0-9\[]')
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


def normalize_url_input(value, mapping=None):
    # The URL parser removes ASCII TAB, LF, and CR anywhere, then trims leading/trailing C0 controls
    # and space before scheme parsing. Preserve the origin of every surviving character so a
    # normalized hit still points at the exact source byte after entity/literal decoding.
    out = []
    origins = []
    for index, char in enumerate(value):
        if char in "\t\n\r":
            continue
        out.append(char)
        origins.append(index if mapping is None else mapping[index])
    left = 0
    right = len(out)
    while left < right and ord(out[left]) <= 0x20:
        left += 1
    while right > left and ord(out[right - 1]) <= 0x20:
        right -= 1
    return "".join(out[left:right]), origins[left:right]


def external_offsets(value, allow_multiple=False):
    # data:/blob: are local targets. Their payload/origin text can itself contain `https://`, but
    # that spelling is not a second request by the call consuming the outer URL. Executable literal
    # data documents are parsed separately at the HTML sink that instantiates them.
    normalized, origins = normalize_url_input(value)
    if re.match(r'(?ai)^\s*(?:data|blob):', normalized):
        return []
    found = {}
    absolute_slashes = []
    for m in ABS.finditer(normalized):
        if not network_start_allowed(normalized, m.start(), allow_multiple):
            continue
        if valid_authority(normalized, m.end("slashes")):
            found[origins[m.start()]] = 1
            absolute_slashes.append((m.start("slashes"), m.end("slashes")))
    for m in STUN.finditer(normalized):
        if network_start_allowed(normalized, m.start(1), allow_multiple):
            found[origins[m.start(1)]] = 1
    for m in SLASH_RUN.finditer(normalized):
        # Do not double-report the slash run belonging to an absolute special-scheme URL.
        if any(a <= m.start() < b for a, b in absolute_slashes):
            continue
        if m.start() > 0 and normalized[m.start() - 1] == ":":
            continue
        if not network_start_allowed(normalized, m.start(), allow_multiple):
            continue
        if valid_authority(normalized, m.end()):
            found[origins[m.start()]] = 1
    return sorted(found)

# HTML/SVG fetching attributes are TAG-BOUNDED: an attribute only fetches inside a real `<tag ...>`
# span. A tiny start-tag tokenizer, rather than a quote-anywhere regex, tracks when a quote can
# actually open an attribute value (only after `=`). That mirrors browser recovery for stray quote
# and `<` bytes in attribute names/unquoted values, while still keeping a quoted `>` inside the tag
# and treating an unclosed quoted tag as extending through EOF. A bare `src=`/`data=` in plain JS is
# a variable, not markup. `data` fetches ONLY on <object>; elsewhere it is inert markup.


HTML_SPACE = " \t\n\f\r"
JS_UNICODE_LINE_SEPARATORS = tuple(chr(codepoint) for codepoint in (0x2028, 0x2029))
JS_UTF8_LINE_SEPARATORS = tuple(
    character.encode("utf-8").decode("latin-1")
    for character in JS_UNICODE_LINE_SEPARATORS
)
JS_UNICODE_WHITESPACE = tuple(chr(codepoint) for codepoint in (
    0x00a0, 0x1680,
    0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005,
    0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
    0x202f, 0x205f, 0x3000, 0xfeff,
))
JS_UTF8_WHITESPACE = tuple(
    character.encode("utf-8").decode("latin-1")
    for character in JS_UNICODE_WHITESPACE
)
DECODED_WAIVER_BARRIERS = set()


def js_line_terminator_width(source, index):
    """Width in the Latin-1 byte snapshot of an ECMAScript LineTerminatorSequence."""
    if index < 0 or index >= len(source):
        return 0
    if source[index] == "\r":
        return 2 if index + 1 < len(source) and source[index + 1] == "\n" else 1
    if source[index] == "\n":
        return 1
    if source[index] in JS_UNICODE_LINE_SEPARATORS:
        return 1
    if any(source.startswith(separator, index) for separator in JS_UTF8_LINE_SEPARATORS):
        return 3
    return 0


def next_js_line_terminator(source, start=0):
    candidates = [
        source.find("\r", start),
        source.find("\n", start),
        *(source.find(separator, start) for separator in JS_UNICODE_LINE_SEPARATORS),
        *(source.find(separator, start) for separator in JS_UTF8_LINE_SEPARATORS),
    ]
    candidates = [offset for offset in candidates if offset >= 0]
    return min(candidates) if candidates else len(source)


def has_js_line_terminator(source):
    return next_js_line_terminator(source) < len(source)


def html_tag_tail_end(source, cursor):
    state = "before-name"
    quote = None
    while cursor < len(source):
        char = source[cursor]
        if state == "quoted":
            if char == quote:
                state = "before-name"
            cursor += 1
            continue
        if char == ">":
            return cursor + 1
        if state == "before-name":
            if char in HTML_SPACE or char == "/":
                cursor += 1
                continue
            state = "name"
            cursor += 1
            continue
        if state == "name":
            if char == "=":
                state = "before-value"
            elif char in HTML_SPACE:
                state = "after-name"
            cursor += 1
            continue
        if state == "after-name":
            if char in HTML_SPACE:
                cursor += 1
                continue
            if char == "=":
                state = "before-value"
            else:
                state = "name"
            cursor += 1
            continue
        if state == "before-value":
            if char in HTML_SPACE:
                cursor += 1
                continue
            if char in "\"'":
                quote = char
                state = "quoted"
            else:
                state = "unquoted"
            cursor += 1
            continue
        if state == "unquoted":
            if char in HTML_SPACE:
                state = "before-name"
            cursor += 1
    return None


class TagToken:
    def __init__(self, source, start, name_end, attrs_end, end):
        self.source = source
        self._start = start
        self._name_end = name_end
        self._attrs_end = attrs_end
        self._end = end

    def group(self, index=0):
        if index == 0:
            return self.source[self._start:self._end]
        if index == 1:
            return self.source[self._start + 1:self._name_end]
        if index == 2:
            return self.source[self._name_end:self._attrs_end]
        raise IndexError(index)

    def start(self, index=0):
        if index == 0:
            return self._start
        if index == 1:
            return self._start + 1
        if index == 2:
            return self._name_end
        raise IndexError(index)

    def end(self, index=0):
        if index == 0:
            return self._end
        if index == 1:
            return self._name_end
        if index == 2:
            return self._attrs_end
        raise IndexError(index)

    def span(self, index=0):
        return self.start(index), self.end(index)


class TagPattern:
    @staticmethod
    def finditer(source):
        pos = 0
        size = len(source)
        while pos < size:
            opened = source.find("<", pos)
            if opened < 0:
                return
            name_start = opened + 1
            if name_start >= size or not source[name_start].isalpha() or ord(source[name_start]) > 127:
                pos = opened + 1
                continue
            name_end = name_start + 1
            while (name_end < size and ord(source[name_end]) < 128 and
                   (source[name_end].isalnum() or source[name_end] in ":-")):
                name_end += 1

            end = html_tag_tail_end(source, name_end)
            if end is None:
                yield TagToken(source, opened, name_end, size, size)
                return
            yield TagToken(source, opened, name_end, end - 1, end)
            pos = end


TAGSPAN = TagPattern()
ATTR = re.compile(r'(?is)(?<![\w:.-])([a-z_:][\w:.-]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'>]+))')
FETCH_ATTRS = {
    "imagesrcset", "srcset", "src", "xlink:href", "href", "formaction", "action",
    "poster", "background", "cite", "ping", "manifest", "data"
}
SET_ATTRS = FETCH_ATTRS - {"data", "manifest"}
XLINK_NAMESPACE = "http://www.w3.org/1999/xlink"

# A genuine namespace such as `<svg xmlns="http://www.w3.org/2000/svg">` is an identifier, not a
# fetch. Only a parsed `xmlns`/`xmlns:*` attribute receives that suppression in the loop below.
CTRL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')     # body sanitizer (keeps tab; body is single-line)
PATHCTRL = re.compile(r'[\x00-\x1f\x7f]')          # path sanitizer: strip ALL controls incl NUL/LF/tab


def sanp(p):                                       # an untrusted path must not forge terminal output
    return PATHCTRL.sub("?", p)


def mask_range(chars, start, end):
    for i in range(start, min(end, len(chars))):
        if chars[i] not in "\r\n":
            chars[i] = " "


def html_comment_end(source, start):
    body = start + 4
    if body < len(source) and source[body] == ">":           # `<!-->` abrupt empty close
        return body + 1
    if source.startswith("->", body):                       # `<!--->`, same recovery
        return body + 2
    normal = source.find("-->", body)
    end_bang = source.find("--!>", body)
    candidates = [(normal + 3) if normal >= 0 else None,
                  (end_bang + 4) if end_bang >= 0 else None]
    closed = [candidate for candidate in candidates if candidate is not None]
    return min(closed) if closed else len(source)


def rawtext_close(source, tag, start):
    # In raw-text/RCDATA states, a matching name followed by whitespace, `/`, or `>` becomes an end
    # tag. Attributes are a parse error but still close; quoted `>` bytes do not end the token early.
    close_rx = re.compile(r'(?is)</' + re.escape(tag) + r'(?=[\t\n\f\r />])')
    candidate = close_rx.search(source, start)
    if not candidate:
        return None
    end = html_tag_tail_end(source, candidate.end())
    if end is None:
        return None

    class RawClose:
        def start(self):
            return candidate.start()

        def end(self):
            return end

    return RawClose()


def html_regions(source):
    # Resolve outer HTML comments and raw-text elements in source order. A comment wins when it opens
    # first, so `<script>` text inside a comment is inert; once a real raw-text element opens, `<!--`
    # in its JS/CSS body belongs to that language and cannot hide its closing tag or later markup.
    comments = []
    raw_blocks = []
    tag_tokens = list(TAGSPAN.finditer(source))
    tag_ranges = [match.span() for match in tag_tokens]

    def inside_tag(offset):
        return any(start < offset < end for start, end in tag_ranges)

    def next_comment(start):
        candidate = source.find("<!--", start)
        while candidate >= 0 and inside_tag(candidate):
            candidate = source.find("<!--", candidate + 4)
        return candidate

    def next_rawtext(start):
        return next((candidate for candidate in tag_tokens
                     if candidate.start() >= start and
                     candidate.group(1).lower() in {"script", "style", "title", "textarea"}),
                    None)

    pos = 0
    while True:
        opened = next_rawtext(pos)
        comment_start = next_comment(pos)
        if comment_start >= 0 and (not opened or comment_start < opened.start()):
            end = html_comment_end(source, comment_start)
            comments.append((comment_start, end))
            pos = max(end, comment_start + 4)
            continue
        if not opened:
            break
        tag = opened.group(1).lower()
        closed = rawtext_close(source, tag, opened.end())
        body_end = closed.start() if closed else len(source)
        raw_blocks.append((tag, opened.start(), opened.end(), body_end))
        if not closed:
            break
        pos = closed.end()
    return comments, raw_blocks


def mask_html_comments(source):
    chars = list(source)
    comments, _ = html_regions(source)
    for start, end in comments:
        mask_range(chars, start, end)
    return "".join(chars), comments


def rawtext_blocks(source):
    _, blocks = html_regions(source)
    for block in blocks:
        yield block


def html_markup_mask(source):
    # HTML comments and raw-text/RCDATA element bodies are not markup. Mask them without changing
    # length/newline positions so a tag-shaped JS string or escaped example cannot become a tag.
    chars = list(source)
    comments, blocks = html_regions(source)
    for start, end in comments:
        mask_range(chars, start, end)
    for _, _, body_start, body_end in blocks:
        mask_range(chars, body_start, body_end)
    return "".join(chars)


ENTITY = re.compile(r'&(?:#[xX][0-9a-fA-F]+;?|#[0-9]+;?|[a-zA-Z][a-zA-Z0-9]+;)')

# HTML's numeric-reference end state remaps only these C1 values through Windows-1252. Other C0
# controls (for example `&#1;`) survive as their code point despite being parse errors; Python's
# html.unescape drops them, which could incorrectly join two local-looking fragments into `https`
# or `//` and create a false finding.
HTML_NUMERIC_REPLACEMENTS = {
    0x80: 0x20ac, 0x82: 0x201a, 0x83: 0x0192, 0x84: 0x201e, 0x85: 0x2026,
    0x86: 0x2020, 0x87: 0x2021, 0x88: 0x02c6, 0x89: 0x2030, 0x8a: 0x0160,
    0x8b: 0x2039, 0x8c: 0x0152, 0x8e: 0x017d, 0x91: 0x2018, 0x92: 0x2019,
    0x93: 0x201c, 0x94: 0x201d, 0x95: 0x2022, 0x96: 0x2013, 0x97: 0x2014,
    0x98: 0x02dc, 0x99: 0x2122, 0x9a: 0x0161, 0x9b: 0x203a, 0x9c: 0x0153,
    0x9e: 0x017e, 0x9f: 0x0178,
}


def decode_html_entity(token):
    if not token.startswith("&#"):
        return html.unescape(token)
    digits = token[2:-1] if token.endswith(";") else token[2:]
    base = 10
    if digits[:1].lower() == "x":
        base = 16
        digits = digits[1:]
    codepoint = int(digits, base)
    if codepoint == 0 or codepoint > 0x10ffff or 0xd800 <= codepoint <= 0xdfff:
        codepoint = 0xfffd
    codepoint = HTML_NUMERIC_REPLACEMENTS.get(codepoint, codepoint)
    return chr(codepoint)


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
            decoded = decode_html_entity(token)
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


def record_decoded_line_barriers(source, mapping, grammar):
    """Bind decoded JS/CSS line boundaries to their ultimate raw source offsets."""
    if mapping is None:
        return
    if grammar == "js":
        cursor = 0
        while cursor < len(source):
            terminator = next_js_line_terminator(source, cursor)
            if terminator >= len(source):
                break
            raw = map_offset(mapping, terminator)
            if raw is not None:
                DECODED_WAIVER_BARRIERS.add(raw)
            cursor = terminator + js_line_terminator_width(source, terminator)
        return
    if grammar == "css":
        for offset, character in enumerate(source):
            if character not in "\r\n\f":
                continue
            raw = map_offset(mapping, offset)
            if raw is not None:
                DECODED_WAIVER_BARRIERS.add(raw)


def add_value_hits(value, mapping, hits, allow_multiple=False):
    for off in external_offsets(value, allow_multiple):
        raw = map_offset(mapping, off)
        if raw is not None:
            hits[raw] = 1


def decode_data_payload_once(raw, mapping):
    # A data URL percent-decodes once before its media-type consumer parses the bytes. Preserve a
    # map to the `%` source byte so nested findings still land on the original artifact line.
    out = []
    out_map = []
    i = 0
    while i < len(raw):
        if (raw[i] == "%" and i + 2 < len(raw) and
                re.match(r'^[0-9a-fA-F]{2}$', raw[i + 1:i + 3])):
            out.append(chr(int(raw[i + 1:i + 3], 16)))
            out_map.append(mapping[i])
            i += 3
            continue
        out.append(raw[i])
        out_map.append(mapping[i])
        i += 1
    return "".join(out), out_map


MAX_EXECUTABLE_DATA_PAYLOAD = 1024 * 1024
JAVASCRIPT_MIME_ESSENCES = {
    "application/ecmascript", "application/javascript", "application/x-ecmascript",
    "application/x-javascript", "text/ecmascript", "text/javascript", "text/javascript1.0",
    "text/javascript1.1", "text/javascript1.2", "text/javascript1.3", "text/javascript1.4",
    "text/javascript1.5", "text/jscript", "text/livescript", "text/x-ecmascript",
    "text/x-javascript",
}


def scan_data_payload(value, mapping, hits, depth, grammar):
    if depth > 8:
        raise RuntimeError("data URL nesting exceeds scanner safety bound")
    value, mapping = normalize_url_input(value, mapping)
    match = re.match(r'(?is)^\s*data:([^,]*),(.*)$', value)
    if not match:
        return
    metadata = match.group(1)
    mime = metadata.split(";", 1)[0].strip().lower() or "text/plain"
    html_mime = mime in {"text/html", "application/xhtml+xml", "image/svg+xml"}
    js_mime = mime in JAVASCRIPT_MIME_ESSENCES
    css_mime = mime == "text/css"
    # External classic scripts deliberately ignore the response MIME essence for historical web
    # compatibility. Keep that sink distinct from module/import/worker JavaScript, whose existing
    # MIME contract remains strict.
    if not ((grammar == "html" and html_mime) or
            (grammar == "classic-js") or
            (grammar == "js" and js_mime) or
            (grammar == "css" and css_mime)):
        return
    # Static recovery of a base64 executable payload has no faithful byte-to-source map. Treat that
    # unsupported executable form as a finding at the outer target instead of certifying it clean.
    if re.search(r'(?ai)(?:^|;)base64(?:;|$)', metadata):
        raw = map_offset(mapping, match.start())
        if raw is not None:
            hits[raw] = 1
        return
    # The data-URL processor serializes with `exclude fragment=true`: a literal fragment is not a
    # response-body byte, while a literal query remains body and can execute. Percent-encoded `%23`
    # is not a delimiter and decodes only after this split.
    raw_payload = match.group(2)
    delimiter = raw_payload.find("#")
    if delimiter >= 0:
        raw_payload = raw_payload[:delimiter]
    payload_end = match.start(2) + len(raw_payload)
    payload_map = mapping[match.start(2):payload_end]
    # Bound the recursive parser's byte surface. Percent encoding can consume at most three source
    # bytes per decoded byte, so an encoded body above 3x the limit is necessarily oversized; the
    # second check catches large unencoded/mixed bodies after their one decoding pass.
    if len(raw_payload) > MAX_EXECUTABLE_DATA_PAYLOAD * 3:
        raw = map_offset(mapping, match.start())
        if raw is not None:
            hits[raw] = 1
        return
    payload, decoded_map = decode_data_payload_once(raw_payload, payload_map)
    if len(payload) > MAX_EXECUTABLE_DATA_PAYLOAD:
        raw = map_offset(mapping, match.start())
        if raw is not None:
            hits[raw] = 1
        return
    if grammar == "html":
        scan_srcdoc(payload, decoded_map, hits, depth + 1)
    elif grammar in {"js", "classic-js"}:
        scan_js(payload, decoded_map, hits, depth + 1)
    elif grammar == "css":
        scan_css(payload, decoded_map, hits, depth + 1)


def scan_javascript_url(value, mapping, hits, depth):
    if depth > 8:
        raise RuntimeError("javascript URL nesting exceeds scanner safety bound")
    value, mapping = normalize_url_input(value, mapping)
    match = re.match(r'(?is)^javascript:(.*)$', value)
    if not match:
        return
    encoded = match.group(1)
    if len(encoded) > MAX_EXECUTABLE_DATA_PAYLOAD * 3:
        raw = map_offset(mapping, match.start())
        if raw is not None:
            hits[raw] = 1
        return
    encoded_map = mapping[match.start(1):match.end(1)]
    script, script_map = decode_data_payload_once(encoded, encoded_map)
    if len(script) > MAX_EXECUTABLE_DATA_PAYLOAD:
        raw = map_offset(mapping, match.start())
        if raw is not None:
            hits[raw] = 1
        return
    scan_js(script, script_map, hits, depth + 1)


def script_element_kind(attributes):
    # HTML determines the script kind from the first `type` attribute, or the obsolete `language`
    # attribute only when `type` is absent. Unsupported values are data blocks and do not fetch a
    # `src`; module scripts retain strict response-MIME checking.
    if "type" in attributes:
        type_string = attributes["type"].strip().lower()
    elif attributes.get("language", "").strip():
        type_string = "text/" + attributes["language"].strip().lower()
    else:
        type_string = ""
    # The HTML `type` attribute uses JavaScript MIME *essence match* as an exact string concept:
    # unlike a response Content-Type, parameters are significant and make this a data block.
    if not type_string or type_string in JAVASCRIPT_MIME_ESSENCES:
        return "classic"
    if type_string == "module":
        return "module"
    if type_string == "importmap":
        return "importmap"
    if type_string == "speculationrules":
        return "speculationrules"
    return "data"


def first_tag_attribute_values(source, mapping, tag_match, wanted):
    # Read the start-tag token itself so valueless first attributes still participate in HTML's
    # first-duplicate-wins rule. `ATTR` intentionally recognizes only valued fetching attributes;
    # using it here would let a later `type=module` override an earlier bare `type`.
    values = {}
    cursor = tag_match.start(2)
    end = tag_match.end(2)
    while cursor < end:
        while cursor < end and source[cursor] in HTML_SPACE + "/":
            cursor += 1
        if cursor >= end:
            break
        name_start = cursor
        while cursor < end and source[cursor] not in HTML_SPACE + "/=":
            cursor += 1
        name = source[name_start:cursor].lower()
        while cursor < end and source[cursor] in HTML_SPACE:
            cursor += 1
        raw_start = cursor
        raw_end = cursor
        if cursor < end and source[cursor] == "=":
            cursor += 1
            while cursor < end and source[cursor] in HTML_SPACE:
                cursor += 1
            if cursor < end and source[cursor] in "\"'":
                quote = source[cursor]
                cursor += 1
                raw_start = cursor
                while cursor < end and source[cursor] != quote:
                    cursor += 1
                raw_end = cursor
                if cursor < end:
                    cursor += 1
            else:
                raw_start = cursor
                while cursor < end and source[cursor] not in HTML_SPACE:
                    cursor += 1
                raw_end = cursor
        if name not in wanted or name in values:
            continue
        raw = source[raw_start:raw_end]
        origin = raw_start if mapping is None else mapping[raw_start:raw_end]
        values[name] = decode_html_attr_once(raw, origin)[0]
    return values


def scan_executable_data_url(tag, name, value, mapping, hits, depth, link_rel="",
                             script_kind="classic"):
    # data:/blob: targets are not egress by themselves. A literal data document can nevertheless
    # instantiate a second parser at a browser sink. Navigation targets parse HTML; script sources
    # parse JS; stylesheet links parse CSS. Blob bytes are not present in the URL, so the code that
    # constructs them remains visible to the ordinary JS scanner instead.
    grammars = []
    navigation = ((tag in {"iframe", "frame", "object", "embed"} and name in {"src", "data"}) or
            (tag in {"a", "area"} and name == "href") or
            (tag == "form" and name == "action") or
            (tag in {"button", "input"} and name == "formaction"))
    if navigation:
        grammars.append("html")
    elif tag == "script" and name == "src":
        if script_kind == "classic":
            grammars.append("classic-js")
        elif script_kind == "module":
            grammars.append("js")
    elif tag == "link" and name == "href":
        rel_tokens = {
            token.lower() for token in re.split(r'[ \t\n\f\r]+', link_rel) if token
        }
        if "modulepreload" in rel_tokens:
            grammars.append("js")
        if "stylesheet" in rel_tokens:
            grammars.append("css")
    for grammar in grammars:
        scan_data_payload(value, mapping, hits, depth, grammar)
    if navigation:
        scan_javascript_url(value, mapping, hits, depth)


def raw_script_element_context(source, mapping, tag_start):
    # Raw-text discovery carries the opening tag's exact offset. Re-read that tag's first `type` /
    # `language` attributes and src presence so an inline data block, or ignored child text on an
    # external classic/module script, is not parsed as executable JavaScript.
    for tag_match in TAGSPAN.finditer(source):
        if tag_match.start() != tag_start:
            continue
        context = first_tag_attribute_values(
            source, mapping, tag_match, {"type", "language", "src"})
        return script_element_kind(context), "src" in context
    return "classic", False  # recovery ambiguity fails closed to executable


def lex_source(source, line_comments):
    # Produce an offset-preserving CODE mask plus literal spans. Comments and literal bodies become
    # spaces (newlines retained). Grammar regexes operate only on CODE; a matched API then consumes
    # its adjacent literal from the original span. This prevents comments/ordinary strings from
    # impersonating executable fetch grammar without losing the URL inside a real argument.
    chars = list(source)
    spans = []
    opaque = []
    ambiguities = []
    n = len(source)

    # The stable on-disk snapshot is Latin-1 decoded so one character always equals one source
    # byte, while HTML/entity recursion can supply already-decoded Unicode characters. Normalize
    # both views of ECMAScript Unicode whitespace to offset-preserving CODE spaces/newlines;
    # literal values continue to read the untouched source and retain their exact source map.
    if line_comments:
        def normalize_sequence(sequence, first):
            cursor = source.find(sequence)
            while cursor >= 0:
                chars[cursor] = first
                for offset in range(1, len(sequence)):
                    chars[cursor + offset] = " "
                cursor = source.find(sequence, cursor + len(sequence))

        for whitespace in JS_UNICODE_WHITESPACE + JS_UTF8_WHITESPACE:
            normalize_sequence(whitespace, " ")
        for terminator in JS_UNICODE_LINE_SEPARATORS + JS_UTF8_LINE_SEPARATORS:
            normalize_sequence(terminator, "\n")

    def add_opaque(start, end):
        opaque.append((start, end))
        mask_range(chars, start, end)

    def next_line_terminator(start):
        """Return the first ECMAScript line terminator at/after start, or EOF."""
        return next_js_line_terminator(source, start)

    def trailing_keyword(text, allowed):
        text = text.rstrip()
        match = re.search(r'[A-Za-z_$][A-Za-z0-9_$]*$', text)
        if not match or match.group(0).lower() not in allowed:
            return False
        before = text[:match.start()].rstrip()
        return not before.endswith(".") and not before.endswith("?.")

    def matching_open(text, opening, closing):
        depth = 0
        for index in range(len(text) - 1, -1, -1):
            if text[index] == closing:
                depth += 1
            elif text[index] == opening:
                depth -= 1
                if depth == 0:
                    return index
        return None

    def control_statement_close(text):
        if not text.endswith(")"):
            return False
        opened = matching_open(text, "(", ")")
        return opened is not None and trailing_keyword(
            text[:opened], {"if", "while", "for", "with", "switch", "catch"}
        )

    def statement_block_close(text):
        if not text.endswith("}"):
            return False
        opened = matching_open(text, "{", "}")
        if opened is None:
            return False
        before = text[:opened].rstrip()
        if not before or before[-1] in ";{}":
            return True
        if trailing_keyword(before, {"else", "do", "try", "finally", "catch"}):
            return True
        if control_statement_close(before):
            return True
        # Match a named function declaration by balancing its final parameter parentheses, rather
        # than a `[^()]*` shortcut that fails on defaults such as `x = g()`. Anonymous/function-
        # valued forms retain the preceding `=` and are not statement boundaries.
        if before.endswith(")"):
            params = matching_open(before, "(", ")")
            head = before[:params].rstrip() if params is not None else ""
            if re.search(
                    r'(?is)(?:^|[;{}])\s*(?:export\s+(?:default\s+)?)?'
                    r'(?:async\s+)?function(?:\s*\*)?\s+'
                    r'[A-Za-z_$][A-Za-z0-9_$]*$', head):
                return True
            if re.search(
                    r'(?is)(?:^|[;{}])\s*export\s+default\s+'
                    r'(?:async\s+)?function(?:\s*\*)?\s*$', head):
                return True
        # A top-level/sequence labeled block is a statement too. Do not accept `{label:` here: that
        # spelling can be an object property whose closing brace remains an expression value.
        if re.search(r'(?is)(?:^|[;}])\s*[A-Za-z_$][A-Za-z0-9_$]*\s*:$', before):
            return True
        declaration_boundary = r'(?:^|[;{}\r\n])\s*'
        decorator_prefix = (
            r'(?:@[A-Za-z_$][A-Za-z0-9_$.]*'
            r'(?:\s*\([^;\r\n]*\))?\s+)*'
        )
        if re.search(
                r'(?s)' + declaration_boundary + decorator_prefix +
                r'(?:export\s+(?:default\s+)?)?(?:declare\s+)?(?:abstract\s+)?'
                r'class\s+[A-Za-z_$][A-Za-z0-9_$]*'
                r'(?:\s*<[^;\r\n]*>)?'
                r'(?:\s+extends\s+[^\r\n]+?)?'
                r'(?:\s+implements\s+[^\r\n]+)?$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary + decorator_prefix +
                r'export\s+default\s+(?:abstract\s+)?class(?:\s+extends\s+.+)?$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary +
                r'(?:export\s+)?(?:declare\s+)?type\s+'
                r'[A-Za-z_$][A-Za-z0-9_$]*(?:\s*<[^;\r\n]*>)?\s*='
                r'[^;\r\n]*$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary +
                r'(?:export\s+(?:default\s+)?)?(?:declare\s+)?interface\s+'
                r'[A-Za-z_$][A-Za-z0-9_$]*(?:\s*<[^;\r\n]*>)?'
                r'(?:\s+extends\s+[^{}\r\n]+)?$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary +
                r'(?:export\s+)?(?:declare\s+)?(?:const\s+)?enum\s+'
                r'[A-Za-z_$][A-Za-z0-9_$.]*$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary +
                r'(?:export\s+)?(?:declare\s+)?namespace\s+'
                r'[A-Za-z_$][A-Za-z0-9_$.]*$', before):
            return True
        if re.search(
                r'(?s)' + declaration_boundary +
                r'(?:declare\s+module(?:\s+[A-Za-z_$][A-Za-z0-9_$.]*)?'
                r'|(?:export\s+)?module\s+[A-Za-z_$][A-Za-z0-9_$.]*'
                r'|declare\s+global)$', before):
            return True
        return False

    def typescript_declaration_tail(text):
        """Return True/False for a proved goal, or None when a multiline tail is uncertain."""
        candidates = list(re.finditer(
            r'(?is)(?:^|[;{}\r\n])\s*(?P<head>'
            r'(?:(?:export|declare)\s+)*type\b|'
            r'declare\s+(?:const|let|var|function)\b)', text))
        if not candidates:
            return False
        statement = text[candidates[-1].start("head"):].strip()
        # A full TypeScript type parser is outside this static rung. Do not guess where a
        # semicolon-free multiline declaration ends: mark its following slash as lexical
        # uncertainty so it fails closed instead of choosing a mask that can hide live code.
        if re.search(r'[\r\n]', statement):
            return None
        stack = []
        semicolons = []
        pairs = {")": "(", "]": "[", "}": "{"}
        for offset, char in enumerate(statement):
            if char in "([{":
                stack.append(char)
            elif char in ")]}":
                if not stack or stack[-1] != pairs[char]:
                    return False
                stack.pop()
            elif char == ";" and not stack:
                semicolons.append(offset)
        if stack:
            return False
        end = len(statement)
        if semicolons and not statement[semicolons[-1] + 1:].strip():
            end = semicolons.pop()
        start = semicolons[-1] + 1 if semicolons else 0
        if statement[start:end].strip() != statement[:end].strip():
            return False
        statement = statement[:end].strip()
        return bool(
            re.match(
                r'(?s)^(?:(?:export|declare)\s+)*type\s+'
                r'[A-Za-z_$][A-Za-z0-9_$]*(?:\s*<.*>)?\s*=.+$', statement) or
            re.match(r'(?s)^declare\s+(?:const|let|var|function)\b.+$', statement)
        )

    def regex_allowed(pos, floor):
        # ECMAScript's lexical goal depends on the preceding token. This small tokenizer only needs
        # the conservative expression-start boundary: after an operator/delimiter or a keyword that
        # requires an expression, `/` begins a regex; after a value/close-delimiter it is division.
        prior = "".join(chars[floor:pos]).rstrip()
        if not prior:
            return True
        # Import/export declarations terminate before a following line's expression even though the
        # module specifier literal is blanked in CODE. Likewise `export {x}` closes with `}` but is not
        # a statement block. Recognize only a line-terminator-separated declaration tail.
        previous_spans = [span for span in spans if span["end"] <= pos]
        if previous_spans:
            previous = max(previous_spans, key=lambda span: span["end"])
            if has_js_line_terminator(source[previous["end"]:pos]):
                before_literal = "".join(chars[floor:previous["start"]]).rstrip()
                if (re.search(r'(?is)(?:^|[;\r\n])\s*(?:import|export)\b[^;\r\n]*\bfrom$',
                              before_literal) or
                        re.search(r'(?is)(?:^|[;\r\n])\s*import\s*$', before_literal)):
                    return True
        if has_js_line_terminator(source[floor:pos]) and re.search(
                r'(?is)(?:^|[;\r\n])\s*export\s*\{[^{}]*\}\s*$', prior):
            return True
        if prior.endswith("++") or prior.endswith("--"):
            return False
        if prior.endswith("..."):
            return True
        if prior[-1] in "([{,:;=!?&|+-*/%^~<>":
            return True
        if has_js_line_terminator(source[floor:pos]):
            typescript_goal = typescript_declaration_tail(prior)
            if typescript_goal is not False:
                return typescript_goal
        if control_statement_close(prior) or statement_block_close(prior):
            return True
        return trailing_keyword(prior, {
            "return", "throw", "yield", "await", "case", "delete", "void", "typeof",
            "instanceof", "in", "of", "new", "else", "do", "default", "extends", "break",
            "continue", "debugger",
        })

    def regex_end(start):
        i = start + 1
        in_class = False
        while i < n:
            ch = source[i]
            if js_line_terminator_width(source, i):
                return None
            if ch == "\\":
                i = min(n, i + 2)
                continue
            if ch == "[":
                in_class = True
            elif ch == "]" and in_class:
                in_class = False
            elif ch == "/" and not in_class:
                i += 1
                while i < n and (source[i].isalnum() or source[i] in "_$"):
                    i += 1
                return i
            i += 1
        return None

    def string_end(start, quote):
        i = start + 1
        while i < n:
            if source[i] == "\\":
                if line_comments:
                    width = js_line_terminator_width(source, i + 1)
                    if width:
                        i += 1 + width
                        continue
                if i + 1 < n and source[i + 1] == "\r":
                    i += 3 if i + 2 < n and source[i + 2] == "\n" else 2
                    continue
                if i + 1 < n and source[i + 1] in "\n\f":
                    i += 2
                    continue
                i = min(n, i + 2)
                continue
            if source[i] == quote:
                return i + 1
            # An unescaped line break terminates an ordinary JS string and is CSS bad-string
            # recovery. Keeping the following bytes visible prevents the malformed prefix from
            # laundering an active statement/declaration later on the next line.
            if ((line_comments and js_line_terminator_width(source, i)) or
                    (not line_comments and source[i] in "\r\n\f")):
                return i
            i += 1
        return n

    def add_literal(start, end):
        content_end = end - 1 if end <= n and end > start and source[end - 1] == source[start] else end
        spans.append({"start": start, "content": start + 1, "content_end": content_end, "end": end,
                      "value": source[start + 1:content_end], "js": line_comments,
                      "quote": source[start]})
        add_opaque(start, end)

    def parse_template(start):
        i = start + 1
        quasi_start = start
        has_expression = False
        while i < n:
            if source[i] == "\\":
                width = js_line_terminator_width(source, i + 1)
                if width:
                    i += 1 + width
                    continue
                i = min(n, i + 2)
                continue
            if source[i] == "`":
                end = i + 1
                if not has_expression:
                    add_literal(start, end)          # static template: valid literal call argument
                else:
                    spans.append({"start": start, "content": start + 1, "content_end": end - 1,
                                  "end": end, "value": source[start + 1:end - 1], "dynamic": True,
                                  "js": True, "quote": "`"})
                    add_opaque(quasi_start, end)     # final quasi and closing backtick only
                return end
            if source.startswith("${", i):
                has_expression = True
                add_opaque(quasi_start, i + 2)       # raw quasi + `${`; expression stays executable
                close = parse_code(i + 2, True, i + 2)
                if close >= n:
                    return n
                add_opaque(close, close + 1)         # closing `}` is template punctuation
                i = close + 1
                quasi_start = i
                continue
            i += 1
        add_opaque(quasi_start, n)
        return n

    def parse_code(start, stop_on_brace=False, floor=0):
        i = start
        depth = 0
        while i < n:
            if stop_on_brace and source[i] == "}":
                if depth == 0:
                    return i
                depth -= 1
                i += 1
                continue
            if stop_on_brace and source[i] == "{":
                depth += 1
                i += 1
                continue
            if line_comments and source.startswith("<!--", i):
                end = next_line_terminator(i)
                add_opaque(i, end)
                i = end
                continue
            if source.startswith("/*", i):
                end = source.find("*/", i + 2)
                end = n if end < 0 else end + 2
                add_opaque(i, end)
                i = end
                continue
            if line_comments and source.startswith("//", i):
                end = next_line_terminator(i + 2)
                add_opaque(i, end)
                i = end
                continue
            if source[i] in "\"'":
                end = string_end(i, source[i])
                add_literal(i, end)
                i = end
                continue
            if source[i] == "`" and line_comments:
                i = parse_template(i)
                continue
            if line_comments and source[i] == "/":
                regex_goal = regex_allowed(i, floor)
                if regex_goal is None:
                    ambiguities.append(i)
                if regex_goal is not False:
                    end = regex_end(i)
                    if end is not None:
                        add_opaque(i, end)
                        i = end
                        continue
            i += 1
        return n

    parse_code(0, False, 0)
    spans.sort(key=lambda span: span["start"])
    opaque.sort()
    return "".join(chars), spans, {"opaque": opaque, "ambiguities": ambiguities}


def decode_javascript_literal(value, mapping):
    # Decode the statically knowable StringLiteral/TemplateLiteral escape forms before handing a
    # URL to its runtime API. Each output character maps to the escape's source backslash. Unknown
    # identity escapes drop the backslash as JavaScript string literals do; malformed/truncated
    # numeric escapes are kept literal rather than guessed.
    simple = {"b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t", "v": "\v"}
    out = []
    origins = []
    index = 0
    size = len(value)
    while index < size:
        if value[index] != "\\":
            out.append(value[index])
            origins.append(mapping[index])
            index += 1
            continue
        origin = mapping[index]
        if index + 1 >= size:
            out.append("\\")
            origins.append(origin)
            index += 1
            continue
        escaped = value[index + 1]
        line_width = js_line_terminator_width(value, index + 1)
        if line_width:
            index += 1 + line_width
            continue
        if escaped == "x" and index + 3 < size and re.match(r'^[0-9a-fA-F]{2}$', value[index + 2:index + 4]):
            out.append(chr(int(value[index + 2:index + 4], 16)))
            origins.append(origin)
            index += 4
            continue
        if escaped == "u":
            if index + 2 < size and value[index + 2] == "{":
                close = value.find("}", index + 3)
                digits = value[index + 3:close] if close >= 0 else ""
                if digits and len(digits) <= 6 and re.match(r'^[0-9a-fA-F]+$', digits):
                    codepoint = int(digits, 16)
                    if codepoint <= 0x10ffff:
                        out.append(chr(codepoint))
                        origins.append(origin)
                        index = close + 1
                        continue
            elif index + 5 < size and re.match(r'^[0-9a-fA-F]{4}$', value[index + 2:index + 6]):
                out.append(chr(int(value[index + 2:index + 6], 16)))
                origins.append(origin)
                index += 6
                continue
        if escaped in "01234567":
            digits = escaped
            limit = 3 if escaped in "0123" else 2
            cursor = index + 2
            while cursor < size and len(digits) < limit and value[cursor] in "01234567":
                digits += value[cursor]
                cursor += 1
            out.append(chr(int(digits, 8)))
            origins.append(origin)
            index = cursor
            continue
        out.append(simple.get(escaped, escaped))
        origins.append(origin)
        index += 2
    return "".join(out), origins


def decode_css_escapes(value, mapping, allow_line_continuation=True, code_context=False):
    """Decode CSS escapes while mapping each emitted character to its source backslash/byte."""
    out = []
    origins = []
    index = 0
    size = len(value)
    while index < size:
        if value[index] != "\\":
            out.append(value[index])
            origins.append(mapping[index])
            index += 1
            continue
        origin = mapping[index]
        if index + 1 >= size:
            index += 1  # A terminal backslash is a parse error, never a synthetic URL byte.
            continue
        escaped = value[index + 1]
        if escaped in "\r\n\f":
            if allow_line_continuation:
                index += (3 if escaped == "\r" and index + 2 < size and
                          value[index + 2] == "\n" else 2)
                continue
            # Backslash-newline is a continuation only inside a CSS string. It is not a valid
            # identifier escape, so preserve the token boundary in normalized code instead of
            # joining `@im` + `port` or `u` + `rl` into executable grammar.
            out.append("\\")
            origins.append(origin)
            index += 1
            continue
        if escaped in "0123456789abcdefABCDEF":
            cursor = index + 1
            while (cursor < size and cursor < index + 7 and
                   value[cursor] in "0123456789abcdefABCDEF"):
                cursor += 1
            codepoint = int(value[index + 1:cursor], 16)
            if cursor < size and value[cursor] in " \t\n\f\r":
                if value[cursor] == "\r" and cursor + 1 < size and value[cursor + 1] == "\n":
                    cursor += 2
                else:
                    cursor += 1
            emitted = ("\ufffd" if codepoint == 0 or 0xd800 <= codepoint <= 0xdfff or
                       codepoint > 0x10ffff else chr(codepoint))
            # Escapes are code points inside a CSS name token; an escaped space, slash, colon,
            # quote, parenthesis, etc. must never become structural grammar after normalization.
            if (code_context and not (emitted.isalnum() or emitted in "_-" or
                                      ord(emitted) >= 0x80)):
                emitted = "\ufffd"
            out.append(emitted)
            origins.append(origin)
            index = cursor
            continue
        emitted = escaped
        if (code_context and not (emitted.isalnum() or emitted in "_-" or
                                  ord(emitted) >= 0x80)):
            emitted = "\ufffd"
        out.append(emitted)
        origins.append(origin)
        index += 2
    return "".join(out), origins


def javascript_identifier_pattern(word):
    # ECMAScript permits Unicode escapes inside IdentifierName tokens. Match the exact ASCII API
    # spelling or an equivalent four-digit/code-point escape for each character; callers retain
    # their normal identifier boundary checks, so this does not turn arbitrary text into grammar.
    parts = []
    for char in word:
        digits = format(ord(char), "x")
        digits_pattern = "".join(
            "[" + digit.lower() + digit.upper() + "]" if digit.isalpha() else digit
            for digit in digits)
        four_digits_pattern = "".join(
            "[" + digit.lower() + digit.upper() + "]" if digit.isalpha() else digit
            for digit in format(ord(char), "04x"))
        brace_zeros = 6 - len(digits)
        parts.append(
            r'(?:' + re.escape(char) + r'|\\u(?:' + four_digits_pattern +
            r'|\{0{0,' + str(brace_zeros) + r'}' + digits_pattern + r'\}))'
        )
    return "".join(parts)


JS_IDENTIFIER_ESCAPE = re.compile(r'(?i)\\u(?:([0-9a-f]{4})|\{([0-9a-f]{1,6})\})')


def decode_javascript_identifier(value):
    def replace(match):
        codepoint = int(match.group(1) or match.group(2), 16)
        return chr(codepoint) if codepoint <= 0x10ffff else match.group(0)
    return JS_IDENTIFIER_ESCAPE.sub(replace, value)


def span_runtime_value(span, mapping):
    origins = []
    for rel in range(len(span["value"])):
        raw = map_offset(mapping, span["content"] + rel)
        if raw is None:
            return span["value"], []
        origins.append(raw)
    if span.get("js"):
        return decode_javascript_literal(span["value"], origins)
    return decode_css_escapes(span["value"], origins)


def in_ranges(pos, ranges):
    return any(a <= pos < b for a, b in ranges)


def local_uri_ranges(source):
    # Suppress an absolute spelling only when it is bytes INSIDE a literal data:/blob: target. The
    # outer URL is local; executable data payloads are independently parsed at their HTML sink.
    ranges = []
    _, spans, _ = lex_source(source, True)
    for span in spans:
        value, value_map = span_runtime_value(span, None)
        value, _ = normalize_url_input(value, value_map)
        if re.match(r'(?ai)^\s*(?:data|blob):', value):
            ranges.append((span["content"], span["content_end"]))
    markup = html_markup_mask(source)
    for tm in TAGSPAN.finditer(markup):
        for am in ATTR.finditer(tm.group(2)):
            gi = next((group for group in (2, 3, 4) if am.group(group) is not None), None)
            if gi is None:
                continue
            base = tm.start(2) + am.start(gi)
            raw_value = source[base:base + len(am.group(gi))]
            value, value_map = decode_html_attr_once(raw_value, base)
            value, _ = normalize_url_input(value, value_map)
            if re.match(r'(?ai)^\s*(?:data|blob):', value):
                ranges.append((base, base + len(raw_value)))
    for match in re.finditer(r'(?is)\burl\s*\(\s*((?:data|blob):[^\s)]*)', source):
        ranges.append((match.start(1), match.end(1)))
    return ranges


def network_literal_context(source):
    # Absolute spellings are policy findings even in ordinary literals, but a special-scheme token
    # embedded later in a same-origin value (`/assets/https:logo.svg`) is path text, not a new URL.
    # Return every value range plus only the source offsets that are URL-candidate starts.
    ranges = []
    allowed = set()

    def add_value(value, start, mapping=None, cover=None):
        ranges.append(cover or ((start, start + len(value)) if mapping is None else
                                (min(mapping), max(mapping) + 1) if mapping else (start, start)))
        for rel in external_offsets(value):
            if ABS.match(value, rel) or re.match(r'(?ai)(?:stun|turns?):', value[rel:]):
                allowed.add(start + rel if mapping is None else mapping[rel])

    _, spans, _ = lex_source(source, True)
    for span in spans:
        value, value_map = span_runtime_value(span, None)
        add_value(value, span["content"], value_map, (span["content"], span["content_end"]))

    markup = html_markup_mask(source)
    for tm in TAGSPAN.finditer(markup):
        for am in ATTR.finditer(tm.group(2)):
            gi = next((group for group in (2, 3, 4) if am.group(group) is not None), None)
            if gi is None:
                continue
            base = tm.start(2) + am.start(gi)
            raw_value = source[base:base + len(am.group(gi))]
            value, value_map = decode_html_attr_once(raw_value, base)
            add_value(value, base, value_map, (base, base + len(raw_value)))

    # Unquoted CSS url() tokens are not JS/HTML literals, but still form one consumed URL value.
    for match in re.finditer(r'(?is)\burl\s*\(\s*([^\s"\')][^\s)]*)', source):
        add_value(match.group(1), match.start(1))
    return ranges, allowed


def grouped_literal_end(mask, start, span, limit=None):
    """Return the byte after a literal and its balanced neutral grouping, or None."""
    limit = len(mask) if limit is None else limit
    prefix = "".join(mask[start:span["start"]].split())
    if any(char != "(" for char in prefix):
        return None

    cursor = span["end"]
    for _ in prefix:
        while cursor < limit and mask[cursor].isspace():
            cursor += 1
        if cursor >= limit or mask[cursor] != ")":
            return None
        cursor += 1
    return cursor


def literal_has_only_grouping(mask, start, span, end=None):
    """Accept one literal wrapped only in balanced, semantically neutral parentheses."""
    cursor = grouped_literal_end(mask, start, span, end)
    if cursor is None:
        return False
    return end is None or not mask[cursor:end].strip()


def next_literal(mask, spans, pos, limit=None):
    limit = len(mask) if limit is None else limit
    for span in spans:
        if span["start"] < pos:
            continue
        if span["start"] >= limit or span["end"] > limit:
            return None
        if grouped_literal_end(mask, pos, span, limit) is None:
            return None
        return span
    return None


def literal_segment(mask, spans, start, end):
    inside = [s for s in spans if start <= s["start"] and s["end"] <= end]
    dynamic = [span for span in inside if span.get("dynamic")]
    if dynamic:
        span = min(dynamic, key=lambda item: (item["start"], -item["end"]))
        if literal_has_only_grouping(mask, start, span, end):
            return span
    if len(inside) != 1:
        return None
    span = inside[0]
    if not literal_has_only_grouping(mask, start, span, end):
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
    value, value_map = span_runtime_value(span, mapping)
    for rel in external_offsets(value, allow_multiple):
        raw = map_offset(value_map, rel)
        if raw is not None:
            hits[raw] = 1


def scan_span_data(span, mapping, hits, depth, grammar):
    value, value_map = span_runtime_value(span, mapping)
    if value_map:
        scan_data_payload(value, value_map, hits, depth, grammar)


def scan_span_javascript_url(span, mapping, hits, depth):
    value, value_map = span_runtime_value(span, mapping)
    if value_map:
        scan_javascript_url(value, value_map, hits, depth)


def worker_data_grammar(args, code, spans, mapping):
    # Worker/SharedWorker default to classic scripts. Recognize a statically certain final
    # `{type: "module"}` option as module-strict; unknown/computed options remain classic for a
    # fail-closed advisory result rather than attempting general object/data-flow evaluation.
    if len(args) < 2:
        return "classic-js"
    start, end, _ = args[1]
    left = start
    right = end
    while left < right and code[left].isspace():
        left += 1
    while right > left and code[right - 1].isspace():
        right -= 1

    # Parentheses around the whole options object do not change its value. Unwrap only when the
    # opening parenthesis matches the final non-space byte; comma/conditional expressions remain
    # unknown and therefore retain the conservative classic-worker policy.
    while left < right and code[left] == "(":
        nesting = 0
        matched = None
        for cursor in range(left, right):
            if code[cursor] == "(":
                nesting += 1
            elif code[cursor] == ")":
                nesting -= 1
                if nesting == 0:
                    matched = cursor
                    break
        if matched != right - 1:
            break
        left += 1
        right -= 1
        while left < right and code[left].isspace():
            left += 1
        while right > left and code[right - 1].isspace():
            right -= 1
    if right - left < 2 or code[left] != "{" or code[right - 1] != "}":
        return "classic-js"

    brace_depth = 0
    object_close = None
    for cursor in range(left, right):
        if code[cursor] == "{":
            brace_depth += 1
        elif code[cursor] == "}":
            brace_depth -= 1
            if brace_depth == 0:
                object_close = cursor
                break
    if object_close != right - 1:
        return "classic-js"

    # Split only the outer object's top-level properties. String bodies/comments are already blank
    # in `code`, so commas and braces inside them cannot counterfeit a boundary.
    properties = []
    prop_start = left + 1
    nesting = 0
    for cursor in range(left + 1, right - 1):
        char = code[cursor]
        if char in "([{":
            nesting += 1
        elif char in ")]}":
            if nesting:
                nesting -= 1
        elif char == "," and nesting == 0:
            properties.append((prop_start, cursor))
            prop_start = cursor + 1
    properties.append((prop_start, right - 1))

    def static_property_key(cursor, prop_end):
        key_span = next_literal(code, spans, cursor, prop_end)
        if key_span and not code[cursor:key_span["start"]].strip():
            return (span_runtime_value(key_span, mapping)[0],
                    key_span["end"])
        while cursor < prop_end and code[cursor].isspace():
            cursor += 1
        identifier = re.match(
            r'(?:[A-Za-z_$]|\\u(?:[0-9a-fA-F]{4}|\{[0-9a-fA-F]{1,6}\}))'
            r'(?:[A-Za-z0-9_$]|\\u(?:[0-9a-fA-F]{4}|\{[0-9a-fA-F]{1,6}\}))*',
            code[cursor:prop_end])
        if not identifier:
            return None, cursor
        return (decode_javascript_identifier(identifier.group(0)),
                cursor + identifier.end())

    # `None` means absent or statically unknown. A later explicit property overrides an earlier
    # spread/computed/accessor property exactly as object-literal evaluation does.
    type_value = None
    for prop_start, prop_end in properties:
        visible = code[prop_start:prop_end]
        if not visible.strip():
            continue
        if visible.lstrip().startswith(("...", "[")):
            type_value = None
            continue

        accessor = re.match(r'(?i)\s*(?:get|set)\b', visible)
        if accessor:
            key, _ = static_property_key(prop_start + accessor.end(), prop_end)
            if key in {None, "type"}:
                type_value = None
            continue

        key, after_key = static_property_key(prop_start, prop_end)
        while after_key < prop_end and code[after_key].isspace():
            after_key += 1
        colon = after_key if after_key < prop_end and code[after_key] == ":" else None

        if key != "type":
            continue
        if colon is None:
            type_value = None
            continue
        value_span = literal_segment(code, spans, colon + 1, prop_end)
        if not value_span:
            type_value = None
            continue
        type_value = span_runtime_value(value_span, mapping)[0]

    return "js" if type_value == "module" else "classic-js"


def javascript_document_ambiguous(code):
    """Return true unless every visible document token is provably a direct global receiver."""
    identifier_start = r'(?<![A-Za-z0-9_$])'
    group_open = r'(?:\(\s*)*'
    group_close = r'(?:\s*\))*'
    document_identifier = javascript_identifier_pattern("document")
    with_identifier = javascript_identifier_pattern("with")
    eval_identifier = javascript_identifier_pattern("eval")
    if (re.search(identifier_start + with_identifier + r'\s*\(', code) or
            re.search(identifier_start + group_open + eval_identifier + group_close +
                      r'\s*\(', code)):
        return True
    for token in re.finditer(
            identifier_start + document_identifier + r'(?![A-Za-z0-9_$])', code):
        before = token.start() - 1
        while before >= 0 and code[before].isspace():
            before -= 1
        after = token.end()
        while after < len(code) and code[after].isspace():
            after += 1
        # A member suffix such as fake.document is not the global Document. Any non-receiver use
        # is a possible declaration, parameter, destructuring/import/loop binding, shorthand
        # property, alias, or bare value. Both revoke the optimization instead of enumerating syntax.
        if ((before >= 0 and code[before] in ".#") or
                after >= len(code) or code[after] not in ".["):
            return True
    return False


def scan_js(source, mapping, hits, depth=0):
    if depth > 8:
        raise RuntimeError("JavaScript data URL nesting exceeds scanner safety bound")
    record_decoded_line_barriers(source, mapping, "js")
    code, spans, lexical = lex_source(source, True)
    for ambiguity in lexical["ambiguities"]:
        raw = map_offset(mapping, ambiguity)
        if raw is not None:
            hits[raw] = "uncertain"

    def identifiers(*names):
        return r'(?:' + "|".join(javascript_identifier_pattern(name) for name in names) + r')'

    identifier_start = r'(?<![A-Za-z0-9_$])'
    plain_identifier = r'[A-Za-z_$][A-Za-z0-9_$]*'
    group_open = r'(?:\(\s*)*'
    group_close = r'(?:\s*\))*'

    def namespace_argument_value(argument):
        """Classify the nullable namespace argument without executing JavaScript."""
        start, end, span = argument
        if span:
            if span.get("dynamic"):
                return None
            return span_runtime_value(span, mapping)[0]
        return "" if code[start:end].strip() == "null" else None

    def namespace_argument_kind(argument):
        value = namespace_argument_value(argument)
        if value is None:
            return "unknown"
        return "null" if value == "" else "non-null"

    def static_call_arguments(args, expected):
        """Require exact arity and arguments whose evaluation cannot run attacker code."""
        if len(args) != expected:
            return False
        for start, end, span in args:
            if span:
                if span.get("dynamic"):
                    return False
                continue
            if code[start:end].strip() not in {"null", "true", "false"}:
                return False
        return True

    def expression_ends_at(cursor):
        """Prove an expression ends here, including a narrow identifier-led ASI boundary."""
        saw_line_terminator = False
        while cursor < len(code) and code[cursor].isspace():
            saw_line_terminator = saw_line_terminator or code[cursor] in "\r\n"
            cursor += 1
        if cursor >= len(code) or code[cursor] in ";}":
            return True
        if saw_line_terminator:
            following = re.match(r'[A-Za-z_$][A-Za-z0-9_$]*', code[cursor:])
            if following and following.group(0) not in {"in", "instanceof", "of"}:
                return True
            if code[cursor] in "\"'`":
                return True
        return False

    def assigned_literal(position):
        """Return a literal only when it is the complete assignment RHS, not a leading operand."""
        span = next_literal(code, spans, position)
        if not span or span.get("dynamic"):
            return None
        cursor = grouped_literal_end(code, position, span)
        if cursor is None:
            return None
        return span if expression_ends_at(cursor) else None

    def brace_depth(position):
        return code[:position].count("{") - code[:position].count("}")

    # Bounded direct-object tracking for elements created in this source. Identity/state is granted
    # only across a contiguous flat chain of whitelisted direct statements; every alias, shadow,
    # reassignment, control-flow construct, unrelated call, or other token ends the proof interval.
    script_events = {}
    script_binding_depths = {}
    script_creation_ends = {}
    non_script_bindings = {}
    known_image_bindings = {}
    binding_counts = {}
    immediate_script_ends = []
    document_identifier = identifiers("document")
    create_script = re.compile(
        r'(?<![A-Za-z0-9_$\.#])(?P<document>' + document_identifier +
        r')\s*\.\s*' + identifiers("createElement") + r'\s*\('
    )
    created_candidates = list(create_script.finditer(code))
    # `document.createElement` is authoritative only when every visible `document` token is a
    # direct receiver and none is a member suffix. A declaration, parameter, destructuring target,
    # import, loop binding, shorthand property, or bare value necessarily leaves the token followed
    # by something other than `.` / `[`, so this token rule covers all binding grammar without an
    # open-ended list of declaration regexes. `with`/direct `eval` disables the proof outright, and
    # the prepass propagates classic-global ambiguity across scripts/files before any narrowing.
    document_is_ambiguous = (
        TREE_DOCUMENT_AMBIGUOUS or javascript_document_ambiguous(code)
    )
    if document_is_ambiguous:
        created_candidates = []
    for created in created_candidates:
        args, close = call_args(code, spans, created.end() - 1)
        if (close is None or not args or not args[0][2] or
                args[0][2].get("dynamic")):
            continue
        element_name = span_runtime_value(args[0][2], mapping)[0].strip().lower()
        binding = re.search(
            r'(?:^|[;{}\r\n])\s*(?P<declaration>const|let|var)\s+(?P<name>' +
            plain_identifier + r')\s*=\s*$', code[:created.start()]
        )
        # A prefix call does not define the binding's element identity. `&&`, comma/conditional
        # tails, member/call continuations, and similar operators can replace the runtime value.
        if (binding and (binding.group("declaration") != "const" or
                         not expression_ends_at(close + 1))):
            binding = None
        if binding:
            name = binding.group("name")
            binding_counts[name] = binding_counts.get(name, 0) + 1
        element_creation_end = close + 1
        if element_name != "script":
            if binding:
                non_script_bindings.setdefault(
                    binding.group("name"),
                    (element_creation_end, brace_depth(created.start())))
                if element_name == "img" and binding.group("declaration") == "const":
                    known_image_bindings.setdefault(
                        binding.group("name"),
                        (element_creation_end, brace_depth(created.start())))
            continue
        creation_end = element_creation_end
        immediate_script_ends.append(creation_end)
        append_child = re.search(
            r'\.\s*' + identifiers("appendChild") + r'\s*\(\s*$',
            code[:created.start()])
        if append_child:
            append_close = re.match(r'\s*\)', code[creation_end:])
            if append_close:
                immediate_script_ends.append(creation_end + append_close.end())
        if binding:
            name = binding.group("name")
            script_binding_depths.setdefault(name, brace_depth(created.start()))
            script_creation_ends.setdefault(name, creation_end)
            script_events.setdefault(name, [])

    def record_script_event(object_name, event_start, event_end, kind):
        # Only a same-block, statement-leading, fully static mutation joins the local proof chain.
        # Unknown/nested/conditional syntax remains visible between creation and the eventual sink,
        # which makes the use fall back to the conservative grammar union.
        origin_depth = script_binding_depths.get(object_name)
        boundary = max(code.rfind(";", 0, event_start),
                       code.rfind("{", 0, event_start),
                       code.rfind("}", 0, event_start))
        creation_end = script_creation_ends.get(object_name)
        creation_gap = (code[creation_end:event_start]
                        if creation_end is not None and creation_end <= event_start else "")
        asi_after_creation = (any(char in "\r\n" for char in creation_gap) and
                              not creation_gap.strip())
        if (kind == "unknown" or event_end is None or origin_depth is None or
                brace_depth(event_start) != origin_depth or
                (code[boundary + 1:event_start].strip() and not asi_after_creation)):
            return
        script_events.setdefault(object_name, []).append((event_start, event_end, kind))

    direct_type = re.compile(
        r'(?<![A-Za-z0-9_$])' + group_open + r'(?P<object>' + plain_identifier +
        r')' + group_close + r'\s*\.\s*' + identifiers("type") + r'\s*='
    )
    for assignment in direct_type.finditer(code):
        if assignment.group("object") not in script_events:
            continue
        span = assigned_literal(assignment.end())
        kind = (script_element_kind({"type": span_runtime_value(span, mapping)[0]})
                if span else "unknown")
        event_end = grouped_literal_end(code, assignment.end(), span) if span else None
        record_script_event(
            assignment.group("object"), assignment.start(), event_end, kind)

    type_setter = re.compile(
        r'(?<![A-Za-z0-9_$])' + group_open + r'(?P<object>' + plain_identifier +
        r')' + group_close + r'\s*(?:\.|\?\.)\s*(?P<setter>' +
        identifiers("setAttribute", "setAttributeNS") + r')\s*(?:\?\.\s*)?\('
    )
    for setter_match in type_setter.finditer(code):
        if setter_match.group("object") not in script_events:
            continue
        args, call_close = call_args(code, spans, setter_match.end() - 1)
        setter_name = decode_javascript_identifier(setter_match.group("setter")).lower()
        expected_args = 3 if setter_name == "setattributens" else 2
        if not static_call_arguments(args, expected_args):
            continue
        namespace_kind = "null"
        if setter_name == "setattributens" and args:
            namespace_kind = namespace_argument_kind(args[0])
            if namespace_kind == "non-null":
                record_script_event(
                    setter_match.group("object"), setter_match.start(),
                    call_close + 1 if call_close is not None else None, "preserve")
                continue
        name_i, value_i = (1, 2) if setter_name == "setattributens" else (0, 1)
        if len(args) <= value_i or not args[name_i][2]:
            continue
        name_span = args[name_i][2]
        if name_span.get("dynamic"):
            record_script_event(
                setter_match.group("object"), setter_match.start(),
                call_close + 1 if call_close is not None else None, "unknown")
            continue
        attribute_name = span_runtime_value(name_span, mapping)[0]
        if ((setter_name == "setattributens" and attribute_name != "type") or
                (setter_name == "setattribute" and attribute_name.lower() != "type")):
            record_script_event(
                setter_match.group("object"), setter_match.start(),
                call_close + 1 if call_close is not None else None, "preserve")
            continue
        kind = "unknown"
        if namespace_kind == "unknown":
            kind = "unknown"
        elif args[value_i][2] and not args[value_i][2].get("dynamic"):
            kind = script_element_kind(
                {"type": span_runtime_value(args[value_i][2], mapping)[0]})
        record_script_event(
            setter_match.group("object"), setter_match.start(),
            call_close + 1 if call_close is not None else None, kind)

    bracket_type = re.compile(
        r'(?<![A-Za-z0-9_$])' + group_open + r'(?P<object>' + plain_identifier +
        r')' + group_close + r'\s*(?:\?\.\s*)?\['
    )
    for bracket_match in bracket_type.finditer(code):
        if bracket_match.group("object") not in script_events:
            continue
        close = code.find("]", bracket_match.end())
        if close < 0:
            continue
        name_span = literal_segment(code, spans, bracket_match.end(), close)
        if not name_span:
            continue
        if name_span.get("dynamic"):
            record_script_event(
                bracket_match.group("object"), bracket_match.start(), None, "unknown")
            continue
        member_name = span_runtime_value(name_span, mapping)[0]
        if member_name == "type":
            tail = re.match(r'\s*=', code[close + 1:])
            if not tail:
                continue
            value_span = assigned_literal(close + 1 + tail.end())
            kind = (script_element_kind(
                {"type": span_runtime_value(value_span, mapping)[0]})
                if value_span else "unknown")
            event_end = (grouped_literal_end(
                code, close + 1 + tail.end(), value_span) if value_span else None)
            record_script_event(
                bracket_match.group("object"), bracket_match.start(), event_end, kind)
            continue
        if member_name not in {"setAttribute", "setAttributeNS", "removeAttribute",
                               "removeAttributeNS", "toggleAttribute"}:
            continue
        call_tail = re.match(group_close + r'\s*(?:\?\.\s*)?\(', code[close + 1:])
        if not call_tail:
            continue
        args, call_close = call_args(
            code, spans, close + 1 + call_tail.end() - 1)
        ns_member = member_name in {"setAttributeNS", "removeAttributeNS"}
        expected_args = (3 if member_name == "setAttributeNS" else
                         2 if member_name == "removeAttributeNS" else
                         2 if member_name == "setAttribute" else 1)
        if not static_call_arguments(args, expected_args):
            continue
        namespace_kind = "null"
        if ns_member and args:
            namespace_kind = namespace_argument_kind(args[0])
            if namespace_kind == "non-null":
                record_script_event(
                    bracket_match.group("object"), bracket_match.start(),
                    call_close + 1 if call_close is not None else None, "preserve")
                continue
        name_i = 1 if ns_member else 0
        if len(args) <= name_i or not args[name_i][2]:
            continue
        attribute_span = args[name_i][2]
        if attribute_span.get("dynamic"):
            record_script_event(
                bracket_match.group("object"), bracket_match.start(),
                call_close + 1 if call_close is not None else None, "unknown")
            continue
        attribute_name = span_runtime_value(attribute_span, mapping)[0]
        if ((ns_member and attribute_name != "type") or
                (not ns_member and attribute_name.lower() != "type")):
            record_script_event(
                bracket_match.group("object"), bracket_match.start(),
                call_close + 1 if call_close is not None else None, "preserve")
            continue
        kind = "unknown"
        if namespace_kind == "unknown":
            kind = "unknown"
        elif member_name in {"setAttribute", "setAttributeNS"}:
            value_i = 2 if ns_member else 1
            if (len(args) > value_i and args[value_i][2] and
                    not args[value_i][2].get("dynamic")):
                kind = script_element_kind(
                    {"type": span_runtime_value(args[value_i][2], mapping)[0]})
        else:
            kind = "classic"
        record_script_event(
            bracket_match.group("object"), bracket_match.start(),
            call_close + 1 if call_close is not None else None, kind)

    type_remover = re.compile(
        r'(?<![A-Za-z0-9_$])' + group_open + r'(?P<object>' + plain_identifier +
        r')' + group_close + r'\s*(?:\.|\?\.)\s*(?P<remover>' +
        identifiers("removeAttribute", "removeAttributeNS", "toggleAttribute") +
        r')\s*(?:\?\.\s*)?\('
    )
    for remover_match in type_remover.finditer(code):
        if remover_match.group("object") not in script_events:
            continue
        args, call_close = call_args(code, spans, remover_match.end() - 1)
        remover_name = decode_javascript_identifier(remover_match.group("remover")).lower()
        expected_args = 2 if remover_name == "removeattributens" else 1
        if not static_call_arguments(args, expected_args):
            continue
        namespace_kind = "null"
        if remover_name == "removeattributens" and args:
            namespace_kind = namespace_argument_kind(args[0])
            if namespace_kind == "non-null":
                record_script_event(
                    remover_match.group("object"), remover_match.start(),
                    call_close + 1 if call_close is not None else None, "preserve")
                continue
        name_i = 1 if remover_name == "removeattributens" else 0
        if len(args) <= name_i or not args[name_i][2]:
            continue
        attribute_span = args[name_i][2]
        if attribute_span.get("dynamic"):
            record_script_event(
                remover_match.group("object"), remover_match.start(),
                call_close + 1 if call_close is not None else None, "unknown")
            continue
        attribute_name = span_runtime_value(attribute_span, mapping)[0]
        is_type = (attribute_name == "type" if remover_name == "removeattributens"
                   else attribute_name.lower() == "type")
        if is_type:
            kind = "unknown" if namespace_kind == "unknown" else "classic"
            record_script_event(
                remover_match.group("object"), remover_match.start(),
                call_close + 1 if call_close is not None else None, kind)
        else:
            record_script_event(
                remover_match.group("object"), remover_match.start(),
                call_close + 1 if call_close is not None else None, "preserve")

    for events in script_events.values():
        events.sort()

    def direct_identity_use(binding, receiver_start):
        creation_end, creation_depth = binding
        if (receiver_start < creation_end or
                brace_depth(receiver_start) != creation_depth):
            return False
        return re.fullmatch(r'[\s;]*', code[creation_end:receiver_start]) is not None

    def trusted_script_chain(object_name, receiver_start):
        creation_end = script_creation_ends.get(object_name)
        creation_depth = script_binding_depths.get(object_name)
        if (creation_end is None or creation_depth is None or
                receiver_start < creation_end or
                brace_depth(receiver_start) != creation_depth):
            return None
        cursor = creation_end
        kind = "classic"
        for event_start, event_end, event_kind in script_events.get(object_name, []):
            if event_start >= receiver_start:
                break
            if event_start < cursor or event_end > receiver_start:
                return None
            if re.fullmatch(r'[\s;]*', code[cursor:event_start]) is None:
                return None
            if event_kind != "preserve":
                kind = event_kind
            cursor = event_end
        if re.fullmatch(r'[\s;]*', code[cursor:receiver_start]) is None:
            return None
        return kind

    def tracked_script_kind(member_start):
        receiver_match = re.search(r'(?<![A-Za-z0-9_$\.])' + group_open +
                                   r'(?P<object>' + plain_identifier + r')' +
                                   group_close + r'\s*$',
                                   code[:member_start])
        if receiver_match:
            object_name = receiver_match.group("object")
            if binding_counts.get(object_name, 0) > 1:
                return None
            receiver_start = receiver_match.start()
            image_binding = known_image_bindings.get(object_name)
            if image_binding and direct_identity_use(image_binding, receiver_start):
                return "image"
            non_script_binding = non_script_bindings.get(object_name)
            if (non_script_binding and
                    direct_identity_use(non_script_binding, receiver_start)):
                return "non-script"
            script_kind = trusted_script_chain(object_name, receiver_start)
            if script_kind is not None:
                return script_kind
        for creation_end in reversed(immediate_script_ends):
            if creation_end <= member_start and not code[creation_end:member_start].strip():
                return "classic"
        return None

    def scan_fetching_member(name, span, member_start, allow_multiple=False,
                             script_kind_override=None):
        script_kind = (script_kind_override if name == "src" and script_kind_override else
                       tracked_script_kind(member_start) if name == "src" else None)
        if script_kind == "classic":
            grammars = {"src": ("classic-js",)}
        elif script_kind == "module":
            grammars = {"src": ("js",)}
        elif script_kind == "data":
            grammars = {"src": ()}
        elif script_kind == "image":
            grammars = {"src": ()}
        elif script_kind == "non-script":
            grammars = {"src": ("html", "js")}
        else:
            grammars = {"src": ("html", "js", "classic-js"),
                        "href": ("html", "css"),
                        "action": ("html",), "formaction": ("html",)}
        for grammar in grammars.get(name, ()):
            scan_span_data(span, mapping, hits, depth, grammar)
        if name in {"src", "href", "action", "formaction"}:
            scan_span_javascript_url(span, mapping, hits, depth)
        span_value_hits(span, mapping, hits, allow_multiple)

    api_identifier = identifiers(
        "fetch", "import", "importScripts", "WebSocket", "EventSource", "sendBeacon",
        "Worker", "SharedWorker"
    )
    call = re.compile(
        identifier_start + group_open + r'(?P<api>' + api_identifier +
        r')' + group_close + r'\s*(?:\?\.\s*)?\('
    )
    for m in call.finditer(code):
        args, _ = call_args(code, spans, m.end() - 1)
        if not args:
            continue
        api_name = decode_javascript_identifier(m.group("api")).lower()
        if api_name == "importscripts":
            for _, _, span in args:
                if not span:
                    continue
                scan_span_data(span, mapping, hits, depth, "classic-js")
                span_value_hits(span, mapping, hits)
            continue
        if args[0][2]:
            span = args[0][2]
            if api_name in {"worker", "sharedworker"}:
                scan_span_data(
                    span, mapping, hits, depth,
                    worker_data_grammar(args, code, spans, mapping))
            elif api_name == "import":
                scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)

    # A no-substitution TemplateLiteral can be passed directly as a tag argument. In particular,
    # `fetch`//host`` invokes fetch with a one-element TemplateStringsArray whose string coercion
    # is the external URL. Dynamic templates are deliberately excluded here: their tag argument is
    # an array of quasis rather than the interpolated runtime string and is not a static URL proof.
    tagged_fetch = re.compile(
        identifier_start + group_open + identifiers("fetch") + group_close + r'\s*$'
    )
    for span in spans:
        if span.get("quote") != "`" or span.get("dynamic"):
            continue
        if tagged_fetch.search(code[:span["start"]]):
            span_value_hits(span, mapping, hits)

    for rx, data_grammar in (
        (re.compile(identifier_start + group_open + identifiers("serviceWorker") +
                    group_close + r'\s*(?:\.|\?\.)\s*' + identifiers("register") +
                    group_close + r'\s*(?:\?\.\s*)?\('), None),
        (re.compile(identifier_start + group_open + identifiers("window") + group_close +
                    r'\s*(?:\.|\?\.)\s*' + identifiers("open") + group_close +
                    r'\s*(?:\?\.\s*)?\('), "html"),
        (re.compile(identifier_start + group_open + identifiers("location") + group_close +
                    r'\s*(?:\.|\?\.)\s*' + identifiers("assign", "replace") +
                    group_close + r'\s*(?:\?\.\s*)?\('), "html"),
    ):
        for m in rx.finditer(code):
            args, _ = call_args(code, spans, m.end() - 1)
            if args and args[0][2]:
                span = args[0][2]
                if data_grammar:
                    scan_span_data(span, mapping, hits, depth, data_grammar)
                    scan_span_javascript_url(span, mapping, hits, depth)
                span_value_hits(span, mapping, hits)

    # XHR-like `.open("METHOD", URL)`, while leaving an unrelated one-argument `db.open(URL)` clean.
    for m in re.finditer(r'\.\s*' + identifiers("open") + group_close +
                         r'\s*(?:\?\.\s*)?\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        if len(args) >= 2 and args[0][2] and args[1][2]:
            method = span_runtime_value(args[0][2], mapping)[0].upper()
            if method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}:
                span_value_hits(args[1][2], mapping, hits)

    # Static import/export: comments are blank space in CODE, literals are separate spans. The
    # bounded clause cannot cross `=`, `;`, `(`, `.`, or a string into a distant `from`.
    mod_from = re.compile(r'(?s)\b(?:import|export)\b[\w$*{},\s]*?\bfrom\b')
    for m in mod_from.finditer(code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'\bimport\b', code):
        p = m.end()
        span = next_literal(code, spans, p)
        if span:  # bare side-effect import; import.meta/import(...) contain visible punctuation
            scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)

    # Dot property assignments and location.href/direct location assignments.
    prop = identifiers("srcset", "src", "href", "action", "formaction", "poster",
                       "background", "cite", "ping")
    for m in re.finditer(r'\.\s*(?P<prop>' + prop + r')\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            name = decode_javascript_identifier(m.group("prop"))
            scan_fetching_member(name, span, m.start())
    for m in re.finditer(r'(?<![A-Za-z0-9_$\.])' + identifiers("location") + r'\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "html")
            scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits)
    for m in re.finditer(identifier_start + group_open +
                         identifiers("window", "document", "globalThis", "self", "top", "parent") +
                         group_close + r'\s*\.\s*' +
                         identifiers("location") + r'\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "html")
            scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits)

    # Bracket navigation: location["href"] = URL (including window.location[...]).
    for m in re.finditer(identifier_start + group_open + identifiers("location") +
                         group_close + r'\s*(?:\?\.\s*)?\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name:
            continue
        member_name = span_runtime_value(name, mapping)[0]
        if member_name == "href":
            tail = re.match(r'\s*=', code[close + 1:])
            if tail:
                span = next_literal(code, spans, close + 1 + tail.end())
                if span:
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                    span_value_hits(span, mapping, hits)
        elif member_name in {"assign", "replace"}:
            tail = re.match(group_close + r'\s*(?:\?\.\s*)?\(', code[close + 1:])
            if tail:
                args, _ = call_args(code, spans, close + 1 + tail.end() - 1)
                if args and args[0][2]:
                    span = args[0][2]
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                    span_value_hits(span, mapping, hits)

    # Bracketed global APIs/properties: globalThis["fetch"](URL), navigator["sendBeacon"](URL),
    # window["open"](URL), and window/document["location"] = URL. A property-name literal is
    # grammar, not a URL, but it still receives the same static JavaScript escape decoding.
    for m in re.finditer(identifier_start + group_open +
                         identifiers("window", "document", "globalThis", "navigator", "self",
                                     "top", "parent", "this") +
                         group_close + r'\s*(?:\?\.\s*)?\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name:
            continue
        prop_name = span_runtime_value(name, mapping)[0]
        if prop_name == "location":
            tail = re.match(group_close + r'\s*=', code[close + 1:])
            if tail:
                span = next_literal(code, spans, close + 1 + tail.end())
                if span:
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                    span_value_hits(span, mapping, hits)
            else:
                chained = re.match(group_close + r'\s*(?:\?\.\s*)?\[', code[close + 1:])
                if chained:
                    open2 = close + 1 + chained.end()
                    close2 = code.find("]", open2)
                    member = literal_segment(code, spans, open2, close2) if close2 >= 0 else None
                    assign = re.match(r'\s*=', code[close2 + 1:]) if close2 >= 0 else None
                    member_name = span_runtime_value(member, mapping)[0] if member else ""
                    if member_name == "href" and assign:
                        span = next_literal(code, spans, close2 + 1 + assign.end())
                        if span:
                            scan_span_data(span, mapping, hits, depth, "html")
                            scan_span_javascript_url(span, mapping, hits, depth)
                            span_value_hits(span, mapping, hits)
                    elif member_name in {"assign", "replace"}:
                        call_tail = re.match(
                            group_close + r'\s*(?:\?\.\s*)?\(', code[close2 + 1:])
                        if call_tail:
                            args, _ = call_args(code, spans,
                                                close2 + 1 + call_tail.end() - 1)
                            if args and args[0][2]:
                                span = args[0][2]
                                scan_span_data(span, mapping, hits, depth, "html")
                                scan_span_javascript_url(span, mapping, hits, depth)
                                span_value_hits(span, mapping, hits)
                else:
                    dotted = re.match(
                        r'\s*(?:\.|\?\.)\s*(?P<member>' +
                        identifiers("href", "assign", "replace") + r')', code[close + 1:]
                    )
                    if dotted:
                        member_name = decode_javascript_identifier(dotted.group("member"))
                        member_end = close + 1 + dotted.end()
                        if member_name == "href":
                            assign = re.match(r'\s*=', code[member_end:])
                            if assign:
                                span = next_literal(code, spans, member_end + assign.end())
                                if span:
                                    scan_span_data(span, mapping, hits, depth, "html")
                                    scan_span_javascript_url(span, mapping, hits, depth)
                                    span_value_hits(span, mapping, hits)
                        else:
                            call_tail = re.match(r'\s*\(', code[member_end:])
                            if call_tail:
                                args, _ = call_args(code, spans,
                                                    member_end + call_tail.end() - 1)
                                if args and args[0][2]:
                                    span = args[0][2]
                                    scan_span_data(span, mapping, hits, depth, "html")
                                    scan_span_javascript_url(span, mapping, hits, depth)
                                    span_value_hits(span, mapping, hits)
            continue
        if prop_name == "fetch":
            tagged_span = next((span for span in spans if span["start"] >= close + 1), None)
            if (tagged_span and tagged_span.get("quote") == "`" and
                    not tagged_span.get("dynamic") and
                    re.fullmatch(group_close + r'\s*',
                                 code[close + 1:tagged_span["start"]])):
                span_value_hits(tagged_span, mapping, hits)
                continue
        tail = re.match(group_close + r'\s*(?:\?\.\s*)?\(', code[close + 1:])
        if not tail:
            continue
        if prop_name in {"fetch", "open", "WebSocket", "EventSource", "sendBeacon",
                          "Worker", "SharedWorker", "importScripts"}:
            args, _ = call_args(code, spans, close + 1 + tail.end() - 1)
            api_name = prop_name
            if api_name == "importScripts":
                for _, _, span in args:
                    if not span:
                        continue
                    scan_span_data(span, mapping, hits, depth, "classic-js")
                    span_value_hits(span, mapping, hits)
                continue
            if args and args[0][2]:
                span = args[0][2]
                if api_name == "open":
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                elif api_name in {"Worker", "SharedWorker"}:
                    scan_span_data(
                        span, mapping, hits, depth,
                        worker_data_grammar(args, code, spans, mapping))
                span_value_hits(span, mapping, hits)

    def scan_bracket_script_member(open_pos, content_start, close, script_kind_override=None):
        member = literal_segment(code, spans, content_start, close)
        if not member:
            return
        member_name = span_runtime_value(member, mapping)[0]
        if member_name == "src":
            assign = re.match(r'\s*=', code[close + 1:])
            if assign:
                span = next_literal(code, spans, close + 1 + assign.end())
                if span:
                    scan_fetching_member(
                        "src", span, open_pos,
                        script_kind_override=script_kind_override)
            return
        if member_name not in {"setAttribute", "setAttributeNS"}:
            return
        call_tail = re.match(group_close + r'\s*(?:\?\.\s*)?\(', code[close + 1:])
        if not call_tail:
            return
        args, _ = call_args(code, spans, close + 1 + call_tail.end() - 1)
        namespace_member = member_name == "setAttributeNS"
        namespace_kind = namespace_argument_kind(args[0]) if namespace_member and args else "null"
        name_i, value_i = (1, 2) if namespace_member else (0, 1)
        if len(args) <= value_i or not args[name_i][2] or not args[value_i][2]:
            return
        name = span_runtime_value(args[name_i][2], mapping)[0]
        if namespace_member and namespace_kind == "non-null":
            namespace_value = namespace_argument_value(args[0])
            if namespace_value != XLINK_NAMESPACE or name.rsplit(":", 1)[-1] != "href":
                return
            name = "xlink:href"
        elif (namespace_member and namespace_kind == "unknown" and
              name.rsplit(":", 1)[-1] == "href"):
            name = "xlink:href"
        elif not namespace_member:
            name = name.lower()
        if name in SET_ATTRS:
            scan_fetching_member(
                name, args[value_i][2], open_pos,
                name in {"srcset", "imagesrcset", "ping"},
                script_kind_override)

    # Direct bracket members on tracked script objects: `s["src"] = ...` and
    # `s["setAttribute"]("src", ...)` are semantically identical to their dot spellings.
    for m in re.finditer(identifier_start + group_open +
                         r'(?P<object>' + plain_identifier +
                         r')' + group_close + r'\s*(?:\?\.\s*)?\[', code):
        open_pos = m.end() - 1
        close = code.find("]", m.end())
        if close >= 0:
            scan_bracket_script_member(open_pos, m.end(), close)

    # The same bracket spellings can immediately follow `document.createElement("script")`, before
    # any identifier exists to match in the loop above.
    for creation_end in immediate_script_ends:
        bracket = re.match(group_close + r'\s*\[', code[creation_end:])
        if not bracket:
            continue
        open_pos = creation_end + bracket.end() - 1
        close = code.find("]", open_pos + 1)
        if close >= 0:
            scan_bracket_script_member(open_pos, open_pos + 1, close, "classic")

    # DOM setters: setAttribute(name, value) and setAttributeNS(ns, name, value).
    setter = identifiers("setAttributeNS", "setAttribute")
    for m in re.finditer(r'\.\s*(?P<setter>' + setter + r')' + group_close +
                         r'\s*(?:\?\.\s*)?\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        setter_name = decode_javascript_identifier(m.group("setter")).lower()
        namespace_member = setter_name == "setattributens"
        namespace_kind = namespace_argument_kind(args[0]) if namespace_member and args else "null"
        name_i, value_i = (1, 2) if namespace_member else (0, 1)
        if len(args) <= value_i or not args[name_i][2] or not args[value_i][2]:
            continue
        name = span_runtime_value(args[name_i][2], mapping)[0]
        if namespace_member and namespace_kind == "non-null":
            namespace_value = namespace_argument_value(args[0])
            if namespace_value != XLINK_NAMESPACE or name.rsplit(":", 1)[-1] != "href":
                continue
            name = "xlink:href"
        elif (namespace_member and namespace_kind == "unknown" and
              name.rsplit(":", 1)[-1] == "href"):
            name = "xlink:href"
        elif not namespace_member:
            name = name.lower()
        if name in SET_ATTRS:
            scan_fetching_member(
                name, args[value_i][2], m.start(),
                name in {"srcset", "imagesrcset", "ping"})


def scan_css(source, mapping, hits, depth=0):
    if depth > 8:
        raise RuntimeError("CSS data URL nesting exceeds scanner safety bound")
    record_decoded_line_barriers(source, mapping, "css")
    css_code, spans, _ = lex_source(source, False)
    css_scan_code, css_scan_map = decode_css_escapes(
        css_code, range(len(css_code)), allow_line_continuation=False,
        code_context=True)

    def raw_boundary(decoded_offset):
        return css_scan_map[decoded_offset] if decoded_offset < len(css_scan_map) else len(css_code)

    # CSS names include hyphen and every non-ASCII code point. The decoder also represents an
    # escaped structural code point with a non-ASCII sentinel so it stays inside its name token.
    # A Python `\w` boundary would therefore let `not-url` or `\20url` counterfeit `url()`.
    calls = re.compile(
        r'(?ai)(?<![-_A-Za-z0-9\u0080-\U0010FFFF])'
        r'(?P<fn>url|image-set|image)\s*\('
    )
    for m in calls.finditer(css_scan_code):
        raw_open = css_scan_map[m.end() - 1]
        if re.search(r'(?ai)\bnew\s*$', css_scan_code[:m.start()]):
            continue
        args, close = call_args(css_code, spans, raw_open)
        if close is None:
            continue
        if m.group("fn").lower() == "url":
            start = raw_open + 1
            import_target = bool(re.search(r'(?ai)@import\s*$', css_scan_code[:m.start()]))
            span = literal_segment(css_code, spans, start, close)
            if span:
                if import_target:
                    scan_span_data(span, mapping, hits, depth, "css")
                span_value_hits(span, mapping, hits)
            else:
                left, right = start, close
                while left < right and source[left].isspace():
                    left += 1
                while right > left and source[right - 1].isspace():
                    right -= 1
                raw_map = list(range(left, right)) if mapping is None else list(mapping[left:right])
                decoded_value, decoded_map = decode_css_escapes(
                    source[left:right], raw_map, allow_line_continuation=False)
                if import_target and left < right:
                    scan_data_payload(decoded_value, decoded_map, hits, depth, "css")
                for rel in external_offsets(decoded_value):
                    raw = map_offset(decoded_map, rel)
                    if raw is not None:
                        hits[raw] = 1
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
    for m in re.finditer(r'(?ai)@import\b', css_scan_code):
        span = next_literal(css_code, spans, raw_boundary(m.end()))
        if span:
            scan_span_data(span, mapping, hits, depth, "css")
            span_value_hits(span, mapping, hits)


def scan_processed_script_block(source, mapping, hits, depth, kind):
    # Import maps and speculation rules are JSON-shaped processed script blocks, not inert data
    # blocks. Their literal URL values can feed module fetches or navigations. Decode the same
    # static string forms as JavaScript, scan every URL candidate, and recursively inspect literal
    # data: targets under the grammar used by the consumer.
    record_decoded_line_barriers(source, mapping, "js")
    code, spans, _ = lex_source(source, True)
    grammar = "js" if kind == "importmap" else "html"
    for span in spans:
        cursor = span["end"]
        while cursor < len(code) and code[cursor].isspace():
            cursor += 1
        if cursor < len(code) and code[cursor] == ":":
            continue  # JSON object keys name mappings/rules; only their values can fetch.
        scan_span_data(span, mapping, hits, depth, grammar)
        span_value_hits(span, mapping, hits)


def scan_srcdoc(source, mapping, hits, depth=0):
    # `iframe[srcdoc]` is parsed as a new HTML document after the outer attribute is decoded. Walk
    # that real second parsing stage with the outer decoded-to-raw map, including another one-pass
    # decode for each nested attribute. Excessive recursive srcdoc nesting fails closed.
    if depth > 8:
        raise RuntimeError("srcdoc nesting exceeds scanner safety bound")
    markup = html_markup_mask(source)

    for raw_tag, tag_start, body_start, body_end in rawtext_blocks(source):
        body = source[body_start:body_end]
        body_map = mapping[body_start:body_end]
        if raw_tag == "script":
            script_kind, has_src = raw_script_element_context(
                source, mapping, tag_start)
            if not has_src and script_kind in {"classic", "module"}:
                scan_js(body, body_map, hits, depth)
            elif not has_src and script_kind in {"importmap", "speculationrules"}:
                scan_processed_script_block(body, body_map, hits, depth, script_kind)
        elif raw_tag == "style":
            scan_css(body, body_map, hits)

    for tm in TAGSPAN.finditer(markup):
        tag = tm.group(1).lower()
        by_name = {}
        context = first_tag_attribute_values(
            source, mapping, tm, {"rel", "type", "language"})
        link_rel = context.get("rel", "") if tag == "link" else ""
        script_kind = script_element_kind(context) if tag == "script" else "classic"
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
                scan_executable_data_url(
                    tag, name, value, value_map, hits, depth, link_rel, script_kind)
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
                url = re.search(r'(?ai)\burl\s*=', content)
                if url:
                    target = content[url.end():]
                    target_map = content_map[url.end():]
                    scan_data_payload(target, target_map, hits, depth, "html")
                    scan_javascript_url(target, target_map, hits, depth)
                    add_value_hits(target, target_map, hits)


HTML_SUFFIXES = {".html", ".htm", ".xhtml", ".svg", ".xml"}
JS_SUFFIXES = {".js", ".mjs", ".cjs", ".ts"}
CSS_SUFFIXES = {".css"}


def media_mode(path):
    # The scanner has no HTTP Content-Type header. A recognized source suffix supplies the narrow
    # grammar; unknown/extensionless media is deliberately scanned as the union of HTML, JS, and CSS
    # so identical HTML/JS polyglot bytes cannot be certified by a punctuation guess.
    suffix = os.path.splitext(path)[1].lower()
    if suffix in HTML_SUFFIXES:
        return "html"
    if suffix in JS_SUFFIXES:
        return "js"
    if suffix in CSS_SUFFIXES:
        return "css"
    return "unknown"


def stat_fingerprint(info):
    return (
        info.st_dev,
        info.st_ino,
        stat.S_IFMT(info.st_mode),
        info.st_size,
        getattr(info, "st_mtime_ns", int(info.st_mtime * 1000000000)),
        getattr(info, "st_ctime_ns", int(info.st_ctime * 1000000000)),
    )


def read_regular_snapshot(path):
    """Capture one regular-file snapshot without following a replacement symlink."""
    pathname = os.lstat(path)
    if not stat.S_ISREG(pathname.st_mode):
        raise OSError("path is no longer a regular file")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        if (not stat.S_ISREG(opened.st_mode) or
                (pathname.st_dev, pathname.st_ino) != (opened.st_dev, opened.st_ino)):
            raise OSError("path identity changed before open")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        closed = os.fstat(descriptor)
        if stat_fingerprint(opened) != stat_fingerprint(closed):
            raise OSError("file changed while its snapshot was read")
    finally:
        os.close(descriptor)
    raw = b"".join(chunks)
    if len(raw) != opened.st_size:
        raise OSError("snapshot size differs from file metadata")
    return (
        raw.decode("latin-1"),
        stat_fingerprint(opened),
        hashlib.sha256(raw).hexdigest(),
    )


# Capture every text path once. The authority prepass and findings pass consume these exact immutable
# strings; a later closing check fails if pathname identity, metadata, or bytes moved during the scan.
TEXT_SNAPSHOTS = {}
SNAPSHOT_RECORDS = {}
SNAPSHOT_ERRORS = set()
for snapshot_pb in paths:
    try:
        snapshot_text, snapshot_stat, snapshot_digest = read_regular_snapshot(snapshot_pb)
        TEXT_SNAPSHOTS[snapshot_pb] = snapshot_text
        SNAPSHOT_RECORDS[snapshot_pb] = (snapshot_stat, snapshot_digest)
    except OSError:
        SNAPSHOT_ERRORS.add(snapshot_pb)


# Authority prepass: identity narrowing is useful only when the global document binding is stable.
# Inspect all loose classic-capable JavaScript snapshots and every inline classic script before any
# sink is scanned. Modules do not create classic global lexical bindings, so HTML module bodies and
# .mjs declarations do not contribute ambiguity to other scan units.
for authority_pb, authority_text in TEXT_SNAPSHOTS.items():
    authority_path = os.fsdecode(authority_pb)
    authority_mode = media_mode(authority_path)
    if authority_mode in {"js", "unknown"} and not authority_path.lower().endswith(".mjs"):
        authority_code, _, _ = lex_source(authority_text, True)
        if javascript_document_ambiguous(authority_code):
            TREE_DOCUMENT_AMBIGUOUS = True
            break
    if authority_mode in {"html", "unknown"}:
        for _, authority_tag_start, authority_body_start, authority_body_end in rawtext_blocks(
                authority_text):
            authority_kind, authority_has_src = raw_script_element_context(
                authority_text, None, authority_tag_start)
            if authority_kind != "classic" or authority_has_src:
                continue
            authority_body = authority_text[authority_body_start:authority_body_end]
            authority_code, _, _ = lex_source(authority_body, True)
            if javascript_document_ambiguous(authority_code):
                TREE_DOCUMENT_AMBIGUOUS = True
                break
        if TREE_DOCUMENT_AMBIGUOUS:
            break


violations = waived = benign = 0
for pb in paths:
    path = os.fsdecode(pb)
    DECODED_WAIVER_BARRIERS.clear()
    if pb in SNAPSHOT_ERRORS:
        violations += 1
        print("UNREADABLE %s (could not capture a stable regular-file snapshot — fail closed)" %
              sanp(path))
        continue
    text = TEXT_SNAPSHOTS[pb]  # latin-1 preserves byte-to-character offsets with no decode failure

    def next_report_line_terminator(start):
        js_terminator = next_js_line_terminator(text, start)
        form_feed = text.find("\f", start)
        return min(js_terminator, form_feed) if form_feed >= 0 else js_terminator

    starts = [0]
    cursor = 0
    while cursor < len(text):
        terminator = next_report_line_terminator(cursor)
        if terminator >= len(text):
            break
        cursor = terminator + (js_line_terminator_width(text, terminator) or 1)
        starts.append(cursor)

    def loc(off):
        idx = bisect.bisect_right(starts, off) - 1
        st = starts[idx]
        en = next_report_line_terminator(st)
        return idx + 1, text[st:en], st

    hits = {}
    mode = media_mode(path)
    markup = html_markup_mask(text)
    tags = list(TAGSPAN.finditer(markup)) if mode in {"html", "unknown"} else []
    local_targets = local_uri_ranges(text)
    literal_ranges, literal_network = network_literal_context(text)
    consumed_ranges = local_targets + literal_ranges

    # Absolute special-scheme and WebRTC URLs remain conservative anywhere in source. Grammar-
    # sensitive network-path references are added only by a fetching HTML/CSS/JS context below. An
    # inner spelling inside a literal data:/blob: target is not a second request.
    for m in ABS.finditer(text):
        if in_ranges(m.start(), consumed_ranges):
            if m.start() in literal_network:
                hits[m.start()] = 1
        elif valid_authority(text, m.end("slashes")):
            hits[m.start()] = 1
    for m in STUN.finditer(text):
        if (m.start(1) in literal_network or
                not in_ranges(m.start(1), consumed_ranges)):
            hits[m.start(1)] = 1

    # Explicit source media gets its own grammar. Unknown/extensionless text gets the conservative
    # union; this preserves content-first enumeration while resolving cross-language ambiguity closed.
    if mode in {"js", "unknown"}:
        scan_js(text, None, hits)
    if mode in {"css", "unknown"}:
        scan_css(text, None, hits)
    # Scan raw script/style bodies independently too. Prose outside the element may contain quotes
    # meaningful to neither language; it must not be able to extend a heuristic JS/CSS literal mask
    # across the element and hide a real request. `range` is an O(1) identity-to-source offset map.
    if mode in {"html", "unknown"}:
        for raw_tag, tag_start, body_start, body_end in rawtext_blocks(text):
            body = text[body_start:body_end]
            body_map = range(body_start, body_end)
            if raw_tag == "script":
                script_kind, has_src = raw_script_element_context(text, None, tag_start)
                if not has_src and script_kind in {"classic", "module"}:
                    scan_js(body, body_map, hits)
                elif not has_src and script_kind in {"importmap", "speculationrules"}:
                    scan_processed_script_block(body, body_map, hits, 0, script_kind)
            elif raw_tag == "style":
                scan_css(body, body_map, hits)

    ns = []
    for tm in tags:
        tag = tm.group(1).lower()
        by_name = {}
        context = first_tag_attribute_values(
            text, None, tm, {"rel", "type", "language"})
        link_rel = context.get("rel", "") if tag == "link" else ""
        script_kind = script_element_kind(context) if tag == "script" else "classic"
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
                scan_executable_data_url(
                    tag, name, value, value_map, hits, 0, link_rel, script_kind)
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
                url = re.search(r'(?ai)\burl\s*=', content)
                if url:
                    target = content[url.end():]
                    target_map = content_map[url.end():]
                    scan_data_payload(target, target_map, hits, 0, "html")
                    scan_javascript_url(target, target_map, hits, 0)
                    add_value_hits(target, target_map, hits)

    def in_ns(off):
        return any(a <= off < b for a, b in ns)

    for off in sorted(hits):
        ln, body, line_start = loc(off)
        waiver_match = WAIVER.search(body)
        waiver_crosses_decoded_line = bool(
            waiver_match and any(
                off < barrier <= line_start + waiver_match.start()
                for barrier in DECODED_WAIVER_BARRIERS
            )
        )
        verdict, cls = ("NSURI ", "benign") if in_ns(off) else \
                       (("WAIVED", "waived") if waiver_match and not waiver_crosses_decoded_line else
                        (("UNCERT", "violations") if hits[off] == "uncertain" else
                         ("EGRESS", "violations")))
        if cls == "benign":
            benign += 1
        elif cls == "waived":
            waived += 1
        else:
            violations += 1
        print("%s %s:%d:%s" % (verdict, sanp(path), ln, CTRL.sub("?", body)))

# Re-open only for a closing fail-closed comparison, never as parser input. This binds the green
# result to the captured snapshot and detects atomic path replacement, in-place writes, truncation,
# or metadata/byte drift between capture and completion.
for stable_pb, (expected_stat, expected_digest) in SNAPSHOT_RECORDS.items():
    stable_path = os.fsdecode(stable_pb)
    try:
        _, observed_stat, observed_digest = read_regular_snapshot(stable_pb)
    except OSError:
        observed_stat = observed_digest = None
    if observed_stat != expected_stat or observed_digest != expected_digest:
        violations += 1
        print("CHANGED %s (path identity or bytes changed during scan — fail closed)" %
              sanp(stable_path))

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
