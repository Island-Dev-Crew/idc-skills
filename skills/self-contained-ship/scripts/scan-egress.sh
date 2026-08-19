#!/usr/bin/env bash
# self-contained-ship: STATIC egress scanner. Fails closed (exit 1) on any un-waived
# external reference in a deliverable. This is the static rung — necessary, not
# sufficient. Obfuscation and string-built URLs slip past a regex; the ENFORCED proof
# is the sealed-load runtime rung in SKILL.md. State that boundary; never imply this
# grep alone certifies containment.
set -euo pipefail

# Every egress vector, caught case-INSENSITIVELY so HTTPS:// / FETCH( can't bypass:
#   absolute schemes http(s)/ws(s)/ftp; fetch(; new WebSocket; XMLHttpRequest;
#   EventSource; sendBeacon; dynamic import( of a URL; @import of a URL; url(http|//)
#   in CSS; and src=/href= to http|// (covers <link href=http, <script src=http).
EGRESS="(https?|wss?|ftp)://|fetch[[:space:]]*\(|new[[:space:]]+WebSocket|XMLHttpRequest|EventSource|navigator\.sendBeacon|import[[:space:]]*\([^)]*(https?:)?//|@import[^;{]*(https?:)?//|url\([[:space:]]*[\"']?(https?:)?//|(src|href)[[:space:]]*=[[:space:]]*[\"']?(https?:)?//"

# The waiver: a BOUNDED, case-SENSITIVE, TRAILING comment. A hit is suppressed only
# when ITS line ends with a real `# egress-ok` / `// egress-ok` / `/* egress-ok */`.
# The delimiter must sit at line-start or after whitespace, so a URL-internal `//`
# (…evil.example//egress-ok at EOL) can't act as the comment delimiter and launder a
# real hit — the anchor requires start/space, delimiter, egress-ok, then end-of-line.
WAIVER='(^|[[:space:]])(#|//|/\*)[[:space:]]*egress-ok([[:space:]]*\*/)?[[:space:]]*$'

[ "$#" -ge 1 ] || { echo "usage: scan-egress.sh <file-or-dir> ..." >&2; exit 2; }

# Enumerate by CONTENT, not by extension. An allowlist of extensions missed
# extensionless scripts (`deploy` with a shebang), UPPERCASE extensions (`.SH`), and
# any novel extension — all false greens (review finding). Instead: take every regular
# file and classify text-vs-binary by content (`grep -I`), scan every text file whatever
# its name. Symlinks break self-containment (the content lives outside the shipped tree),
# so they are flagged as violations. Binary files can't be regex-scanned for URLs, so
# they are reported as UNSCANNED rather than silently passed.
files=()
symlinks=()
binaries=()
classify_file() {  # <path> -> append to files (text) or binaries (binary)
  if LC_ALL=C grep -Iq . "$1" 2>/dev/null; then files+=("$1"); else binaries+=("$1"); fi
}
for p in "$@"; do
  if [ -L "$p" ]; then
    symlinks+=("$p")
  elif [ -d "$p" ]; then
    while IFS= read -r f || [ -n "$f" ]; do symlinks+=("$f"); done < <(find "$p" -type l 2>/dev/null)
    while IFS= read -r f || [ -n "$f" ]; do classify_file "$f"; done < <(find "$p" -type f 2>/dev/null)
  elif [ -e "$p" ]; then
    classify_file "$p"
  else
    echo "scan-egress: no such path: $p" >&2; exit 2
  fi
done
[ $(( ${#files[@]} + ${#symlinks[@]} + ${#binaries[@]} )) -ge 1 ] || { echo "scan-egress: no scannable files under: $*" >&2; exit 2; }

violations=0
waived=0
benign=0
for f in "${files[@]}"; do
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    n="${line%%:*}"
    body="${line#*:}"
    # Non-fetching URI contexts: XML namespace declarations (xmlns / xmlns:*) and DOCTYPE
    # DTD URIs are pure identifiers — a browser never fetches them, so the bare-scheme
    # branch flagging inline-SVG xmlns="http://www.w3.org/2000/svg" is a false positive.
    # Strip those contexts; if NO egress survives, the hit was a non-fetching URI. A line
    # that also carries a real egress keeps it after the strip and still falls through.
    stripped="$(printf '%s' "$body" | sed -E \
      -e 's/(^|[^A-Za-z0-9_-])xmlns(:[A-Za-z0-9_.-]+)?[[:space:]]*=[[:space:]]*"[^"]*"/\1/g' \
      -e "s/(^|[^A-Za-z0-9_-])xmlns(:[A-Za-z0-9_.-]+)?[[:space:]]*=[[:space:]]*'[^']*'/\1/g" \
      -e 's/<![Dd][Oo][Cc][Tt][Yy][Pp][Ee][^>]*>//g')"
    if ! printf '%s' "$stripped" | grep -Eqi -- "$EGRESS"; then
      benign=$((benign + 1)); echo "NSURI   $f:$n:$body"
      continue
    fi
    # Per-HIT waiver: re-test the hit's own line against the bounded trailing anchor,
    # never a substring — so one query-string marker can't launder a real egress.
    if printf '%s' "$body" | grep -Eq -- "$WAIVER"; then
      waived=$((waived + 1)); echo "WAIVED  $f:$n:$body"
    else
      violations=$((violations + 1)); echo "EGRESS  $f:$n:$body"
    fi
  done < <(grep -niE -- "$EGRESS" "$f" || true)
done

# Symlinks break self-containment: the referenced bytes live outside the shipped tree,
# so their content was never scanned. Treat each as a violation requiring the human.
if [ "${#symlinks[@]}" -gt 0 ]; then
  for s in "${symlinks[@]}"; do
    violations=$((violations + 1))
    echo "SYMLINK $s -> $(readlink "$s" 2>/dev/null || echo '?') (breaks self-containment)"
  done
fi

# Binary files cannot be regex-scanned for URLs — report them so they are never a silent
# green. This does not auto-fail (legitimate assets are common); the operator reviews.
bincount=${#binaries[@]}
if [ "$bincount" -gt 0 ]; then
  for b in "${binaries[@]}"; do echo "UNSCANNED(binary) $b"; done
fi

echo "--- scan-egress: $violations un-waived, $waived waived, $benign non-fetching URI(s), ${#files[@]} text file(s), ${#symlinks[@]} symlink(s), $bincount binary/unscanned ---"
[ "$bincount" -eq 0 ] || echo "scan-egress: NOTE — $bincount binary file(s) not regex-scanned; review them for embedded egress." >&2
[ "$violations" -eq 0 ] || { echo "scan-egress: FAIL — un-waived external reference(s) or self-containment break(s)" >&2; exit 1; }
echo "scan-egress: PASS — no un-waived external references (binaries excepted, see NOTE)"
exit 0
