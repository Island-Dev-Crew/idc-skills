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
# The text egress scan is a WHOLE-FILE (multiline-aware) static match, run by python3, so a fetching
# context split across lines (`src\n="//h"`, `fetch(\n"//h")`) and every srcset candidate are caught
# — a per-line regex structurally cannot. python3 is REQUIRED for the text rung: if it is missing the
# scan cannot certify text files and FAILS CLOSED (exit 1), never open. `jq` is not used here.
#
# TRUSTED COUNTS CHANNEL: the pass/fail gate is driven by a counts line python writes to a SEPARATE
# temp file — never parsed out of the findings stream. Finding text is attacker-influenced bytes
# (a NUL after the classification window can flip grep into "Binary file matches" mode and collapse
# an in-band trailer to zero -> false green). The counts line is STRICTLY validated (exactly three
# all-digit fields) and anything else FAILS CLOSED; finding lines are display-only, with control
# bytes sanitized so they can't carry terminal escapes either.
#
# HTML/SVG attribute matching is TAG-BOUNDED: a fetching attribute (`src=`, `srcset=`, ...) counts
# only INSIDE a `<tag ...>` span, so a plain JS variable `const src='//docs'` is not egress; the
# `data=` attribute fetches only on `<object>`, so `<div data='//docs'>` is inert. JS PROPERTY
# assignments (`img.src='//h'` — dot-prefixed) stay caught on their own pattern.
#
# Documented residuals a static scan cannot close (keep the sealed-load runtime rung underneath):
#   - egress that string-concatenation / obfuscation / runtime code BUILDS after load
#   - a request issued by a service worker, a delayed timer, or an interaction the scan never runs
set -uo pipefail

# What a browser (or an XML/CSS/JS consumer) FETCHES. Absolute schemes http(s)/ws(s)/ftp — including
# the backslash forms (`https:\\h`, `https:\/\/h`) URL parsers normalize to slashes — and WebRTC
# stun/turn(s) match anywhere; protocol-relative `//host` (or `\\host`, and an IPv6 `//[...]` literal)
# is caught only in a fetching CONTEXT (a tag-bounded URL attribute incl. every srcset candidate, CSS
# url()/image-set()/@import, a JS network-API call incl. navigator.sendBeacon / new Worker /
# serviceWorker.register / XHR.open, static+dynamic module import / export-from, a location
# navigation, a dot-prefixed fetching property assignment, or a `url=` redirect) and only when a
# hostname char follows, so a JS `// comment` and a same-origin/`data:`/`blob:` target are NOT
# flagged (a runtime-built external URL is the disclosed residual rung 2 catches). The full context
# set lives in the python matcher below; this bash-visible regex is the ABSOLUTE-scheme set used for
# BINARY string scanning (protocol-relative has no meaning inside a compiled binary).
EGRESS_BIN='(https?|wss?|ftp):[/\\][/\\]|(^|[^a-z])(stun|turns?):[a-z0-9]'

usage() { echo "usage: scan-egress.sh [--allow-binary <glob>]... <file-or-dir> ..." >&2; exit 2; }
is_count() { case "$1" in ''|*[!0-9]*) return 1 ;; *) return 0 ;; esac; }  # strict all-digit field

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
    echo "scan-egress: no such path: $p" >&2; exit 2
  fi
