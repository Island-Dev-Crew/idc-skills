#!/usr/bin/env bash
# Assemble console.lock from exact HEAD blobs, never from mutable worktree globs.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
GIT="${IDC_CONSOLE_GIT:-$(command -v git 2>/dev/null || true)}"
case "$GIT" in /*) ;; *) printf 'refusing to assemble: absolute Git executable required\n' >&2; exit 2 ;; esac

"$GIT" rev-parse --is-inside-work-tree >/dev/null 2>&1 || {
  printf 'refusing to assemble: not a git repository\n' >&2
  exit 2
}
if ! "$GIT" diff --quiet || ! "$GIT" diff --cached --quiet; then
  printf 'refusing to assemble: uncommitted changes\n' >&2
  exit 2
fi

TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/idc-console.XXXXXXXX")"
chmod 700 "$TMP_ROOT"
trap 'rm -rf "$TMP_ROOT"' EXIT

"$GIT" ls-files --others --exclude-standard -z -- console/blocks/ > "$TMP_ROOT/untracked"
[ ! -s "$TMP_ROOT/untracked" ] || {
  printf 'refusing to assemble: untracked console block entries exist\n' >&2
  exit 2
}
{
  "$GIT" ls-files --others --ignored --exclude-standard -z -- console/blocks/
  "$GIT" ls-files -ci --exclude-standard -z -- console/blocks/
} > "$TMP_ROOT/ignored"
[ ! -s "$TMP_ROOT/ignored" ] || {
  printf 'refusing to assemble: ignored console block entries exist\n' >&2
  exit 2
}

"$GIT" ls-files -v -z -- console/blocks/ > "$TMP_ROOT/index-flags"
while IFS= read -r -d '' entry; do
  tag="${entry%% *}"
  case "$tag" in
    S|[a-z])
      printf 'refusing to assemble: skip-worktree or assume-unchanged block flag exists\n' >&2
      exit 2
      ;;
  esac
done < "$TMP_ROOT/index-flags"

GIT_NO_REPLACE_OBJECTS=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  "$GIT" ls-tree -rz --full-tree HEAD -- console/blocks/ > "$TMP_ROOT/head-tree"
declare -a OBJECTS=()
declare -a NAMES=()
while IFS= read -r -d '' entry; do
  metadata="${entry%%$'\t'*}"
  path="${entry#*$'\t'}"
  IFS=' ' read -r mode type object_id <<< "$metadata"
  relative="${path#console/blocks/}"
  case "$relative" in
    ''|*/*|*[!A-Za-z0-9._-]*|*.md.md) printf 'refusing to assemble: unsafe block path in HEAD\n' >&2; exit 2 ;;
    *.md) ;;
    *) printf 'refusing to assemble: non-Markdown block in HEAD\n' >&2; exit 2 ;;
  esac
  if [ "$type" != "blob" ] || { [ "$mode" != "100644" ] && [ "$mode" != "100755" ]; }; then
    printf 'refusing to assemble: unsupported block object in HEAD\n' >&2
    exit 2
  fi
  lowered="$(printf '%s' "$relative" | tr '[:upper:]' '[:lower:]')"
  for prior in "${NAMES[@]-}"; do
    [ "$prior" != "$lowered" ] || {
      printf 'refusing to assemble: case-folded block collision in HEAD\n' >&2
      exit 2
    }
  done
  NAMES+=("$lowered")
  OBJECTS+=("$object_id")
done < "$TMP_ROOT/head-tree"
[ "${#OBJECTS[@]}" -gt 0 ] || { printf 'refusing to assemble: HEAD has no blocks\n' >&2; exit 2; }

: > "$TMP_ROOT/assembled"
for object_id in "${OBJECTS[@]}"; do
  GIT_NO_REPLACE_OBJECTS=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
    "$GIT" cat-file blob "$object_id" >> "$TMP_ROOT/assembled"
done
SHA="$(shasum -a 256 "$TMP_ROOT/assembled" | awk '{print $1}')"
HEAD_COMMIT="$(GIT_NO_REPLACE_OBJECTS=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  "$GIT" rev-parse --verify 'HEAD^{commit}')"
BLOCKS_TREE="$(GIT_NO_REPLACE_OBJECTS=1 GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null \
  "$GIT" rev-parse --verify 'HEAD:console/blocks')"
{
  printf '<!-- console.lock - assembled from blocks-tree:%s - sha256:%s -->\n\n' "$BLOCKS_TREE" "$SHA"
  cat "$TMP_ROOT/assembled"
} > "$TMP_ROOT/console.lock"
chmod 644 "$TMP_ROOT/console.lock"
mv "$TMP_ROOT/console.lock" console/console.lock
printf 'assembled console: sha256:%s @ %s\n' "$SHA" "$HEAD_COMMIT"
