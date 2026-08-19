#!/usr/bin/env bash
# self-contained-ship: STATIC egress scanner. Fails closed (exit 1) on any un-waived external
# reference, symlink, non-regular file, OR binary in a deliverable. This is the static rung —
# necessary, not sufficient. Obfuscation and string-built URLs slip past a regex; the ENFORCED
# proof is the sealed-load runtime rung in SKILL.md. State that boundary; never imply this grep
# alone certifies containment.
#
# SECURE-BY-DEFAULT: a green result means "every file was scanned clean OR explicitly human-waived"
# — never "some files we could not look at." A symlink fails closed (bytes outside the tree); a
# non-regular file (FIFO/socket/device) fails closed and is NEVER read (reading a FIFO would hang);
# a binary fails closed too — its strings are `grep -a`-scanned, an embedded URL is reported and
# fails EVEN IF the binary is glob-waived (a waiver must not launder a live URL), and a URL-free
# binary fails as uncertifiable until reviewed and waived with `--allow-binary <glob>`.
set -uo pipefail

# What a browser (or an XML/CSS/JS consumer) FETCHES, caught case-INSENSITIVELY. Absolute schemes
# `http(s)/ws(s)/ftp` and WebRTC `stun/turn(s)` match anywhere; protocol-relative `//host` is caught
# only in a fetching CONTEXT (a URL attribute, CSS url()/image-set()/@import, a JS network-API call,
# or a `url=` redirect) and only when a hostname char follows the `//`, so a JS `// comment` is not a
# false positive. NOTE: a bare `fetch(x)` / `XMLHttpRequest` with a same-origin, `data:`, or `blob:`
# target is NOT flagged (that is not an external reference; a runtime-built external URL is the
# disclosed obfuscation residual that rung 2 catches).
EGRESS="(https?|wss?|ftp)://|(^|[^a-z])(stun|turns?):[a-z0-9]|@import[^;{]*(https?:)?//[a-z0-9]|(url|image-set|image)[[:space:]]*\([[:space:]]*[\"']?(https?:)?//[a-z0-9]|(src|srcset|imagesrcset|href|xlink:href|action|formaction|poster|background|cite|ping|manifest)[[:space:]]*=[[:space:]]*[\"']?(https?:)?//[a-z0-9]|(^|[^a-z])url[[:space:]]*=[[:space:]]*[\"']?(https?:)?//[a-z0-9]|(fetch|import|importscripts|websocket|eventsource)[[:space:]]*\([[:space:]]*[\"']?(https?:)?//[a-z0-9]"

# The waiver: a BOUNDED, case-SENSITIVE, TRAILING comment. A hit is suppressed only when ITS line
# ends with a real `# egress-ok` / `// egress-ok` / `/* egress-ok */`. The delimiter must sit at
# line-start or after whitespace, so a URL-internal `//` can't act as the comment delimiter.
WAIVER='(^|[[:space:]])(#|//|/\*)[[:space:]]*egress-ok([[:space:]]*\*/)?[[:space:]]*$'

usage() { echo "usage: scan-egress.sh [--allow-binary <glob>]... <file-or-dir> ..." >&2; exit 2; }

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
# A non-regular file (FIFO/socket/device) is tracked separately and NEVER read.
files=()
symlinks=()
binaries=()
specials=()
classify_file() {  # <path> -> files (text/empty) | binaries | specials
  if [ ! -f "$1" ]; then specials+=("$1"); return; fi        # FIFO/socket/device -> never grep (would hang)
  if [ ! -s "$1" ]; then files+=("$1"); return; fi           # empty file: no content, benign
  if LC_ALL=C grep -Iq . "$1" 2>/dev/null; then files+=("$1"); else binaries+=("$1"); fi
}
for p in "${targets[@]}"; do
  if [ -L "$p" ]; then
    symlinks+=("$p")
  elif [ -d "$p" ]; then
    while IFS= read -r -d '' f; do symlinks+=("$f"); done < <(find "$p" -type l -print0 2>/dev/null)
    while IFS= read -r -d '' f; do classify_file "$f"; done < <(find "$p" -type f -print0 2>/dev/null)
    while IFS= read -r -d '' f; do specials+=("$f"); done < <(find "$p" \( -type p -o -type s -o -type b -o -type c \) -print0 2>/dev/null)
  elif [ -e "$p" ]; then
    classify_file "$p"
  else
    echo "scan-egress: no such path: $p" >&2; exit 2
  fi
