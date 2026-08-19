#!/usr/bin/env bash
# Claude Code PreToolUse guard: blocks destructive git commands before they run.
# Reads hook JSON on stdin; exit 2 blocks (with a stderr message), exit 0 allows.
#
# SCOPE (honest — this is advisory until wired, and a speed-bump even then):
# a defense-in-depth STRING classifier. It parses git's global-option grammar,
# so a destructive subcommand cannot hide behind options like -C, -c,
# --no-pager, --git-dir, --work-tree, --namespace, or long/`=` forms, on ANY of
# the blocked subcommands. It is NOT a sandbox: `eval`, `sh -c "..."`, an alias,
# command substitution `$(...)`, or a renamed/copied git binary can still reach
# git. Keep a real OS/repo-level control underneath; never treat this as the
# only barrier. Requires `jq`; if `jq` is missing the guard says so and OPENS
# (fail-open) so it cannot wedge every command — wire it only where jq exists.
set -euo pipefail

cmd="$(cat | jq -r '.tool_input.command // .toolInput.command // .command // empty' 2>/dev/null || true)"
if [ -z "${cmd:-}" ]; then
  echo "block-dangerous-git: no command found in hook payload (guard OPEN)" >&2
  exit 0
fi

block() {
  echo "BLOCKED: you do not have authority to run destructive git commands ($1)." >&2
  echo "If this is intended, the human runs it." >&2
  exit 2
}

# Normalize a single shell word conservatively. Shell permits adjacent quoted
# fragments and backslash escapes inside one word (`p'u'sh`, `pu\sh`, `g''it`).
# Removing those syntax characters recreates the direct word for classification;
# it may over-block an exotic read-only spelling, which is safer than a bypass.
normalize_word() {
  local s="$1"
  s="${s//\\/}"
  s="${s//\'/}"
  s="${s//\"/}"
  printf '%s' "$s"
}

# git global options that CONSUME the following token as their value.
is_value_opt() {
  case "$1" in
    -C|-c|--git-dir|--work-tree|--namespace|--super-prefix|--exec-path|--config-env|--attr-source) return 0 ;;
    *) return 1 ;;
  esac
}

# WORDS/NW hold the current segment's tokens. classify_from <git-index> skips
# git's global options, reads the subcommand, and calls block() if dangerous.
WORDS=()
NW=0
classify_from() {
  local i=$(( $1 + 1 )) t k danger="" sub
  while [ "$i" -lt "$NW" ]; do
    t="$(normalize_word "${WORDS[$i]}")"
    case "$t" in
      --)      i=$(( i + 1 )); break ;;      # explicit end of options
      --*=*)   i=$(( i + 1 )); continue ;;   # --opt=value (single token)
      -?*)     if is_value_opt "$t"; then i=$(( i + 2 )); else i=$(( i + 1 )); fi; continue ;;
      *)       break ;;                       # first non-option = subcommand
    esac
  done
  [ "$i" -lt "$NW" ] || return 0
  sub="$(normalize_word "${WORDS[$i]}")"
  case "$sub" in
    push)  danger="git push" ;;
    reset) for (( k=i+1; k<NW; k++ )); do [ "$(normalize_word "${WORDS[$k]}")" = "--hard" ] && danger="git reset --hard"; done ;;
    clean) for (( k=i+1; k<NW; k++ )); do
             t="$(normalize_word "${WORDS[$k]}")"
             case "$t" in -*f*) case "$t" in *n*) : ;; *) danger="git clean -f" ;; esac ;; esac
           done ;;
    branch)
      local delete=0 force=0
      for (( k=i+1; k<NW; k++ )); do
        t="$(normalize_word "${WORDS[$k]}")"
        [ "$t" = "-D" ] && danger="git branch -D"
        [ "$t" = "--delete" ] && delete=1
        [ "$t" = "--force" ] && force=1
      done
      [ "$delete" -eq 1 ] && [ "$force" -eq 1 ] && danger="git branch --delete --force"
      ;;
    checkout)
      for (( k=i+1; k<NW; k++ )); do
        t="$(normalize_word "${WORDS[$k]}")"
        [ "$t" = "." ] && danger="git checkout ."
        case "$t" in -f|--force) danger="git checkout --force" ;; esac
      done
      ;;
    restore)
      local worktree=0 staged=0
      for (( k=i+1; k<NW; k++ )); do
        t="$(normalize_word "${WORDS[$k]}")"
        [ "$t" = "." ] && danger="git restore ."
        [ "$t" = "--worktree" ] && worktree=1
        [ "$t" = "--staged" ] && staged=1
      done
      [ "$worktree" -eq 1 ] && [ "$staged" -eq 1 ] && danger="git restore --worktree --staged"
      ;;
  esac
  [ -n "$danger" ] && block "matched: $danger"
  return 0
}

# Split the command on shell separators (; & | and && ||), then classify each
# segment. `<<<` keeps the loop in this shell so block()'s exit propagates.
continuation=$'\\\n'
cmd="${cmd//$continuation/}"

# Neutralize $IFS / ${IFS...} expansions, which re-introduce a word boundary only at
# runtime (`git${IFS}push`). Replacing them with a space lets the classifier see the
# real tokens (`git push`) instead of one opaque word it would wave through.
cmd="$(printf '%s' "$cmd" | sed -E 's/\$\{IFS[^}]*\}/ /g; s/\$IFS/ /g')"

# Alias injection: redefining a short name to a blocked op — `-c alias.p=push` (then
# `git p`) or `git config alias.p push`. A single-command classifier cannot see the
# later `git p`, but it CAN refuse the DEFINITION when its value carries a blocked verb.
# Strip quotes/backslashes first so `alias.p="push"` and `alias.p=pu\sh` are caught too.
alias_flat="$(printf '%s' "$cmd" | tr -d '\042\047\134')"
if printf '%s' "$alias_flat" | grep -Eiq 'alias\.[A-Za-z0-9_.-]+[ =]+(git[ ]+)?(push|reset|clean|checkout|restore|branch)'; then
  block "matched: git alias defined to a blocked op (alias injection)"
fi

while IFS= read -r seg; do
  [ -n "$seg" ] || continue
  WORDS=()
  read -r -a WORDS <<< "$seg" || true
  NW=${#WORDS[@]}
  [ "$NW" -gt 0 ] || continue
  for (( gi=0; gi<NW; gi++ )); do
    case "$(normalize_word "${WORDS[$gi]}")" in
      git|*/git) classify_from "$gi" ;;
    esac
  done
done <<< "$(printf '%s' "$cmd" | tr ';&|' '\n')"

exit 0
