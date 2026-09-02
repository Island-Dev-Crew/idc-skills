#!/usr/bin/env bash
# garnet-evidence-packet.sh - assemble a Garnet evidence packet a reviewer recomputes.
#
#   garnet-evidence-packet.sh <slug> <base-ref> [file.garnet ...]
#
# Run from inside the repository, on the branch that holds the change. Every rung
# is captured with its exit code; a red rung is evidence, an absent tool is
# recorded as unverified (never green), and the packet is rolled up into
# packet.sha256. Layout is evidence-packet's: head.txt diff.patch ladder.md out/
# packet.sha256.
#
# Environment (all optional):
#   GE_RUNGS       space-separated rung allowlist (default: every rung below)
#   GE_OUT         packet root, repo-relative (default: evidence)
#   GE_STRICT      1 -> exit 1 unless every rung is green
#   GE_REDACT_SED  repo-relative sed -E script with extra redaction rules
#
# Rungs:
#   worktree          git status --porcelain (excluding the packet root); red when dirty
#   garnet-version    garnet version
#   garnet-check      garnet check --format json <file>   at HEAD, and at base (discriminator pair)
#   garnet-diff-caps  garnet diff-caps --machine <base-file> <head-file>
#   garnet-build      garnet build --deterministic <file> (manifest copied into out/)
#   garnet-seal       garnet seal <file> --out <scratch>/<slug>.seal.json (copied into out/)
#   fmt               cargo fmt --all -- --check
#   whitespace        git diff --check <base-sha> <head-sha>
#   test              cargo test --workspace --no-fail-fast
#   readiness         python3 scripts/garnet_v0_8_1_release_readiness.py --gate
set -euo pipefail

usage() {
  echo "usage: garnet-evidence-packet.sh <slug> <base-ref> [file.garnet ...]" >&2
  echo "       GE_RUNGS, GE_OUT, GE_STRICT, GE_REDACT_SED - see the header of this script" >&2
}
case "${1:-}" in -h|--help) usage; exit 0 ;; esac
if [ "$#" -lt 2 ]; then usage; exit 2; fi
SLUG="$1"
BASE_REF="$2"
shift 2