done
if [ $(( ${#files[@]} + ${#symlinks[@]} + ${#binaries[@]} + ${#specials[@]} )) -lt 1 ]; then
  echo "scan-egress: no scannable files under: ${targets[*]}" >&2; exit 2
fi

violations=0
waived=0
benign=0
for f in ${files[@]+"${files[@]}"}; do
  while IFS= read -r line; do
    [ -n "$line" ] || continue
    n="${line%%:*}"
    body="${line#*:}"
    # Non-fetching URI context: an xmlns / xmlns:* namespace declaration — e.g. inline-SVG
    # xmlns="http://www.w3.org/2000/svg" — is a pure identifier a browser never fetches. Strip ONLY
    # that BOUNDED, quoted value (never an unbounded span — the old <!DOCTYPE ...> strip ate to the
    # first '>' and could launder a real hit); if NO egress survives, it was a namespace URI. A
    # DTD/schema SYSTEM URL is a real external reference and is deliberately NOT stripped (it is
    # fetched by XML consumers).
    stripped="$(printf '%s' "$body" | sed -E \
      -e 's/(^|[^A-Za-z0-9_-])xmlns(:[A-Za-z0-9_.-]+)?[[:space:]]*=[[:space:]]*"[^"]*"/\1/g' \
      -e "s/(^|[^A-Za-z0-9_-])xmlns(:[A-Za-z0-9_.-]+)?[[:space:]]*=[[:space:]]*'[^']*'/\1/g")"
    if ! printf '%s' "$stripped" | grep -Eqi -- "$EGRESS"; then
      benign=$((benign + 1)); echo "NSURI   $f:$n:$body"
      continue
    fi
    if printf '%s' "$body" | grep -Eq -- "$WAIVER"; then
      waived=$((waived + 1)); echo "WAIVED  $f:$n:$body"
    else
      violations=$((violations + 1)); echo "EGRESS  $f:$n:$body"
    fi
  done < <(grep -niE -- "$EGRESS" "$f" || true)
done

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

# Binaries: `grep -a` their strings. An embedded URL fails ALWAYS (a --allow-binary glob must not
# launder a live URL). A URL-free binary is waivable with --allow-binary <glob> (`*` crosses '/', so
# scope the glob tightly — it is a deliberate human review, not a filesystem glob).
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
  hits="$(LC_ALL=C grep -aoiE -- "$EGRESS" "$b" 2>/dev/null | head -5 | tr '\n' ' ' || true)"
  if [ -n "${hits// /}" ]; then
    violations=$((violations + 1)); echo "EGRESS(binary) $b :: $hits"
  elif is_waived_binary "$b"; then
    waived_bin=$((waived_bin + 1)); echo "WAIVED-BINARY $b"
  else
    review_bin=$((review_bin + 1))
    violations=$((violations + 1))
    echo "UNSCANNED(binary) $b (static scan cannot certify; --allow-binary <glob> to waive a reviewed asset)"
  fi
done

echo "--- scan-egress: $violations un-waived, $waived waived, $benign non-fetching URI(s), ${#files[@]} text file(s), ${#symlinks[@]} symlink(s), ${#specials[@]} special, $review_bin binary fail(s), $waived_bin binary waived ---"
if [ "$violations" -ne 0 ]; then
  echo "scan-egress: FAIL — un-waived external reference(s), symlink(s), non-regular file(s), or binary file(s)" >&2
  exit 1
fi
echo "scan-egress: PASS — every file scanned clean or explicitly waived"
exit 0
