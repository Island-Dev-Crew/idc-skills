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
ABS = re.compile(r'(?i)(?:https?|wss?|ftp):(?P<slashes>[/\\]*)')
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
    if re.match(r'(?i)^\s*(?:data|blob):', normalized):
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
    if not ((grammar == "html" and html_mime) or (grammar == "js" and js_mime) or
            (grammar == "css" and css_mime)):
        return
    # Static recovery of a base64 executable payload has no faithful byte-to-source map. Treat that
    # unsupported executable form as a finding at the outer target instead of certifying it clean.
    if re.search(r'(?i)(?:^|;)base64(?:;|$)', metadata):
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
    elif grammar == "js":
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


def scan_executable_data_url(tag, name, value, mapping, hits, depth, link_rel=""):
    # data:/blob: targets are not egress by themselves. A literal data document can nevertheless
    # instantiate a second parser at a browser sink. Navigation targets parse HTML; script sources
    # parse JS; stylesheet links parse CSS. Blob bytes are not present in the URL, so the code that
    # constructs them remains visible to the ordinary JS scanner instead.
    grammar = None
    navigation = ((tag in {"iframe", "frame", "object", "embed"} and name in {"src", "data"}) or
            (tag in {"a", "area"} and name == "href") or
            (tag == "form" and name == "action") or
            (tag in {"button", "input"} and name == "formaction"))
    if navigation:
        grammar = "html"
    elif tag == "script" and name == "src":
        grammar = "js"
    elif tag == "link" and name == "href":
        rel_tokens = {token.lower() for token in link_rel.split()}
        grammar = "js" if "modulepreload" in rel_tokens else "css"
    if grammar:
        scan_data_payload(value, mapping, hits, depth, grammar)
    if navigation:
        scan_javascript_url(value, mapping, hits, depth)


def lex_source(source, line_comments):
    # Produce an offset-preserving CODE mask plus literal spans. Comments and literal bodies become
    # spaces (newlines retained). Grammar regexes operate only on CODE; a matched API then consumes
    # its adjacent literal from the original span. This prevents comments/ordinary strings from
    # impersonating executable fetch grammar without losing the URL inside a real argument.
    chars = list(source)
    spans = []
    opaque = []
    n = len(source)

    def add_opaque(start, end):
        opaque.append((start, end))
        mask_range(chars, start, end)

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
        if re.search(
                r'(?is)(?:^|[;{}])\s*(?:export\s+(?:default\s+)?)?class\s+'
                r'[A-Za-z_$][A-Za-z0-9_$]*(?:\s+extends\s+.+)?$', before):
            return True
        if re.search(
                r'(?is)(?:^|[;{}])\s*export\s+default\s+class(?:\s+extends\s+.+)?$', before):
            return True
        return bool(re.search(
            r'(?is)(?:^|[;{}])\s*(?:export\s+)?(?:declare\s+)?'
            r'(?:interface|enum|namespace|module)\s+[A-Za-z_$][A-Za-z0-9_$.]*$', before
        ))

    def regex_allowed(pos, floor):
        # ECMAScript's lexical goal depends on the preceding token. This small tokenizer only needs
        # the conservative expression-start boundary: after an operator/delimiter or a keyword that
        # requires an expression, `/` begins a regex; after a value/close-delimiter it is division.
        prior = "".join(chars[floor:pos]).rstrip()
        if not prior:
            return True
        # Import/export declarations terminate before a following line's expression even though the
        # module specifier literal is blanked in CODE. Likewise `export {x}` closes with `}` but is not
        # a statement block. Recognize only a newline-separated declaration tail.
        previous_spans = [span for span in spans if span["end"] <= pos]
        if previous_spans:
            previous = max(previous_spans, key=lambda span: span["end"])
            if "\n" in source[previous["end"]:pos]:
                before_literal = "".join(chars[floor:previous["start"]]).rstrip()
                if (re.search(r'(?is)(?:^|[;\n])\s*(?:import|export)\b[^;\n]*\bfrom$',
                              before_literal) or
                        re.search(r'(?is)(?:^|[;\n])\s*import\s*$', before_literal)):
                    return True
        if "\n" in source[floor:pos] and re.search(
                r'(?is)(?:^|[;\n])\s*export\s*\{[^{}]*\}\s*$', prior):
            return True
        if prior.endswith("++") or prior.endswith("--"):
            return False
        if prior.endswith("..."):
            return True
        if prior[-1] in "([{,:;=!?&|+-*/%^~<>":
            return True
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
            if ch in "\r\n":
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
                i = min(n, i + 2)
                continue
            if source[i] == quote:
                return i + 1
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
                end = source.find("\n", i)
                end = n if end < 0 else end
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
                end = source.find("\n", i + 2)
                end = n if end < 0 else end
                add_opaque(i, end)
                i = end
                continue
            if source[i] in "\"'":
                end = string_end(i, source[i])
                add_literal(i, end)
                i = end
                continue
            if source[i] == "`":
                if line_comments:
                    i = parse_template(i)
                else:
                    end = string_end(i, "`")
                    add_literal(i, end)
                    i = end
                continue
            if line_comments and source[i] == "/" and regex_allowed(i, floor):
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
    return "".join(chars), spans, opaque


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
        if escaped == "\r":
            index += 3 if index + 2 < size and value[index + 2] == "\n" else 2
            continue
        if escaped == "\n":
            index += 2
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


