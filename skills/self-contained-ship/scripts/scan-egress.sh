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

files=()
for p in "$@"; do
  if [ -d "$p" ]; then
    while IFS= read -r f; do files+=("$f"); done < <(find "$p" -type f \
      \( -name '*.html' -o -name '*.htm' -o -name '*.css' -o -name '*.js' \
         -o -name '*.mjs' -o -name '*.cjs' -o -name '*.svg' -o -name '*.json' -o -name '*.md' \
         -o -name '*.sh' -o -name '*.bash' -o -name '*.zsh' -o -name '*.py' -o -name '*.rb' \
         -o -name '*.pl' -o -name '*.ts' -o -name '*.tsx' -o -name '*.jsx' -o -name '*.mts' \
         -o -name '*.cts' -o -name '*.yaml' -o -name '*.yml' -o -name '*.toml' -o -name '*.txt' \
         -o -name '*.xml' -o -name '*.env' -o -name '*.cfg' -o -name '*.conf' -o -name '*.ini' \))
  elif [ -e "$p" ]; then
    files+=("$p")
  else
    echo "scan-egress: no such path: $p" >&2; exit 2
  fi
done
[ "${#files[@]}" -ge 1 ] || { echo "scan-egress: no scannable files under: $*" >&2; exit 2; }

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

echo "--- scan-egress: $violations un-waived, $waived waived, $benign non-fetching URI(s), ${#files[@]} file(s) ---"
[ "$violations" -eq 0 ] || { echo "scan-egress: FAIL — un-waived external reference(s)" >&2; exit 1; }
echo "scan-egress: PASS — no un-waived external references"
exit 0