case "$SLUG" in
  ''|*/*|.*|*[!A-Za-z0-9._-]*)
    echo "garnet-evidence: slug must match [A-Za-z0-9._-], no slash, no leading dot: '$SLUG'" >&2
    exit 2 ;;
esac

if command -v shasum >/dev/null 2>&1; then
  sha256_stdin() { shasum -a 256 | cut -d' ' -f1; }
elif command -v sha256sum >/dev/null 2>&1; then
  sha256_stdin() { sha256sum | cut -d' ' -f1; }
else
  echo "garnet-evidence: neither shasum nor sha256sum is on PATH" >&2
  exit 2
fi
sha256_file() { sha256_stdin < "$1"; }

REPO="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "garnet-evidence: not inside a git repository" >&2
  exit 2
}
cd "$REPO"
if ! git rev-parse --verify --quiet "${BASE_REF}^{commit}" >/dev/null; then
  echo "garnet-evidence: base '$BASE_REF' is not resolvable here; make it present first (evidence-packet's guard rung names the remedy)" >&2
  exit 2
fi
HEAD_SHA="$(git rev-parse HEAD)"
BASE_SHA="$(git merge-base "$BASE_REF" HEAD)"

DEFAULT_RUNGS="worktree garnet-version garnet-check garnet-diff-caps garnet-build garnet-seal fmt whitespace test readiness"
RUNGS="${GE_RUNGS:-$DEFAULT_RUNGS}"
OUT_ROOT="${GE_OUT:-evidence}"
case "$OUT_ROOT" in /*|~*|..*) echo "garnet-evidence: GE_OUT must be repo-relative: '$OUT_ROOT'" >&2; exit 2 ;; esac
PACKET="$OUT_ROOT/$SLUG"
PACKET_ABS="$REPO/$PACKET"
if [ -e "$PACKET_ABS" ]; then
  echo "garnet-evidence: packet directory exists; refusing to overwrite: $PACKET" >&2
  exit 2
fi

REDACT_EXTRA=""
REDACT_EXTRA_SHA=""
if [ -n "${GE_REDACT_SED:-}" ]; then
  case "$GE_REDACT_SED" in /*|~*) echo "garnet-evidence: GE_REDACT_SED must be repo-relative" >&2; exit 2 ;; esac
  if [ ! -f "$GE_REDACT_SED" ] || [ -L "$GE_REDACT_SED" ]; then
    echo "garnet-evidence: GE_REDACT_SED must be a regular file: $GE_REDACT_SED" >&2
    exit 2
  fi
  REDACT_EXTRA="$REPO/$GE_REDACT_SED"
  REDACT_EXTRA_SHA="$(sha256_file "$GE_REDACT_SED")"
fi

WORK="$(mktemp -d "${TMPDIR:-/tmp}/garnet-evidence.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
mkdir -p "$WORK/base" "$WORK/head" "$PACKET_ABS/out"
HOME_DIR="${HOME:-}"

# builtin-v1: machine-local paths to placeholders, then typed secret masks.
normalize() {
  sed -e "s,$REPO,<repo>,g" -e "s,$WORK,<work>,g" \
    | { if [ -n "$HOME_DIR" ]; then sed -e "s,$HOME_DIR,<home>,g"; else cat; fi; } \
    | sed -E \
        -e 's,(Bearer[[:space:]]+)[A-Za-z0-9._~+/=-]+,\1<redacted:bearer-token>,g' \
        -e 's,([Aa]uthorization:[[:space:]]*)[^[:space:]].*$,\1<redacted:authorization-header>,' \
        -e 's,AKIA[0-9A-Z]{16},<redacted:aws-access-key-id>,g' \
        -e 's|gh[pousr]_[A-Za-z0-9]{20,}|<redacted:github-token>|g' \
        -e 's,-----BEGIN [A-Z ]*PRIVATE KEY-----,<redacted:private-key-block>,g' \
    | { if [ -n "$REDACT_EXTRA" ]; then sed -E -f "$REDACT_EXTRA"; else cat; fi; }
}

wants() { case " $RUNGS " in *" $1 "*) return 0 ;; esac; return 1; }
slugify() { printf '%s' "$1" | tr '/' '_'; }

GREEN=0; RED=0; UNVERIFIED=0; NA=0
ROWS="$WORK/rows.tsv"
: > "$ROWS"

# run_rung <name> <proves> <command...>   - captures output, EXIT=, STATUS=
run_rung() {
  local name="$1" proves="$2"
  shift 2
  local out="$PACKET_ABS/out/$name.txt" rc=0 status=ran mark shown
  shown="$(printf '%s' "$*" | normalize)"
  if ! command -v "$1" >/dev/null 2>&1; then
    { printf '$ %s\n' "$*"; printf '%s: command not found on PATH\n' "$1"; } | normalize > "$out"
    rc=127; status=tool-absent
  else
    { printf '$ %s\n' "$*"; "$@" 2>&1; } | normalize > "$out" || rc=$?
  fi
  printf 'EXIT=%s\nSTATUS=%s\n' "$rc" "$status" >> "$out"
  case "$status:$rc" in
    ran:0)         mark=green;      GREEN=$((GREEN + 1)) ;;
    tool-absent:*) mark=unverified; UNVERIFIED=$((UNVERIFIED + 1)) ;;
    *)             mark=red;        RED=$((RED + 1)) ;;
  esac
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "$shown" "out/$name.txt" "$rc" "$mark" "$proves" >> "$ROWS"
  echo "  $mark  $name (exit $rc) -> out/$name.txt"
}

# skip_rung <name> <reason> <proves>   - a rung with no applicable input
skip_rung() {
  local name="$1" reason="$2" proves="$3"
  local out="$PACKET_ABS/out/$name.txt"
  printf '%s\nEXIT=\nSTATUS=not-applicable\n' "$reason" > "$out"
  NA=$((NA + 1))
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$name" "-" "out/$name.txt" "-" "n/a" "$proves" >> "$ROWS"
  echo "  n/a  $name ($reason)"
}

# invoked indirectly: run_rung worktree ... worktree_clean
# shellcheck disable=SC2329
worktree_clean() {
  local dirty
  dirty="$(git status --porcelain --untracked-files=all -- ":(exclude)$OUT_ROOT/")"
  printf '%s\n' "$dirty"
  [ -z "$dirty" ]
}

# --- sources: explicit list, or every .garnet added/modified between base and HEAD
FILES=()
if [ "$#" -gt 0 ]; then
  for f in "$@"; do
    case "$f" in "$REPO"/*) f="${f#"$REPO"/}" ;; esac
    FILES+=("$f")
  done
else
  while IFS= read -r f; do
    [ -n "$f" ] && FILES+=("$f")
  done < <(git diff --name-only --diff-filter=AMR "$BASE_SHA" "$HEAD_SHA" -- '*.garnet')
fi

echo "garnet-evidence: packet $PACKET  head=$HEAD_SHA  base=$BASE_REF ($BASE_SHA)"
printf '%s\n' "$HEAD_SHA" > "$PACKET_ABS/head.txt"
git diff "$BASE_SHA" "$HEAD_SHA" | normalize > "$PACKET_ABS/diff.patch"

# --- repository rungs that must see the real tree
if wants worktree; then
  run_rung worktree "the attested HEAD is what was measured - the working tree is clean" worktree_clean
fi

# --- Garnet rungs run in the scratch dir on copies of the attested commits
cd "$WORK"
if wants garnet-version; then
  run_rung garnet-version "the exact Garnet toolchain that produced the garnet rungs" garnet version
fi
SOURCE_LIST=""
if [ "${#FILES[@]}" -eq 0 ]; then
  for r in garnet-check garnet-diff-caps garnet-build garnet-seal; do
    if wants "$r"; then skip_rung "$r" "no .garnet source added or modified between base and HEAD" "-"; fi
  done
fi
for f in ${FILES[@]+"${FILES[@]}"}; do
  s="$(slugify "${f%.garnet}")"
  SOURCE_LIST="$SOURCE_LIST $f"
  if ! git -C "$REPO" show "$HEAD_SHA:$f" > "$WORK/head/$s.garnet" 2>/dev/null; then
    echo "garnet-evidence: $f is not present at HEAD $HEAD_SHA" >&2
    exit 2
  fi
  absent_note=""
  if git -C "$REPO" cat-file -e "$BASE_SHA:$f" 2>/dev/null; then
    git -C "$REPO" show "$BASE_SHA:$f" > "$WORK/base/$s.garnet"
  else
    : > "$WORK/base/$s.garnet"
    absent_note=" ($f is absent at base; diffed against an empty file, so every declared cap shows as gained)"
  fi
  if wants garnet-check; then
    run_rung "garnet-check.$s" "the static capability check accepts $f at HEAD as declared (exit 1 = undeclared capability-bearing call or parse error)" \
      garnet check --format json "$WORK/head/$s.garnet"
    if [ -n "$absent_note" ]; then
      skip_rung "garnet-check-base.$s" "$f is absent at base" "discriminator pair for $f"
    else
      run_rung "garnet-check-base.$s" "the same check at base - the discriminator pair for $f (red here, green at HEAD = the change proving itself)" \
        garnet check --format json "$WORK/base/$s.garnet"
    fi
  fi
  if wants garnet-diff-caps; then
    run_rung "garnet-diff-caps.$s" "declared authority of $f did not widen from base to HEAD; red names each gained cap and must be accepted on purpose or narrowed; declared-surface-only$absent_note" \
      garnet diff-caps --machine "$WORK/base/$s.garnet" "$WORK/head/$s.garnet"
  fi
  if wants garnet-build; then
    run_rung "garnet-build.$s" "a deterministic build manifest (source_hash, ast_hash) for $f; the copy in out/ must equal the reviewer's" \
      garnet build --deterministic "$WORK/head/$s.garnet"
    if [ -f "$WORK/head/$s.garnet.manifest.json" ]; then
      normalize < "$WORK/head/$s.garnet.manifest.json" > "$PACKET_ABS/out/garnet-build.$s.manifest.json"
    fi
  fi
  if wants garnet-seal; then
    run_rung "garnet-seal.$s" "an in-toto seal statement for $f, copied to out/garnet-seal.$s.json; UNSIGNED unless cosign is on PATH (the stderr note is captured)" \
      garnet seal "$WORK/head/$s.garnet" --out "$WORK/head/$s.seal.json"
    if [ -f "$WORK/head/$s.seal.json" ]; then
      normalize < "$WORK/head/$s.seal.json" > "$PACKET_ABS/out/garnet-seal.$s.json"
    fi
  fi
done
cd "$REPO"

# --- the project ladder (Garnet repo CLAUDE.md), from the repo root
if wants fmt; then
  run_rung fmt "rustfmt accepts the workspace unchanged" cargo fmt --all -- --check
fi
if wants whitespace; then
  run_rung whitespace "no whitespace errors in the change range" git diff --check "$BASE_SHA" "$HEAD_SHA"
fi
if wants test; then
  run_rung test "the workspace test suite is green at HEAD" cargo test --workspace --no-fail-fast
fi
if wants readiness; then
  run_rung readiness "the v0.8.1 release-readiness gate passes at HEAD" python3 scripts/garnet_v0_8_1_release_readiness.py --gate
fi

# --- ladder.md
{
  echo "# Ladder - $SLUG"
  echo
  echo "- head: $HEAD_SHA"
  echo "- base: $BASE_REF (merge-base $BASE_SHA)"
  echo "- rungs requested: $RUNGS"
  if [ -n "$SOURCE_LIST" ]; then echo "- garnet sources:$SOURCE_LIST"; else echo "- garnet sources: none"; fi
  if [ -n "$REDACT_EXTRA" ]; then
    echo "- redaction: builtin-v1 + $GE_REDACT_SED (sha256 $REDACT_EXTRA_SHA)"
  else
    echo "- redaction: builtin-v1"
  fi
  echo "  builtin-v1 = repo root, scratch dir, home to <repo> <work> <home>; Bearer tokens, Authorization headers, AWS access key ids, GitHub tokens, PRIVATE KEY block headers to typed placeholders"
  echo "- status: green = ran, exit 0; red = ran, non-zero (evidence, not a failed packet); unverified = tool absent, the rung did not run and proves nothing; n/a = no applicable input. verified is not a status this file carries - verification is the reviewer's recompute from a fresh clone."
  echo "- totals: green=$GREEN red=$RED unverified=$UNVERIFIED n/a=$NA"
  echo
  echo "| rung | command | out | exit | status | proves |"
  echo "|---|---|---|---|---|---|"
  awk -F '\t' '{ printf "| `%s` | `%s` | `%s` | %s | %s | %s |\n", $1, $2, $3, $4, $5, $6 }' "$ROWS"
  echo
  echo "Recompute: fresh clone, git checkout $HEAD_SHA, run this script with GE_RUNGS=\"$RUNGS\" and base $BASE_REF, compare exit codes exactly and out/ after the redaction rule above."
} > "$PACKET_ABS/ladder.md"

# --- roll-up: sorted listing so the fingerprint reproduces on a fresh clone
(
  cd "$PACKET_ABS"
  find . -type f | LC_ALL=C sort | while IFS= read -r p; do
    printf '%s  %s\n' "$(sha256_file "$p")" "$p"
  done | sha256_stdin > "$WORK/packet.sha256"
)
cp "$WORK/packet.sha256" "$PACKET_ABS/packet.sha256"
PACKET_SHA="$(cat "$PACKET_ABS/packet.sha256")"
echo "garnet-evidence: $PACKET packet.sha256=$PACKET_SHA green=$GREEN red=$RED unverified=$UNVERIFIED n/a=$NA"
if [ "${GE_STRICT:-0}" = 1 ] && [ $((RED + UNVERIFIED)) -gt 0 ]; then
  exit 1
fi
exit 0