def javascript_identifier_pattern(word):
    # ECMAScript permits Unicode escapes inside IdentifierName tokens. Match the exact ASCII API
    # spelling or an equivalent four-digit/code-point escape for each character; callers retain
    # their normal identifier boundary checks, so this does not turn arbitrary text into grammar.
    parts = []
    for char in word:
        digits = format(ord(char), "x")
        brace_zeros = 6 - len(digits)
        parts.append(
            r'(?:' + re.escape(char) + r'|\\u(?:' + format(ord(char), "04x") +
            r'|\{0{0,' + str(brace_zeros) + r'}' + digits + r'\}))'
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
    return span["value"], origins


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
        if re.match(r'(?i)^\s*(?:data|blob):', value):
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
            if re.match(r'(?i)^\s*(?:data|blob):', value):
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
            if ABS.match(value, rel) or re.match(r'(?i)(?:stun|turns?):', value[rel:]):
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
    dynamic = [span for span in inside if span.get("dynamic")]
    if dynamic:
        span = min(dynamic, key=lambda item: (item["start"], -item["end"]))
        if not mask[start:span["start"]].strip() and not mask[span["end"]:end].strip():
            return span
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


def scan_js(source, mapping, hits, depth=0):
    if depth > 8:
        raise RuntimeError("JavaScript data URL nesting exceeds scanner safety bound")
    code, spans, _ = lex_source(source, True)

    def identifiers(*names):
        return r'(?:' + "|".join(javascript_identifier_pattern(name) for name in names) + r')'

    identifier_start = r'(?<![A-Za-z0-9_$])'
    api_identifier = identifiers(
        "fetch", "import", "importScripts", "WebSocket", "EventSource", "sendBeacon",
        "Worker", "SharedWorker"
    )
    call = re.compile(
        r'(?i)' + identifier_start + r'(?P<api>' + api_identifier + r')\s*(?:\?\.\s*)?\('
    )
    for m in call.finditer(code):
        args, _ = call_args(code, spans, m.end() - 1)
        if args and args[0][2]:
            span = args[0][2]
            api_name = decode_javascript_identifier(m.group("api")).lower()
            if api_name in {"import", "importscripts", "worker", "sharedworker"}:
                scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)

    for rx, data_grammar in (
        (re.compile(r'(?i)' + identifier_start + identifiers("serviceWorker") + r'\s*\.\s*' +
                    identifiers("register") + r'\s*\('), None),
        (re.compile(r'(?i)' + identifier_start + identifiers("window") + r'\s*\.\s*' +
                    identifiers("open") + r'\s*\('), "html"),
        (re.compile(r'(?i)' + identifier_start + identifiers("location") +
                    r'\s*(?:\.|\?\.)\s*' +
                    identifiers("assign", "replace") + r'\s*\('), "html"),
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
    for m in re.finditer(r'(?i)\.\s*' + identifiers("open") + r'\s*\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        if len(args) >= 2 and args[0][2] and args[1][2]:
            method = span_runtime_value(args[0][2], mapping)[0].upper()
            if method in {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "CONNECT", "TRACE"}:
                span_value_hits(args[1][2], mapping, hits)

    # Static import/export: comments are blank space in CODE, literals are separate spans. The
    # bounded clause cannot cross `=`, `;`, `(`, `.`, or a string into a distant `from`.
    mod_from = re.compile(r'(?is)\b(?:import|export)\b[\w$*{},\s]*?\bfrom\b')
    for m in mod_from.finditer(code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)\bimport\b', code):
        p = m.end()
        span = next_literal(code, spans, p)
        if span:  # bare side-effect import; import.meta/import(...) contain visible punctuation
            scan_span_data(span, mapping, hits, depth, "js")
            span_value_hits(span, mapping, hits)

    # Dot property assignments and location.href/direct location assignments.
    prop = identifiers("srcset", "src", "href", "action", "formaction", "poster",
                       "background", "cite", "ping")
    for m in re.finditer(r'(?i)\.\s*(?P<prop>' + prop + r')\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            name = decode_javascript_identifier(m.group("prop")).lower()
            grammars = {"src": ("html", "js"), "href": ("html", "css"),
                        "action": ("html",), "formaction": ("html",)}
            for grammar in grammars.get(name, ()):
                scan_span_data(span, mapping, hits, depth, grammar)
            if name in {"src", "href", "action", "formaction"}:
                scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)(?<![A-Za-z0-9_$\.])' + identifiers("location") + r'\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "html")
            scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits)
    for m in re.finditer(r'(?i)' + identifier_start +
                         identifiers("window", "document", "globalThis", "self", "top", "parent") +
                         r'\s*\.\s*' +
                         identifiers("location") + r'\s*=', code):
        span = next_literal(code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "html")
            scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits)

    # Bracket navigation: location["href"] = URL (including window.location[...]).
    for m in re.finditer(r'(?i)' + identifier_start + identifiers("location") +
                         r'\s*(?:\?\.\s*)?\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name:
            continue
        member_name = span_runtime_value(name, mapping)[0].lower()
        if member_name == "href":
            tail = re.match(r'\s*=', code[close + 1:])
            if tail:
                span = next_literal(code, spans, close + 1 + tail.end())
                if span:
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                    span_value_hits(span, mapping, hits)
        elif member_name in {"assign", "replace"}:
            tail = re.match(r'\s*(?:\?\.\s*)?\(', code[close + 1:])
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
    for m in re.finditer(r'(?i)' + identifier_start +
                         identifiers("window", "document", "globalThis", "navigator", "self",
                                     "top", "parent") +
                         r'\s*\[', code):
        close = code.find("]", m.end())
        if close < 0:
            continue
        name = literal_segment(code, spans, m.end(), close)
        if not name:
            continue
        prop_name = span_runtime_value(name, mapping)[0]
        if prop_name.lower() == "location":
            tail = re.match(r'\s*=', code[close + 1:])
            if tail:
                span = next_literal(code, spans, close + 1 + tail.end())
                if span:
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                    span_value_hits(span, mapping, hits)
            else:
                chained = re.match(r'\s*(?:\?\.\s*)?\[', code[close + 1:])
                if chained:
                    open2 = close + 1 + chained.end()
                    close2 = code.find("]", open2)
                    member = literal_segment(code, spans, open2, close2) if close2 >= 0 else None
                    assign = re.match(r'\s*=', code[close2 + 1:]) if close2 >= 0 else None
                    member_name = span_runtime_value(member, mapping)[0].lower() if member else ""
                    if member_name == "href" and assign:
                        span = next_literal(code, spans, close2 + 1 + assign.end())
                        if span:
                            scan_span_data(span, mapping, hits, depth, "html")
                            scan_span_javascript_url(span, mapping, hits, depth)
                            span_value_hits(span, mapping, hits)
                    elif member_name in {"assign", "replace"}:
                        call_tail = re.match(r'\s*(?:\?\.\s*)?\(', code[close2 + 1:])
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
                        member_name = decode_javascript_identifier(dotted.group("member")).lower()
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
        tail = re.match(r'\s*(?:\?\.\s*)?\(', code[close + 1:])
        if not tail:
            continue
        if prop_name.lower() in {"fetch", "open", "websocket", "eventsource", "sendbeacon",
                                "worker", "sharedworker", "importscripts"}:
            args, _ = call_args(code, spans, close + 1 + tail.end() - 1)
            if args and args[0][2]:
                span = args[0][2]
                if prop_name.lower() == "open":
                    scan_span_data(span, mapping, hits, depth, "html")
                    scan_span_javascript_url(span, mapping, hits, depth)
                elif prop_name.lower() in {"worker", "sharedworker", "importscripts"}:
                    scan_span_data(span, mapping, hits, depth, "js")
                span_value_hits(span, mapping, hits)

    # DOM setters: setAttribute(name, value) and setAttributeNS(ns, name, value).
    setter = identifiers("setAttributeNS", "setAttribute")
    for m in re.finditer(r'(?i)\.\s*(?P<setter>' + setter + r')\s*\(', code):
        args, _ = call_args(code, spans, m.end() - 1)
        setter_name = decode_javascript_identifier(m.group("setter")).lower()
        name_i, value_i = (1, 2) if setter_name == "setattributens" else (0, 1)
        if len(args) <= value_i or not args[name_i][2] or not args[value_i][2]:
            continue
        name = span_runtime_value(args[name_i][2], mapping)[0].lower()
        if name in SET_ATTRS:
            span = args[value_i][2]
            grammars = {"src": ("html", "js"), "href": ("html", "css"),
                        "action": ("html",), "formaction": ("html",)}
            for grammar in grammars.get(name, ()):
                scan_span_data(span, mapping, hits, depth, grammar)
            if name in {"src", "href", "action", "formaction"}:
                scan_span_javascript_url(span, mapping, hits, depth)
            span_value_hits(span, mapping, hits, name in {"srcset", "imagesrcset", "ping"})


def scan_css(source, mapping, hits, depth=0):
    if depth > 8:
        raise RuntimeError("CSS data URL nesting exceeds scanner safety bound")
    css_code, spans, _ = lex_source(source, False)
    _, _, js_opaque = lex_source(source, True)
    calls = re.compile(r'(?i)(?<![\w$.])(?P<fn>url|image-set|image)\s*\(')
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
        if m.group("fn").lower() == "url":
            start = m.end()
            span = literal_segment(css_code, spans, start, close)
            if span:
                span_value_hits(span, mapping, hits)
            else:
                left, right = start, close
                while left < right and source[left].isspace():
                    left += 1
                while right > left and source[right - 1].isspace():
                    right -= 1
                for rel in external_offsets(source[left:right]):
                    raw = map_offset(mapping, left + rel)
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
    for m in re.finditer(r'(?i)@import\b', css_code):
        if in_ranges(m.start(), js_opaque):
            continue
        span = next_literal(css_code, spans, m.end())
        if span:
            scan_span_data(span, mapping, hits, depth, "css")
            span_value_hits(span, mapping, hits)


def scan_srcdoc(source, mapping, hits, depth=0):
    # `iframe[srcdoc]` is parsed as a new HTML document after the outer attribute is decoded. Walk
    # that real second parsing stage with the outer decoded-to-raw map, including another one-pass
    # decode for each nested attribute. Excessive recursive srcdoc nesting fails closed.
    if depth > 8:
        raise RuntimeError("srcdoc nesting exceeds scanner safety bound")
    markup = html_markup_mask(source)

    for raw_tag, _, body_start, body_end in rawtext_blocks(source):
        body = source[body_start:body_end]
        body_map = mapping[body_start:body_end]
        if raw_tag == "script":
            scan_js(body, body_map, hits, depth)
        elif raw_tag == "style":
            scan_css(body, body_map, hits)

    for tm in TAGSPAN.finditer(markup):
        tag = tm.group(1).lower()
        by_name = {}
        link_rel = ""
        if tag == "link":
            for rel_attr in ATTR.finditer(tm.group(2)):
                if rel_attr.group(1).lower() != "rel":
                    continue
                rel_group = next((g for g in (2, 3, 4) if rel_attr.group(g) is not None), None)
                if rel_group is not None:
                    rel_base = tm.start(2) + rel_attr.start(rel_group)
                    rel_raw = source[rel_base:rel_base + len(rel_attr.group(rel_group))]
                    link_rel = decode_html_attr_once(
                        rel_raw, mapping[rel_base:rel_base + len(rel_raw)])[0]
                break
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
                scan_executable_data_url(tag, name, value, value_map, hits, depth, link_rel)
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
        for raw_tag, _, body_start, body_end in rawtext_blocks(text):
            body = text[body_start:body_end]
            body_map = range(body_start, body_end)
            if raw_tag == "script":
                scan_js(body, body_map, hits)
            elif raw_tag == "style":
                scan_css(body, body_map, hits)

    ns = []
    for tm in tags:
        tag = tm.group(1).lower()
        by_name = {}
        link_rel = ""
        if tag == "link":
            for rel_attr in ATTR.finditer(tm.group(2)):
                if rel_attr.group(1).lower() != "rel":
                    continue
                rel_group = next((g for g in (2, 3, 4) if rel_attr.group(g) is not None), None)
                if rel_group is not None:
                    rel_base = tm.start(2) + rel_attr.start(rel_group)
                    rel_raw = text[rel_base:rel_base + len(rel_attr.group(rel_group))]
                    link_rel = decode_html_attr_once(rel_raw, rel_base)[0]
                break
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
                scan_executable_data_url(tag, name, value, value_map, hits, 0, link_rel)
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
                    target = content[url.end():]
                    target_map = content_map[url.end():]
                    scan_data_payload(target, target_map, hits, 0, "html")
                    scan_javascript_url(target, target_map, hits, 0)
                    add_value_hits(target, target_map, hits)

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
