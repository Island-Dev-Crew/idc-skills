#!/usr/bin/env bash
# Claude Code PreToolUse guard: blocks destructive git commands before they run.
# Reads hook JSON on stdin; exit 2 blocks (with a stderr message), exit 0 allows.
#
# SCOPE (honest — this is advisory until wired, and a speed-bump even then):
# a defense-in-depth STRING classifier. It quote-aware-tokenizes (shlex), skips
# git's global-option grammar (-C, -c, --no-pager, --git-dir, --work-tree,
# --namespace, long/`=` forms), neutralizes ${IFS}/$IFS word-split tricks, and
# refuses alias definitions (`-c alias.x=push`, `config alias.x '!git push'`) and
# whole-tree pathspecs (`.`, `:/`, `*`, `:(top)`). Quote awareness means a commit
# MESSAGE mentioning a blocked command is NOT over-blocked.
#
# It is NOT a sandbox and CANNOT be one. Documented residuals a string classifier
# cannot close (keep a real OS/repo-level control underneath — this is one layer):
#   - variable/dynamic indirection: `C=git; $C push`, `$(printf push)`, `eval`
#   - `sh -c "..."`, a renamed/copied git binary, base64-then-decode
#   - a persistent alias set in a PRIOR command, then invoked in a later one
#   - malformed hook payloads: extraction fails -> guard OPENS (see below), by
#     design, so a parse error cannot wedge every command.
# Requires `jq` (payload) and `python3` (tokenizer); if either is missing the guard
# degrades to a naive splitter / fail-open rather than wedging the agent — wire it
# only where both exist, and never as the only barrier.
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
        case "$t" in .|:/|:|\*|':(top)'|':/:') danger="git checkout <whole-tree pathspec>" ;; esac
        case "$t" in -f|--force) danger="git checkout --force" ;; esac
      done
      ;;
    restore)
      local worktree=0 staged=0
      for (( k=i+1; k<NW; k++ )); do
        t="$(normalize_word "${WORDS[$k]}")"
        case "$t" in .|:/|:|\*|':(top)'|':/:') danger="git restore <whole-tree pathspec>" ;; esac
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
# `git p`) or `git config alias.p push`, including `!`-prefixed shell-command aliases
# that run arbitrary commands. A single-command classifier cannot see the later `git p`,
# but it CAN refuse the DEFINITION. Detected in TOKEN position (only after a real `-c` or
# `config`), NOT by scanning arbitrary text — so a commit message that merely mentions
# "alias.push" no longer false-positives (the fix for the review's over-block finding).
alias_value_dangerous() {   # <value>  (quotes/backslashes already stripped by caller)
  case "$1" in
    \!*)                                                  return 0 ;;  # shell-command alias
    *push*|*reset*|*clean*|*checkout*|*restore*|*branch*) return 0 ;;  # re-point to blocked op
    *)                                                    return 1 ;;
  esac
}
detect_alias_injection() {   # reads WORDS/NW; calls block() on a dangerous alias definition
  local a b nv val v2 v3
  for (( a=0; a<NW; a++ )); do
    nv="$(normalize_word "${WORDS[$a]}")"
    if [ "$nv" = "-c" ] && [ $(( a + 1 )) -lt "$NW" ]; then
      val="$(normalize_word "${WORDS[$(( a + 1 ))]}")"
      case "$val" in alias.*=*) alias_value_dangerous "${val#*=}" && block "matched: alias injection (-c alias to blocked op)" ;; esac
    fi
    if [ "$nv" = "config" ]; then
      for (( b=a+1; b<NW; b++ )); do
        val="$(normalize_word "${WORDS[$b]}")"
        case "$val" in
          alias.*=*) alias_value_dangerous "${val#*=}" && block "matched: alias injection (config alias to blocked op)" ;;
          alias.*)
            v2=""; v3=""
            [ $(( b + 1 )) -lt "$NW" ] && v2="$(normalize_word "${WORDS[$(( b + 1 ))]}")"
            [ $(( b + 2 )) -lt "$NW" ] && v3="$(normalize_word "${WORDS[$(( b + 2 ))]}")"
            alias_value_dangerous "$v2 $v3" && block "matched: alias injection (config alias to blocked op)"
            ;;
        esac
      done
    fi
  done
}

# Tokenize with QUOTE AWARENESS (shlex), not bash word-splitting. This is the fix for
# the review's over-block finding: a quoted arg — e.g. a commit MESSAGE that mentions
# "git config alias.p push" — stays ONE token and cannot trip the alias detector. shlex
# also emits ; && || | & as their own tokens, so we segment on REAL separators, never on
# a separator buried inside quotes. Requires python3; falls back to a naive splitter
# (louder, less precise) if python3 is missing or the quotes are unbalanced.
tokens=()
if command -v python3 >/dev/null 2>&1; then
  while IFS= read -r tok || [ -n "$tok" ]; do tokens+=("$tok"); done < <(python3 - "$cmd" <<'PY' 2>/dev/null
import shlex, sys
s = sys.argv[1]
try:
    lx = shlex.shlex(s, posix=True, punctuation_chars=';&|')
    lx.whitespace_split = True
    lx.commenters = ''            # do not drop anything after '#'
    toks = list(lx)
except ValueError:                # unbalanced quotes etc.
    toks = s.split()
sys.stdout.write("\n".join(t for t in toks if t != ""))
PY
  )
fi
if [ "${#tokens[@]}" -eq 0 ]; then          # python3 absent → naive fallback
  while IFS= read -r seg; do
    for w in $seg; do tokens+=("$w"); done
    tokens+=(';')
  done <<< "$(printf '%s' "$cmd" | tr ';&|' '\n')"
fi

# Walk tokens; a separator token flushes the current segment (alias detection + classify
# each git/*/git command word). block() exits on the first dangerous match.
flush_segment() {
  NW=${#WORDS[@]}
  [ "$NW" -gt 0 ] || return 0
  detect_alias_injection
  local gi
  for (( gi=0; gi<NW; gi++ )); do
    case "$(normalize_word "${WORDS[$gi]}")" in
      git|*/git) classify_from "$gi" ;;
    esac
  done
  WORDS=()
}
WORDS=()
for tok in "${tokens[@]}"; do
  case "$tok" in
    ';'|'&'|'&&'|'|'|'||') flush_segment ;;
    *) WORDS+=("$tok") ;;
  esac
done
flush_segment

exit 0