done
if [ $(( ${#files[@]} + ${#symlinks[@]} + ${#binaries[@]} + ${#specials[@]} + ${#unreadable[@]} )) -lt 1 ] && [ "$traversal_err" -eq 0 ]; then
  echo "scan-egress: no scannable files under: ${targets[*]}" >&2; exit 2
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
import re, os, bisect

paths = [p for p in open(os.environ["SCAN_EGRESS_FILELIST"], "rb").read().split(b"\0") if p]

# Waiver: a BOUNDED, case-sensitive, TRAILING comment on the hit's own line. The delimiter must sit
# at line-start or after whitespace, so a URL-internal `//` can't act as the comment delimiter.
WAIVER = re.compile(r'(?:^|[ \t])(?:#|//|/\*)[ \t]*egress-ok(?:[ \t]*\*/)?[ \t]*$')

# Absolute schemes anywhere — `[/\\]{2}` also matches the backslash spellings (`https:\\h`,
# `https:\/\/h`) that URL parsers normalize to slashes for special schemes; WebRTC stun/turn
# anywhere (with a non-letter boundary before the scheme, `[` admits an IPv6 literal host).
ABS  = re.compile(r'(?i)(?:https?|wss?|ftp):[/\\][/\\]')
STUN = re.compile(r'(?i)(?:^|[^a-z])(stun|turns?):[a-z0-9\[]')

# One protocol-relative "URL start": two slash-class chars (backslash spellings normalize) then a
# hostname char — `[` included so an IPv6 literal `//[2001:db8::1]/x` is caught. Q = an optional
# JS quote (single/double/backtick) with inner whitespace. All context patterns end with PR (3
# chars), so `m.end()-3` is the URL-start offset for every one of them.
PR = r'[/\\][/\\][a-z0-9\[]'
Q  = r'["\'`]?\s*'

# Fetching CONTEXTS for a protocol-relative URL (an absolute one is already caught by ABS):
#  - CSS url()/image-set()/image()/@import
#  - JS network APIs: fetch, dynamic import(), importScripts, WebSocket, EventSource, sendBeacon,
#    Worker/SharedWorker; XHR `.open("METHOD", "//host")`; serviceWorker.register
#  - static ES modules: `import ... from "//h"`, bare `import "//h"`, `export ... from "//h"`
#  - a location navigation: location.assign()/replace(), `location.href =`, `location =`
#  - a dot-prefixed JS FETCHING-PROPERTY assignment (`img.src = "//h"`) — dot-prefixed only, so a
#    plain variable `const src='//docs'` is NOT egress
#  - a `url=` redirect (meta refresh)
# `(?is)` = case-insensitive + DOTALL so a context split across newlines still matches.
CSS     = re.compile(r'(?is)(?:@import\s+|(?:url|image-set|image)\s*\(\s*)' + Q + PR)
JSCALL  = re.compile(r'(?is)\b(?:fetch|import|importScripts|WebSocket|EventSource|sendBeacon|Worker|SharedWorker)\s*\(\s*' + Q + PR)
XHROPEN = re.compile(r'(?is)\.open\s*\(\s*(["\'`])[^"\'`]*\1\s*,\s*' + Q + PR)
SWREG   = re.compile(r'(?is)\bserviceWorker\s*\.\s*register\s*\(\s*' + Q + PR)
ESMOD   = re.compile(r'(?is)\b(?:import|export)\s+(?:[\w$*{},\s]+from\s+)?["\'`]\s*' + PR)
LOC     = re.compile(r'(?is)(?:\blocation\s*\.\s*(?:assign|replace)\s*\(\s*|\blocation\s*(?:\.\s*href\s*)?=\s*)' + Q + PR)
JSPROP  = re.compile(r'(?is)\.\s*(?:srcset|src|href|action|formaction|poster|background|cite|ping)\s*=\s*["\'`]\s*' + PR)
URLEQ   = re.compile(r'(?i)\burl\s*=\s*' + Q + PR)
PROTO   = re.compile(r'(?i)' + PR)

# HTML/SVG fetching attributes are TAG-BOUNDED: an attribute only fetches inside a real `<tag ...>`
# span (quote-aware, so a `>` inside a quoted value doesn't end the span; DOTALL, so a multiline tag
# still matches; an unclosed tag at EOF still counts). A bare `src=`/`data=` in plain JS source is a
# variable, not markup, and is NOT matched here (JSPROP covers dot-prefixed property assignments).
# `data` fetches ONLY on <object>; on any other element it is inert markup.
TAGSPAN = re.compile(r'(?is)<([a-z][a-z0-9:-]*)((?:"[^"]*"|\'[^\']*\'|[^<>"\'])*)>?')
FETCH_ATTRS = r'imagesrcset|srcset|src|xlink:href|href|formaction|action|poster|background|cite|ping|manifest|data'
ATTR    = re.compile(r'(?is)\b(' + FETCH_ATTRS + r')\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'>]+))')

# A genuine XML namespace declaration — `xmlns`/`xmlns:pfx` as an ATTRIBUTE INSIDE A TAG, e.g.
# `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="...">` — is a pure identifier a browser never
# fetches. Suppress ONLY that, via the same tag-bounded span (EVERY xmlns attribute in the tag, not
# just the first). A bare `xmlns=` assignment in JS source, or a `fetch(xmlns=...)` argument, has no
# enclosing tag and is NOT suppressed (it is real egress).
XMLNSATTR = re.compile(r'(?is)\bxmlns(?::[\w.-]+)?\s*=\s*("[^"]*"|\'[^\']*\')')

CTRL = re.compile(r'[\x00-\x08\x0b-\x1f\x7f]')     # display sanitizer: finding text carries no authority


def proto_offsets_in_value(val, base):
    # every protocol-relative candidate inside an attribute value (srcset comma-separated candidates,
    # leading whitespace inside the quotes), excluding an absolute-scheme `//` (preceded by `:`).
    out = []
    for m in PROTO.finditer(val):
        s = m.start()
        if s > 0 and val[s - 1] == ":":
            continue
        out.append(base + s)
    return out


violations = waived = benign = 0
for pb in paths:
    path = os.fsdecode(pb)
    try:
        with open(pb, "rb") as fh:
            text = fh.read().decode("latin-1")     # latin-1: byte<->char 1:1, stable offsets, no decode err
    except OSError:
        violations += 1
        print("UNREADABLE %s (could not read during scan — fail closed)" % path)
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

    ns = []
    for tm in TAGSPAN.finditer(text):
        for am in XMLNSATTR.finditer(tm.group(2)):
            ns.append((tm.start(2) + am.start(1), tm.start(2) + am.end(1)))

    def in_ns(off):
        return any(a <= off < b for a, b in ns)

    hits = {}
    for m in ABS.finditer(text):
        hits[m.start()] = 1
    for m in STUN.finditer(text):
        hits[m.start(1)] = 1
    for rx in (CSS, JSCALL, XHROPEN, SWREG, ESMOD, LOC, JSPROP, URLEQ):
        for m in rx.finditer(text):
            hits[m.end() - 3] = 1
    for tm in TAGSPAN.finditer(text):
        tag = tm.group(1).lower()
        for m in ATTR.finditer(tm.group(2)):
            if m.group(1).lower() == "data" and tag != "object":
                continue                            # data= fetches only on <object>
            for gi in (2, 3, 4):
                if m.group(gi) is not None:
                    for off in proto_offsets_in_value(m.group(gi), tm.start(2) + m.start(gi)):
                        hits[off] = 1
                    break

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
        print("%s %s:%d:%s" % (verdict, path, ln, CTRL.sub("?", body)))

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
  # Fold in the counts from the trusted side channel. STRICT validation — exactly one line of
  # exactly three all-digit fields — and anything else FAILS CLOSED: arbitrary finding bytes must
  # never be able to zero the gate (a NUL in stdout once collapsed an in-band trailer to PASS).
  counts="$(head -n 1 "$sc_cnt" 2>/dev/null | tr -d '\n')"
  set -f
  # shellcheck disable=SC2086  # intentional word split of the validated counts line
  set -- $counts
  set +f
  if [ "$#" -ne 3 ] || ! is_count "$1" || ! is_count "$2" || ! is_count "$3"; then
    echo "scan-egress: counts channel invalid ('$counts') — FAIL CLOSED" >&2
    rm -f "$sc_in" "$sc_out" "$sc_err" "$sc_cnt"
    exit 1
  fi
  violations=$((violations + $1))
  waived=$((waived + $2))
  benign=$((benign + $3))
  rm -f "$sc_in" "$sc_out" "$sc_err" "$sc_cnt"
fi

# Symlinks break self-containment: the referenced bytes live outside the shipped tree.
for s in ${symlinks[@]+"${symlinks[@]}"}; do
  violations=$((violations + 1))
  echo "SYMLINK $s -> $(readlink "$s" 2>/dev/null || echo '?') (breaks self-containment)"
done

# Non-regular files can't be scanned (and reading a FIFO would hang) — fail closed.
for sp in ${specials[@]+"${specials[@]}"}; do
  violations=$((violations + 1))
  echo "SPECIAL $sp (non-regular file: FIFO/socket/device — unscannable, fail closed)"
done

# Unreadable regular files: we never saw the bytes, so no glob waiver may launder them — fail closed.
for u in ${unreadable[@]+"${unreadable[@]}"}; do
  violations=$((violations + 1))
  echo "UNREADABLE $u (regular file not readable — cannot certify, fail closed)"
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
    violations=$((violations + 1)); echo "UNREADABLE(binary) $b (grep error rc=$grc — cannot certify, fail closed)"
  elif [ -n "$raw" ]; then
    hits="$(printf '%s' "$raw" | head -5 | tr '\n' ' ')"
    violations=$((violations + 1)); echo "EGRESS(binary) $b :: $hits"
  elif is_waived_binary "$b"; then
    waived_bin=$((waived_bin + 1)); echo "WAIVED-BINARY $b"
  else
    review_bin=$((review_bin + 1))
    violations=$((violations + 1))
    echo "UNSCANNED(binary) $b (static scan cannot certify; --allow-binary <glob> to waive a reviewed asset)"
  fi
done

echo "--- scan-egress: $violations un-waived, $waived waived, $benign non-fetching URI(s), ${#files[@]} text file(s), ${#symlinks[@]} symlink(s), ${#specials[@]} special, ${#unreadable[@]} unreadable, $review_bin binary fail(s), $waived_bin binary waived ---"
if [ "$violations" -ne 0 ]; then
  echo "scan-egress: FAIL — un-waived external reference(s), symlink(s), non-regular/unreadable file(s), traversal error, or binary file(s)" >&2
  exit 1
fi
echo "scan-egress: PASS — every file scanned clean or explicitly waived"
exit 0
