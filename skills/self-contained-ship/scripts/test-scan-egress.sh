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
mkdir -p "$T/pr" "$T/laundry" "$T/webrtc" "$T/localok" "$T/fifo" "$T/binurl"
# protocol-relative //host in browser-auto-fetched contexts (bare '//', assembled to stay inert here)
_j="${_sep}${_sl}${_sl}"
printf '<img srcset="%scdn.evil.invalid/a.png 2x">\n<video poster="%sevil.invalid/f.jpg"></video>\n' "${_sl}${_sl}" "${_sl}${_sl}" > "$T/pr/index.html"
printf '<meta http-equiv="refresh" content="0;url=%sevil.invalid/next">\n' "${_sl}${_sl}" > "$T/pr/redirect.html"
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

check() { # <label> <want-exit> <needle-or-empty> -- <scan args...>
  local label="$1" want="$2" needle="$3"; shift 3
  local out got
  out="$(bash "$SCAN" "$@" 2>&1)"; got=$?
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q -- "$needle"; then no "$label (missing '$needle')"; return; fi
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
check "protocol-relative srcset/poster fails"   1 "EGRESS"            "$T/pr"
check "meta-refresh protocol-relative fails"     1 "EGRESS"            "$T/pr"
check "DOCTYPE wrapper does not launder a URL"   1 "EGRESS"            "$T/laundry"
check "WebRTC stun: scheme detected"             1 "EGRESS"            "$T/webrtc"
check "same-origin/data fetch + README pass"     0 ""                 "$T/localok"
check "FIFO in dir fails closed (no hang)"        1 "SPECIAL"           "$T/fifo"
check "direct FIFO target fails closed"          1 "SPECIAL"           "$T/fifo/pipe"
check "embedded-URL binary fails even if waived" 1 "EGRESS(binary)"    --allow-binary '*' "$T/binurl"

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
