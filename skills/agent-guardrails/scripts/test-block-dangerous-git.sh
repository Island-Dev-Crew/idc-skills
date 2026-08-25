#!/usr/bin/env bash
# Fixture matrix for block-dangerous-git.sh. Sends inert JSON command strings to
# the guard on stdin and asserts the exit code. NO git command is ever executed;
# the guard only classifies strings. Requires jq. Exit 0 = all fixtures pass.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GUARD="$HERE/block-dangerous-git.sh"
pass=0; fail=0

check() { # <expected-exit> <command-string> <label>
  local want="$1" cmd="$2" label="$3" got
  printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$cmd" | jq -R -s .)" \
    | env -i PATH="$PATH" HOME="${HOME:-/tmp}" TMPDIR="${TMPDIR:-/tmp}" bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

check_inherited() { # <expected-exit> <command-string> <label> [NAME=value ...]
  # Unlike command-string assignments, these variables exist in the GUARD PROCESS environment.
  # That is the exact surface Git inherits when the hook host itself was launched with runtime
  # config. `env` receives only literal NAME=value argv; it never evaluates a value.
  local want="$1" cmd="$2" label="$3" got; shift 3
  printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$cmd" | jq -R -s .)" \
    | env -i PATH="$PATH" HOME="${HOME:-/tmp}" TMPDIR="${TMPDIR:-/tmp}" "$@" bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

check_inherited_count_bound() { # <expected-exit> <count> <label>
  local want="$1" count="$2" label="$3" got i=0
  local cfg=("GIT_CONFIG_COUNT=$count")
  while [ "$i" -lt "$count" ]; do
    cfg+=("GIT_CONFIG_KEY_$i=user.name" "GIT_CONFIG_VALUE_$i=safe")
    i=$((i + 1))
  done
  printf '{"tool_input":{"command":"git status"}}' \
    | env -i PATH="$PATH" HOME="${HOME:-/tmp}" TMPDIR="${TMPDIR:-/tmp}" "${cfg[@]}" bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

check_inherited_parameters_bound() { # <expected-exit> <entry-count> <label>
  local want="$1" count="$2" label="$3" got i=0 raw=""
  while [ "$i" -lt "$count" ]; do
    raw="$raw'user.k$i'='safe' "
    i=$((i + 1))
  done
  printf '{"tool_input":{"command":"git status"}}' \
    | env -i PATH="$PATH" HOME="${HOME:-/tmp}" TMPDIR="${TMPDIR:-/tmp}" \
      "GIT_CONFIG_PARAMETERS=$raw" bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

check_strict() { # <expected-exit> <command-string> <label>
  local want="$1" cmd="$2" label="$3" got
  printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$cmd" | jq -R -s .)" \
    | env -i PATH="$PATH" HOME="${HOME:-/tmp}" TMPDIR="${TMPDIR:-/tmp}" \
      IDC_GUARD_STRICT=1 bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

CANARY_DIR="$(mktemp -d)"
trap 'rm -rf "$CANARY_DIR"' EXIT

echo "== must BLOCK (exit 2) — plain forms =="
check 2 'git push origin main'                 'plain push'
check 2 'git reset --hard HEAD~1'              'reset --hard'
check 2 'git clean -fd'                        'clean -fd'
check 2 'git branch -D feature'               'branch -D'
check 2 'git checkout .'                       'checkout .'
check 2 'git restore .'                        'restore .'

echo "== must BLOCK (exit 2) — global-option bypasses (F-01) =="
check 2 'git -C /tmp push origin main'         '-C then push'
check 2 'git --no-pager push'                  '--no-pager push'
check 2 'git -c user.name=x push'             '-c k=v push'
check 2 'git --git-dir=/tmp/.git push'         '--git-dir= push'
check 2 'git --git-dir /tmp/.git push'         '--git-dir <sp> push'
check 2 'git --work-tree=/tmp push'            '--work-tree= push'
check 2 'git -C /tmp reset --hard'             '-C then reset --hard'
check 2 'git -c x=y clean -fd'                'globals then clean -fd'
check 2 '/usr/bin/git push'                    'full-path git push'
check 2 'echo hi && git -C /r push'            'after && with -C'
check 2 'git "push"'                           'quoted subcommand'
check 2 'GIT_DIR=/x git push'                  'env prefix then push'

echo "== must BLOCK (exit 2) — shell-word and long-form bypasses (F-02) =="
check 2 "git p'u'sh origin main"              'single-quote concatenated push'
check 2 'git pu\sh origin main'                'backslash-concatenated push'
check 2 "g''it push origin main"              'quote-concatenated git executable'
check 2 'git p"u"sh origin main'              'double-quote concatenated push'
check 2 "git 'pu'sh origin main"              'mixed quoted push'
check 2 $'git \\\npush origin main'           'line-continuation push'
check 2 'git branch --delete --force feature'  'branch long delete plus force'
check 2 'git checkout --force feature'         'checkout force'
check 2 'git restore --worktree --staged f'    'restore worktree plus staged'

echo "== must BLOCK (exit 2) — 2.0.3 hardening: IFS word-split + alias injection =="
# shellcheck disable=SC2016  # ${IFS} is a literal test-INPUT string; it must NOT expand here
check 2 'git${IFS}push origin main'            'IFS word-split push'
# shellcheck disable=SC2016
check 2 'git${IFS}reset --hard'               'IFS word-split reset --hard'
check 2 'git -c alias.p=push p'                'alias injection via -c (push)'
check 2 'git -c alias.co=checkout co .'        'alias injection via -c (checkout)'
check 2 'git config alias.p push'              'persistent alias definition to push'
check 2 'git config alias.nuke "reset --hard"' 'persistent alias definition to reset --hard'

echo "== must BLOCK (exit 2) — 2.0.3 review round 2: !shell aliases + whole-tree pathspec =="
check 2 "git config alias.deploy '!git push'"  'shell-command alias (!git push)'
check 2 "git -c alias.x='!git reset --hard' x" 'shell-command alias via -c'
check 2 'git checkout :/'                       'checkout whole-tree pathspec :/'
check 2 'git restore :/'                        'restore whole-tree pathspec :/'
check 2 "git checkout '*'"                      'checkout glob pathspec *'
check 2 'git checkout HEAD -- :/'               'checkout HEAD whole-tree'

echo "== must BLOCK (exit 2) — 2.0.3 review round 3 (Codex re-verify probes) =="
check 2 $'echo ok\ngit push origin main'       'multiline: inert line then git push'
check 2 $'true\ngit reset --hard'              'multiline: reset --hard on 2nd line'
check 2 'git checkout ./'                       'checkout ./ (whole tree)'
check 2 'git checkout ./.'                      'checkout ./. (whole tree)'
check 2 "git checkout ':(top,glob)**'"          'checkout magic pathspec :(top,glob)**'
check 2 'git branch -d -f feature'              'branch -d -f (force delete, split flags)'
check 2 'git branch -df feature'                'branch -df (force delete, bundled)'
check 2 'git branch -fd feature'                'branch -fd (force delete, bundled reversed)'
check 2 'git.exe push origin main'              'git.exe push (Windows binary name)'
check 2 'git -calias.p=push p origin main'      'alias injection via glued -calias.p=push'
check 2 'foo && git.exe checkout .'             'git.exe checkout . after &&'
check 2 'x=1 git push'                          'env-assignment prefix then push'
check 2 'git config alias.co checkout'          'config alias.co=checkout (aliases a guarded sub)'

echo "== must BLOCK (exit 2) — 2.0.3 self-red-team (adversarial panel) =="
check 2 '(git push)'                            'subshell glued to git (no space)'
check 2 '(git reset --hard)'                    'subshell reset --hard'
check 2 'true && (git clean -fd)'               'subshell after && '
check 2 'diff <(git push) /dev/null'            'process substitution <(git push)'
check 2 'git reset --har HEAD'                  'abbrev --har == --hard'
check 2 'git reset --ha HEAD'                   'abbrev --ha == --hard'
check 2 'git clean --for'                       'abbrev --for == --force (clean)'
check 2 'git clean --forc -d'                   'abbrev --forc == --force (clean)'
check 2 'git checkout --for main'               'abbrev --for == --force (checkout)'
check 2 'git branch --dele --forc feature'      'abbrev --dele --forc == delete+force'
check 2 'git checkout -fq main'                 'bundled checkout force -fq'
check 2 'git checkout -fb created'              'bundled checkout force -fb'
check 2 'git restore -SW file.txt'              'bundled restore -SW (staged+worktree)'
check 2 'git restore -WS file.txt'              'bundled restore -WS (worktree+staged)'
check 2 'git switch -f main'                    'switch -f discards changes'
check 2 'git switch --discard-changes main'     'switch --discard-changes'
check 2 'git checkout -- :!keep.txt'            'exclude pathspec :! (whole-tree-minus-one)'
check 2 'git -c ALIAS.p=push p'                 'case-variant config section ALIAS.'
check 2 'git -c Alias.p=push p'                 'case-variant config section Alias.'
check 2 "git -c 'alias.p=-p push' p"            'alias value with leading global flag -p'
check 2 "git -c 'alias.x=!git push;' x"         'bang alias with glued semicolon'

echo "== must BLOCK (exit 2) — 2.0.3-r4 (Codex round-3 exact-head) =="
# inline alias VALUE combined with CALL-SITE args (value alone is not dangerous)
check 2 'git -c alias.n=reset n --hard'         'inline alias reset + call-site --hard'
check 2 'git -c alias.n=clean n -fd'            'inline alias clean + call-site -fd'
check 2 'git -c alias.n=branch n -D feature'    'inline alias branch + call-site -D'
# official config-injection surfaces resolved against leading env assignments
check 2 'P=push git --config-env=alias.p=P p origin main'                       '--config-env alias from env var'
check 2 'GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push git p origin main' 'GIT_CONFIG_* env alias injection'
# forced branch (re)creation discards the ref tip
check 2 'git checkout -B main origin/main'      'checkout -B force branch reset'
check 2 'git switch -C main origin/main'        'switch -C force branch reset'
# static bash grammar the shell would actually run git through
check 2 "\$'git' push"                          "ANSI-C quoted git word \$'git'"
check 2 "git \$'push'"                          "ANSI-C quoted subcommand \$'push'"
check 2 'echo ok |& git push'                   '|& pipe-both separator then push'
check 2 '>/tmp/x git push'                       'leading redirection then push'
check 2 '! git push'                             'leading ! negation then push'
check 2 '{ git push; }'                          'brace group then push'
check 2 'if true; then git push; fi'             'if/then/fi with push in body'
# wrapper grammars that DO execute the following git word
check 2 'command -p git push'                    'command -p (default PATH) runs git'
check 2 'nice -n 5 git push'                      'nice -n <value> then push'
check 2 'env --unset FOO git push'               'env --unset <var> then push'
check 2 'exec -a gitname git push'               'exec -a <name> then push'

echo "== must BLOCK (exit 2) — 2.0.3-r5 (Codex round-4 exact-head) =="
# F2: exclude-only pathspecs address the WHOLE tree ("everything EXCEPT x")
check 2 "git restore ':(exclude)does-not-exist'"    'restore exclude-only pathspec (whole tree)'
check 2 "git checkout ':(exclude)does-not-exist'"   'checkout exclude-only pathspec (whole tree)'
check 2 "git checkout ':(top,exclude)README.md'"    'checkout :(top,exclude) magic pathspec'
# F3: leading execution grammar the shell strips before running git
check 2 '2>&1 git push'                             'fd-dup 2>&1 then push'
check 2 '1>&2 git push'                             'fd-dup 1>&2 then push'
check 2 '>&2 git push'                              'bare fd-dup >&2 then push'
check 2 'VAR+=x git push'                           'append-assignment prefix then push'
check 2 'A[0]=x git push'                           'array-assignment prefix then push'
check 2 '<<< x git push'                            'herestring then push'
check 2 '>|/tmp/x git push'                         'noclobber-override redirection then push'
# F4: env split-string hides a complete git command line in ONE shell word
check 2 "env -S 'git push origin main'"             'env -S split-string push'
check 2 "env --split-string='git push origin main'" 'env --split-string= push'
check 2 "env -S'git push origin main'"              'env -S glued split-string push'
check 2 "env -vS'git push origin main'"             'env bundled -vS split-string push'
check 2 "env -u X -S 'git push'"                    'env -u then -S split-string push'
# F5: nested alias chains resolved recursively (bounded, cycle-safe)
check 2 "git -c alias.n='-c alias.p=push p' n"      'nested alias chain n -> p -> push (invoked)'
check 2 "git -c alias.n='-c alias.p=push p' status" 'nested alias chain defined via -c'
check 2 "git config alias.n '-c alias.p=push p'"    'persistent nested alias chain'
check 2 "git -c alias.a='-c alias.b=reset b' a --hard" 'nested alias + call-site --hard'
# F6: forced branch ref updates move/clobber refs destructively
check 2 'git branch -f topic HEAD~1'                'branch -f force ref move'
check 2 'git branch --force topic HEAD~1'           'branch --force ref move'
check 2 'git branch -M old new'                     'branch -M force rename (clobbers target)'
check 2 'git branch -C old new'                     'branch -C force copy (clobbers target)'
check 2 'git branch --move --force a b'             'branch --move --force'
check 2 'git branch --copy --force a b'             'branch --copy --force'

echo "== must ALLOW (exit 0) — 2.0.3-r5 safe forms (no over-block) =="
# F9: command -pv/-pV only PRINT a path (query), never execute
check 0 'command -pv git push'                      'command -pv is a query (prints a path)'
check 0 'command -pV git push'                      'command -pV is a query'
check 0 'git branch -m old new'                     'branch -m safe rename (fails on clobber)'
check 0 'git branch -c old new'                     'branch -c safe copy (fails on clobber)'
check 0 "git -c alias.n='-c alias.p=status p' n"    'nested alias to a SAFE subcommand'
check 0 'git -c alias.self=self self'               'alias cycle: git refuses it, nothing runs'
check 0 'git branch -u origin/x topic'              'branch -u upstream (not a force)'
check 0 'git branch --merged main'                  'branch --merged (read-only listing)'

echo "== must BLOCK (exit 2) — 2.0.3-r6 (Codex round-5 exact-head) =="
# G1: fd-prefixed noclobber-override clobber redirection still runs git (fd prefix must not orphan)
check 2 '2>|/dev/null git push'                     'fd2 clobber-override redirect then push'
check 2 '1>|/dev/null git push'                     'fd1 clobber-override redirect then push'
check 2 '9>|/dev/null git push'                     'fd9 clobber-override redirect then push'
check 2 '2>| /dev/null git push'                    'fd clobber-override with spaced target'
check 2 '0>|/dev/null git reset --hard'             'fd0 clobber-override then reset --hard'
# G2: GIT_CONFIG_PARAMETERS is git'"'"'s own -c env encoding; real git resolves the alias into push
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\" git p"       'GIT_CONFIG_PARAMETERS split key=value alias'
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.p=push'\" git p"         'GIT_CONFIG_PARAMETERS single-token alias'
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.a'='status' 'alias.p'='push'\" git p" 'GIT_CONFIG_PARAMETERS multiple entries'
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.n'='reset --hard'\" git n" 'GIT_CONFIG_PARAMETERS alias to reset --hard'
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.x=!git push'\" git x"    'GIT_CONFIG_PARAMETERS bang-alias to push'

echo "== must ALLOW (exit 0) — 2.0.3-r6 safe forms (no over-block) =="
# G3: a `config` token in ordinary argv (after --) is NOT an alias definition
check 0 'git status -- config alias.p push'         'config as status pathspec, not an alias def'
check 0 'git diff -- config alias.p push'           'config as diff pathspec, not an alias def'
check 0 'git log -- config alias.p push'            'config as log pathspec, not an alias def'
check 0 'git add -- config alias.p push'            'config as add pathspec, not an alias def'
check 0 'git log config alias.p push'               'config as a plain log argument'
check 0 'git show config alias.p push'              'config as a plain show argument'
# GIT_CONFIG_PARAMETERS benign entries must not over-block
check 0 "GIT_CONFIG_PARAMETERS=\"'user.name'='x'\" git status"   'GIT_CONFIG_PARAMETERS non-alias entry'
check 0 "GIT_CONFIG_PARAMETERS=\"'alias.st'='status'\" git st"   'GIT_CONFIG_PARAMETERS alias to safe status'
check 0 "GIT_CONFIG_PARAMETERS=\"'alias.p'\" git p"              'GIT_CONFIG_PARAMETERS boolean alias (no value)'
check 0 'echo 2 >|/tmp/x'                           'a spaced digit before >| is an arg, no git'
# G3 control: a REAL config alias definition still blocks
check 2 'git config alias.p push'                   'real config alias.p=push still blocked'
check 2 'git config --global alias.co checkout'     'real config --global alias.co still blocked'

echo "== must ALLOW (exit 0) — 2.0.3-r4 safe forms (no over-block) =="
check 0 'command -v git push'                    'command -v git only prints a path'
check 0 'git checkout -bfeature'                 'checkout -b<name> attached (create branch)'
check 0 'git switch -cfeature'                   'switch -c<name> attached (create branch)'
check 0 'git restore -sfeature README.md'        'restore -s<source> attached (single file)'
check 0 'git clean -efoo'                         'clean -e<pattern> attached (exclude)'
check 0 "git checkout ':(literal)README.md'"     'magic pathspec single file :(literal)'
check 0 "git checkout ':(top)README.md'"         'magic pathspec single file :(top)path'
check 0 "git checkout ':/README.md'"             'root-relative single file :/path'
check 0 'git status # docs; git push origin main' 'push is shell-comment text, not a command'

echo "== must ALLOW (exit 0) — read-only / dry-run / non-dangerous =="
check 0 'echo git push'                                          'unquoted git as echo argument'
check 0 'grep -r git push'                                       'unquoted git as grep argument'
check 0 'git add -A && echo done, now run git push'             'safe add + echo mentioning push'
check 0 "git config alias.unstage 'reset HEAD'"                 'soft reset HEAD alias is safe'
check 0 'git switch main'                                        'plain branch switch'
check 0 'git config alias.st status'           'safe alias definition (status)'
check 0 'git config alias.lg "log --oneline"'  'safe alias definition (log)'

echo "== must ALLOW (exit 0) — false-positive regressions (quoted text must not trip) =="
check 0 'git commit -m "run git config alias.p push someday"'  'commit message mentions the command'
check 0 'git commit -m "document alias.branch behavior"'       'commit message mentions alias.branch'
check 0 'echo "alias.push=push in docs"'                       'echo of alias text (non-git)'
check 0 'git commit -m "fix: checkout . regression"'           'commit message mentions checkout .'
check 0 'echo config alias.p push'                             'non-git echo of config alias (not a git invocation)'
check 0 'python -c alias.p=push'                               'python -c is not a git -c (scoped to git word)'
check 0 'git config alias.sb show-branch'                      'safe alias to show-branch (no substring false-match)'
check 0 'git status'                           'status'
check 0 'git -C /repo status'                  '-C then status'
check 0 'git log --oneline -5'                 'log'
check 0 'git diff HEAD'                        'diff'
check 0 'git fetch --all'                      'fetch'
check 0 'git clean -fdn'                       'clean dry-run (-fdn)'
check 0 'git reset --soft HEAD~1'             'reset --soft'
check 0 'git branch -d merged'                'branch -d (safe delete)'
check 0 'git --no-pager log'                   '--no-pager log'
check 0 'ls -la'                               'non-git command'

echo "== must BLOCK/ALLOW — 2.0.3-r7 inherited Git runtime-config environment =="
# These values are inherited by the hook process, not visible in the payload command. Real Git
# expands both aliases; the guard must therefore close the same call path before authorizing it.
check_inherited 2 'git p' 'inherited GIT_CONFIG_PARAMETERS alias -> push' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 2 'git p' 'inherited GIT_CONFIG_COUNT alias -> push' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=push'
check_inherited 2 'git x' 'inherited bang alias -> nested git push' \
  "GIT_CONFIG_PARAMETERS='alias.x=!git push'"
check_inherited 2 'git n' 'inherited nested alias chain -> push' \
  "GIT_CONFIG_PARAMETERS='alias.n=-c alias.p=push p'"
check_inherited 2 'git n --hard' 'inherited PARAMETERS reset + call-site --hard' \
  "GIT_CONFIG_PARAMETERS='alias.n'='reset'"
check_inherited 2 'git x' 'inherited COUNT bang alias -> push' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.x' 'GIT_CONFIG_VALUE_0=!git push'
check_inherited 2 'git n --hard' 'inherited COUNT reset + call-site --hard' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.n' 'GIT_CONFIG_VALUE_0=reset'
check_inherited 2 'git p' 'inherited alias name is case-folded' \
  "GIT_CONFIG_PARAMETERS='alias.P'='push'"
check_inherited 2 'git --config-env=alias.p=P p' 'inherited config-env source is resolved' \
  'P=push'
check_inherited 2 'git p' 'last duplicate PARAMETERS value dangerous' \
  "GIT_CONFIG_PARAMETERS='alias.p'='status' 'alias.p'='push'"
# Multiple sources, Git's precedence (COUNT first, PARAMETERS after it), and a command-visible
# assignment overriding the inherited variable are each isolated. Safe overrides stay usable.
check_inherited 2 'git p' 'inherited PARAMETERS wins collision over COUNT' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'" \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=status'
check_inherited 0 "GIT_CONFIG_PARAMETERS=\"'alias.p'='status'\" git p" \
  'command assignment overrides inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 0 'GIT_CONFIG_COUNT=0 git status' \
  'command count zero disables inherited COUNT entries' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=push'
check_inherited 0 'env -u GIT_CONFIG_PARAMETERS git status' \
  'env -u removes inherited PARAMETERS before git' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
# Benign and non-alias runtime config stays open. Malformed/missing families block explicitly as an
# unclassifiable injection surface; they must never throw into the wrapper's documented fail-open.
check_inherited 0 'git st' 'inherited safe alias -> status' \
  "GIT_CONFIG_PARAMETERS='alias.st'='status'"
check_inherited 0 'git status' 'inherited non-alias config' \
  "GIT_CONFIG_PARAMETERS='user.name'='x'"
check_inherited 2 'git p' 'malformed inherited PARAMETERS blocks explicitly' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push"
check_inherited 2 'git p' 'missing COUNT value blocks explicitly' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.p'
check_inherited 2 'git status' 'invalid unquoted PARAMETERS entry blocks explicitly' \
  'GIT_CONFIG_PARAMETERS=alias.p=push'
# At the explicit resource ceiling a valid safe family is parsed; above it blocks as evasion.
check_inherited_count_bound 0 256 'COUNT at resource ceiling with safe entries'
check_inherited_count_bound 2 257 'COUNT above resource ceiling blocks as evasion'
check_inherited_parameters_bound 0 256 'PARAMETERS at resource ceiling with safe entries'
check_inherited_parameters_bound 2 257 'PARAMETERS above resource ceiling blocks as evasion'
long_cfg="$(printf '%*s' 65537 '' | tr ' ' x)"
check_inherited 2 'git status' 'oversized PARAMETERS raw blocks as evasion' \
  "GIT_CONFIG_PARAMETERS=$long_cfg"
check_inherited 2 'git status' 'oversized COUNT value blocks as evasion' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=user.name' "GIT_CONFIG_VALUE_0=$long_cfg"
check_inherited 2 'git a' 'alias nesting beyond resolver cap blocks as evasion' \
  "GIT_CONFIG_PARAMETERS='alias.a'='b' 'alias.b'='c' 'alias.c'='d' 'alias.d'='e' 'alias.e'='f' 'alias.f'='g' 'alias.g'='h' 'alias.h'='i' 'alias.i'='j' 'alias.j'='status'"

echo "== must ALLOW — 2.0.3-r7 precedence, scope, and single-file controls =="
check_inherited 0 'git status' 'stray indexed vars without COUNT are inert' \
  'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=push'
check_inherited 0 'git status' 'indexed vars above COUNT are inert' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=user.name' 'GIT_CONFIG_VALUE_0=safe' \
  'GIT_CONFIG_KEY_1=alias.p' 'GIT_CONFIG_VALUE_1=push'
check_inherited 0 'git status' 'COUNT zero ignores stray pairs' \
  'GIT_CONFIG_COUNT=0' 'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=push'
check_inherited 0 'git p' 'last duplicate PARAMETERS value safe' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push' 'alias.p'='status'"
check_inherited 0 'git p' 'PARAMETERS safe overrides dangerous COUNT' \
  "GIT_CONFIG_PARAMETERS='alias.p'='status'" \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=alias.p' 'GIT_CONFIG_VALUE_0=push'
check_inherited 0 'git -c alias.p=status p' 'inline safe overrides inherited PARAMETERS danger' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 0 'P=status git -c alias.p=push --config-env=alias.p=P p' \
  'later config-env safe wins within argv layer'
check_inherited 2 'P=push git -c alias.p=status --config-env=alias.p=P p' \
  'later config-env dangerous wins within argv layer'
check_inherited 0 'env -i git status' 'env -i clears inherited runtime config' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check 0 'git status -- -c alias.p=push' 'post-subcommand -c text is ordinary argv'
check 0 'git status -- --config-env=alias.p=P' 'post-subcommand config-env text is ordinary argv'
check 0 'git restore README.md' 'single-file restore intentionally allowed'
check 0 'git restore --worktree README.md' 'single-file worktree restore intentionally allowed'
check 0 'git checkout HEAD -- README.md' 'single-file checkout-from-HEAD intentionally allowed'

echo "== must BLOCK/ALLOW — 2.0.3-r8 exact-head red-team regressions =="
# Shell append assignments are real environment prefixes in Bash 3.2. The environment utility is
# different: after `env`, NAME+=value names NAME+ and must not be mistaken for a shell append.
check 2 "GIT_CONFIG_PARAMETERS+=\"'alias.p'='push'\" git p" \
  'shell += assignment injects PARAMETERS alias -> push'
check 2 'GIT_CONFIG_COUNT+=1 GIT_CONFIG_KEY_0+=alias.p GIT_CONFIG_VALUE_0+=push git p' \
  'shell += assignments inject COUNT alias -> push'
check_inherited 2 "GIT_CONFIG_PARAMETERS+=\"'alias.p'='push'\" git p" \
  'shell += appends a dangerous entry to inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='user.name'='safe' "
check 0 "env GIT_CONFIG_PARAMETERS+=\"'alias.p'='push'\" git status" \
  'env NAME+=value sets NAME+, not GIT_CONFIG_PARAMETERS'

# The obsolete-but-live macOS/BSD `env -` spelling is equivalent to `env -i` and still executes the
# following command. Nested wrapper forms must reach the same classifier.
check 2 'env - git push' 'env dash executes git push'
check 2 '/usr/bin/env - git reset --hard' 'full-path env dash executes reset --hard'
check 2 'command env - git clean -fd' 'nested command+env dash executes clean -fd'
check 2 "env -S 'env - git push'" 'split-string nested env dash executes push'

# Static exported shell state persists across separators. Assignment-only state is exported only when
# it was inherited-exported or an explicit export marks it; an unexported assignment remains inert.
check 2 "export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'exported PARAMETERS persists across shell segment'
check 2 'export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=alias.p GIT_CONFIG_VALUE_0=push; git p' \
  'exported COUNT family persists across shell segment'
check 2 "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; export GIT_CONFIG_PARAMETERS; git p" \
  'assignment then bare export persists PARAMETERS'
check 2 'P=push; export P; git --config-env=alias.p=P p' \
  'exported config-env source persists across shell segments'
check_inherited 2 "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'assignment updates an inherited-exported PARAMETERS variable' \
  "GIT_CONFIG_PARAMETERS='alias.p'='status'"
check 0 "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'unexported assignment-only PARAMETERS stays out of child git'
check 0 "export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; unset GIT_CONFIG_PARAMETERS; git status" \
  'unset removes prior exported PARAMETERS state'
check 0 "export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; export GIT_CONFIG_PARAMETERS=\"'alias.p'='status'\"; git p" \
  'later exported safe PARAMETERS value wins'
check 0 'P=status; export P; git --config-env=alias.p=P p' \
  'exported safe config-env source remains usable'
check 2 "declare -x GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'declare -x exports PARAMETERS across segments'
check 2 "typeset -x GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'typeset -x exports PARAMETERS across segments'
check 2 "set -a; GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'set -a exports later assignment-only PARAMETERS'
check_inherited 2 "GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\" :; git p" \
  'assignment to special builtin updates inherited-exported PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='status'"
check 0 "export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; export -n GIT_CONFIG_PARAMETERS; git status" \
  'export -n removes PARAMETERS from the child environment'

# Conditional/pipeline/subshell state is not a single linear environment. Preserve every feasible
# static variant so a skipped or subshell-only safe mutation cannot erase inherited danger, and a
# conditionally introduced dangerous alias cannot disappear from the model. Linear `;` overrides
# above remain exact; ambiguous control flow deliberately over-blocks in the safe direction.
check_inherited 2 "false && unset GIT_CONFIG_PARAMETERS; git p" \
  'skipped conditional unset cannot erase inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 2 "true || unset GIT_CONFIG_PARAMETERS; git p" \
  'skipped OR unset cannot erase inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 2 "unset GIT_CONFIG_PARAMETERS | true; git p" \
  'pipeline-subshell unset cannot erase inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check 2 "true && export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'conditionally introduced dangerous PARAMETERS remains visible'
check 2 "false || export GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\"; git p" \
  'OR-introduced dangerous PARAMETERS remains visible'
check_inherited 2 "true && export GIT_CONFIG_PARAMETERS=\"'alias.p'='status'\"; git p" \
  'ambiguous safe override is conservatively blocked' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check 2 'true && export A=1; true && export B=1; true && export C=1; true && export D=1; true && export E=1; true && export F=1; git status' \
  'ambiguous shell-state lattice blocks at its hard variant cap'

# Git pathspec wildcards can address every tracked path without spelling `*` exactly. Conservatively
# block wildcard restore/checkout; `:(literal)` remains the explicit single-file escape hatch.
check 2 "git restore '?*'" 'wildcard ?* restores the whole tree'
check 2 "git checkout HEAD -- '?*'" 'checkout wildcard ?* restores the whole tree'
check 2 "git restore ':/?*'" 'root-relative wildcard restores the whole tree'
check 2 "git restore ':(glob)**/*'" 'glob-magic recursive wildcard restores the tree'
check 2 "git checkout ':(top,glob)[a-z]*'" 'glob character class is broad checkout pathspec'
check 2 "git restore '[!.]*'" 'raw character class is broad restore pathspec'
check 2 "git restore ':(icase,glob)?*'" 'mixed magic wildcard is broad restore pathspec'
check 2 "git checkout HEAD -- ':/[a-z]*'" 'root-relative character class is broad checkout pathspec'
check 2 "git restore 'sub/**'" 'recursive subtree wildcard is conservatively blocked'
check 0 "git restore ':(literal)?*'" 'literal magic preserves a concrete wildcard-named file'
check 0 "git checkout HEAD -- ':(top,literal)[a-z]*'" \
  'top+literal magic preserves a concrete bracket-named file'
check 2 'git restore --pathspec-from-file=/tmp/paths' \
  'restore attached opaque pathspec file cannot hide whole-tree selection'
check 2 'git restore --pathspec-from-file /tmp/paths' \
  'restore separate opaque pathspec file cannot hide whole-tree selection'
check 2 'git checkout HEAD --pathspec-from-file=-' \
  'checkout stdin pathspec cannot hide whole-tree selection'
check 2 'git restore --pathspec-from-f=/tmp/paths' \
  'restore unambiguous long-option abbreviation remains blocked'

# Git's `--` ends option parsing. Option-looking names after it are concrete pathspecs and must stay
# usable, while the real pre-boundary options remain blocked. Keep these isolated so a future option
# scan cannot silently regress the single-file recovery contract.
check 0 "git restore -- '-f'" \
  'post-boundary -f is a concrete restore filename'
check 0 "git checkout HEAD -- '--pathspec-from-file'" \
  'post-boundary --pathspec-from-file is a concrete checkout filename'
check 0 "git restore -- '--force'" \
  'post-boundary --force is a concrete restore filename'
check 2 'git restore -f README.md' \
  'pre-boundary -f remains a restore force option'
check 2 'git restore --force README.md' \
  'pre-boundary --force remains a restore force option'
check 2 'git checkout HEAD --pathspec-from-file=/tmp/paths' \
  'pre-boundary --pathspec-from-file remains opaque'

# A literal `--` can itself be the required value of an option. Only the next unconsumed `--` is a
# pathspec separator; force options after a consumed value remain live and destructive. Conversely,
# an option-looking consumed value is data and must not create a false block.
check 2 'git clean -e -- --force victim' \
  'clean exclude consumes first double dash; later --force remains live'
check 2 'git clean -e -- -f victim' \
  'clean exclude consumes first double dash; later -f remains live'
check 2 'git clean -e -- --for victim' \
  'clean exclude consumes first double dash; later abbreviated force remains live'
check 2 'git clean --exclude -- --force victim' \
  'long exclude consumes first double dash; later force remains live'
check 0 'git clean -e -f victim' \
  'option-looking -f is the exclude value, not a force option'
check 0 'git clean --exclude=-- -- --force' \
  'attached exclude value leaves a real separator and concrete --force filename'
check 2 'git clean --ex -- --for victim' \
  'abbreviated exclude consumes its value; later abbreviated force stays live'
check 2 'git restore -s -- --force README.md' \
  'restore source consumes first double dash; later force stays live'
check 0 'git restore -s --force README.md' \
  'option-looking --force is a consumed restore source value'
check 2 'git switch -c -- --discard-changes main' \
  'switch create consumes first double dash; later discard stays live'
check 0 'git switch -c -f main' \
  'option-looking -f is a consumed branch-name value'
check 2 'git branch -u -- --force topic' \
  'branch upstream consumes first double dash; later force stays live'
check 0 'git branch -u -f topic' \
  'option-looking -f is a consumed upstream value'
check 2 'git reset --pathspec-from-file -- --hard' \
  'reset pathspec source consumes first double dash; later hard stays live'
check 0 "git restore -s '*' README.md" \
  'wildcard-shaped source value is not a whole-tree pathspec'

# `:(literal)` is the explicit contract escape for a tracked filename containing wildcard bytes.
# Test the exact wildcard spellings that the broad pathspec policy otherwise blocks.
check 0 "git restore -- ':(literal)*'" \
  'literal magic preserves a concrete star-named file'
check 0 "git checkout HEAD -- ':(top,literal)**'" \
  'top+literal magic preserves a concrete double-star-named file'
check 0 "git restore -- ':(literal)[!.]*'" \
  'literal magic preserves a concrete bracket-and-star filename'

# Git's own sq_quote_buf encoding emits escaped `!` outside adjacent single-quoted chunks. Accept that
# official form as data, while still resolving an encoded bang alias and never evaluating bytes.
check_inherited 0 'git status' 'Git-generated escaped-bang non-alias config is benign' \
  "GIT_CONFIG_PARAMETERS='user.name'=''\\!'safe'"
check_inherited 0 'git x' 'Git-generated escaped-bang alias to status is safe' \
  "GIT_CONFIG_PARAMETERS='alias.x'=''\\!'git status'"
check_inherited 2 'git x' 'Git-generated escaped-bang alias to push blocks' \
  "GIT_CONFIG_PARAMETERS='alias.x'=''\\!'git push'"
check_inherited 2 "git config alias.x '!git n --hard'" \
  'persistent bang alias composes with inherited reset alias' \
  "GIT_CONFIG_PARAMETERS='alias.n'='reset'"
check_inherited 0 "git config alias.x '!git n'" \
  'persistent bang alias composes safely with inherited status alias' \
  "GIT_CONFIG_PARAMETERS='alias.n'='status'"
check_inherited 0 'git status' 'Git-generated embedded quote remains parseable' \
  "GIT_CONFIG_PARAMETERS='user.name'='a'\\''b'"

# Bundled `env -iS` preserves both operations: clear inherited state, then split/execute the string.
check_inherited 0 "env -iS 'git status'" 'bundled env -iS clears inherited PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 0 "env -ivS 'git status'" 'bundled env -ivS retains ignore-environment semantics' \
  "GIT_CONFIG_PARAMETERS='alias.p'='push'"
check_inherited 2 "env -iS 'GIT_CONFIG_PARAMETERS=\"'alias.p'='push'\" git p'" \
  'bundled env -iS clears then installs visible dangerous PARAMETERS' \
  "GIT_CONFIG_PARAMETERS='alias.p'='status'"

echo "== must BLOCK (exit 2) — 2.0.4 G2 red-team grammar regressions =="
# K3-203-002: redirections are valid throughout a simple command, including when glued to the
# decisive subcommand/option/pathspec. Every equivalent destructive form must classify alike.
check 2 'git push>/dev/null'                         'attached output redirect after push'
check 2 'git push</dev/null origin main'             'attached input redirect after push'
check 2 'git</dev/null push origin main'             'attached redirect after git word'
check 2 'git reset --hard>/dev/null'                  'attached redirect after reset option'
check 2 'git restore .>/dev/null'                     'attached redirect after whole-tree pathspec'
check 2 'git checkout .>discard.log'                  'attached redirect after checkout pathspec'
check 2 'git clean --force>/dev/null -d'              'attached redirect after clean force option'
check 2 'git switch --discard-changes>/dev/null main' 'attached redirect after switch option'
check 2 'git branch --force>/dev/null topic'          'attached redirect after branch option'
check 2 'git push>>/dev/null'                         'attached append redirect after push'

# K3-203-003: Git appends call-site arguments to a bang-alias shell body. Classify the body and
# those arguments together instead of blessing the body in isolation.
check 2 "git -c alias.p='!git' p push"               'bang alias bare git plus push argument'
check 2 "git -c alias.p='!git' p reset --hard"       'bang alias bare git plus reset arguments'
check 2 "git -c alias.p='!git' p clean -fd"          'bang alias bare git plus clean arguments'
check 0 "git -c alias.p='!git' p status"             'bang alias bare git plus safe status argument'

# K3-203-015/016/017: non-alias config can remove clean's force floor; plumbing can rewrite refs;
# static Bash brace expansion is outside the declared POSIX grammar and therefore blocks.
check 2 'git -c clean.requireForce=false clean -d'    'clean requireForce=false deletes untracked files'
check 2 'git update-ref refs/heads/topic HEAD~1'       'update-ref force moves a branch ref'
check 2 'git update-ref -d refs/heads/topic'           'update-ref deletes a branch ref'
check 2 'git tag -f release HEAD~1'                    'tag -f clobbers a tag ref'
check 2 'git {push,}'                                  'Bash brace expansion is fail-closed'

# Strict release mode turns every explicitly unsupported dynamic grammar into a block while the
# ordinary advisory mode retains its documented compatibility behavior.
# shellcheck disable=SC2016 # literal attack strings; the test must not execute them
check_strict 2 'C=git; $C push'                        'strict mode blocks variable dispatch'
# shellcheck disable=SC2016 # literal attack strings; the test must not execute them
check_strict 2 'git $(printf pu)sh'                    'strict mode blocks command assembly'
check_strict 2 'eval "git push"'                      'strict mode blocks eval'
check_strict 2 'sh -c "git push"'                     'strict mode blocks nested shell command'
check_strict 2 'f(){ git push; }; f'                   'strict mode blocks function definitions'
check_strict 0 'git status'                            'strict mode retains proved safe Git command'

echo "== must BLOCK/ALLOW — 2.0.4 K3-204 guard regressions =="
# GUARD-C1: Git executes several runtime config values as commands. Exercise every config transport
# the classifier claims to model, plus Git's direct editor environment, without treating unrelated
# config or an inherited editor on a non-editor command as dangerous.
check 2 "git -c core.editor='git push origin main #' commit --allow-empty" \
  'inline exec-valued core.editor config blocks'
check 2 "git -ccore.editor='git push origin main #' commit --allow-empty" \
  'glued inline exec-valued config blocks'
check 2 "ED='git push origin main #' git --config-env=sequence.editor=ED rebase -i HEAD~1" \
  'config-env exec-valued sequence.editor blocks'
check 2 "GIT_CONFIG_PARAMETERS=\"'core.editor'='git push origin main #'\" git commit --allow-empty" \
  'command PARAMETERS exec-valued config blocks'
check 2 "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.editor GIT_CONFIG_VALUE_0='git push origin main #' git commit --allow-empty" \
  'command COUNT exec-valued config blocks'
check_inherited 2 'git commit --allow-empty' \
  'inherited PARAMETERS exec-valued config blocks' \
  "GIT_CONFIG_PARAMETERS='core.editor'='git push origin main #'"
check_inherited 2 'git commit --allow-empty' \
  'inherited COUNT exec-valued config blocks' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=core.editor' \
  'GIT_CONFIG_VALUE_0=git push origin main #'
check 2 "export GIT_CONFIG_PARAMETERS=\"'core.editor'='git push origin main #'\"; git commit --allow-empty" \
  'exported exec-valued config persists across segments'
check 2 "GIT_EDITOR='git push origin main #' git commit --allow-empty" \
  'visible GIT_EDITOR command injection blocks'
check_inherited 2 'git commit --allow-empty' \
  'inherited GIT_EDITOR command injection blocks' \
  'GIT_EDITOR=git push origin main #'
check 2 "git config core.editor 'git push origin main #'" \
  'persistent exec-valued config mutation blocks'
check 2 "git config --global diff.external 'git push origin main #'" \
  'persistent patterned exec-valued config mutation blocks'
check 2 "git -c credential.helper='!git push' fetch" \
  'credential helper runtime command blocks'
check 2 "git -c filter.attack.process='git push' status" \
  'filter process runtime command blocks'
check 2 "git -c submodule.x.update='!git push' submodule update" \
  'custom submodule update command blocks'
check 2 "git -c core.alternateRefsCommand='git push' rev-list --alternate-refs" \
  'alternate refs shell command blocks'
check 2 "git -c diff.attack.textconv='git push' diff" \
  'textconv runtime command blocks'
check 2 "git -c gc.recentObjectsHook='git push' gc" \
  'recent-objects shell hook blocks'
check 2 "git -c gpg.ssh.defaultKeyCommand='git push' commit -S -m msg" \
  'SSH signing key command blocks'
check 2 "git -c difftool.attack.path='/tmp/attack' difftool" \
  'difftool executable path blocks'
check 2 "git -c mergetool.attack.path='/tmp/attack' mergetool" \
  'mergetool executable path blocks'
check 2 "git -c remote.origin.uploadpack='git push' fetch origin" \
  'remote upload-pack command blocks'
check 2 "git -c uploadpack.packObjectsHook='git push' upload-pack ." \
  'upload-pack shell hook blocks'
check 2 "git -c sendemail.ccCmd='git push' send-email patch" \
  'base send-email recipient command blocks'
check 2 "git -c sendemail.work.sendmailCmd='git push' send-email patch" \
  'identity sendmail command blocks'
check 2 "git -c sendemail.smtpServer='/tmp/attack' send-email patch" \
  'send-email executable SMTP-server path blocks'
check 2 "GIT_SSH_COMMAND='git push' git fetch" \
  'visible Git SSH command blocks on a network operation'
check 2 "GIT_EXTERNAL_DIFF='git push' git diff" \
  'visible external diff command blocks on diff'
check 2 "GIT_PAGER='git push' git -p log" \
  'visible pager command blocks under explicit pagination'
check 2 "EDITOR='git push origin main #' git commit --allow-empty" \
  'fallback EDITOR command injection blocks'
check 2 "PAGER='git push' git -p log" \
  'fallback pager command blocks under explicit pagination'
check 0 'git -c user.name=alice status' \
  'ordinary runtime config remains usable'
check 0 'git -c submodule.x.update=checkout status' \
  'built-in submodule update strategy remains usable'
check 0 'git -c core.pager= status' \
  'empty executable config value remains usable'
check 0 'git -c pager.status=false status' \
  'boolean per-command pager setting remains usable'
check 0 'git -c sendemail.smtpServer=smtp.example.com send-email patch' \
  'ordinary SMTP host remains usable'
check 0 'git config --get core.editor' \
  'reading an executable config key remains usable'
check 0 'git config --unset core.editor' \
  'removing an executable config key remains usable'
check_inherited 0 'git status' \
  'inherited editor is inert for a non-editor command' \
  'GIT_EDITOR=vim'
check_inherited 0 'git commit -m msg --allow-empty' \
  'explicit commit message does not invoke inherited editor' \
  'GIT_EDITOR=vim'

# GUARD-C2/C3/C4: cover plumbing equivalents of the existing hard-reset/whole-tree/ref rules while
# keeping concrete single-file checkout-index recovery and non-forced checkout-index use available.
check 2 'git read-tree --reset -u HEAD'                'read-tree reset plus update discards worktree'
check 2 'git read-tree -mu HEAD'                       'read-tree merged update discards worktree'
check 2 'git read-tree --merge --update HEAD'          'read-tree long merge plus update blocks'
check 2 'git checkout-index -f -a'                     'checkout-index force plus all overwrites tree'
check 2 'git checkout-index -fa'                       'checkout-index bundled force plus all blocks'
check 2 'git checkout-index --force --all'             'checkout-index long force plus all blocks'
check 2 'git checkout-index -f -a --prefix=./'         'checkout-index prefixed whole-tree overwrite blocks'
check 0 'git checkout-index -f README.md'              'checkout-index forced concrete file remains usable'
check 0 'git checkout-index -a'                        'checkout-index all without overwrite force remains usable'
check 2 'git tag -d v1'                                'tag short delete removes tag ref'
check 2 'git tag --delete v1'                          'tag long delete removes tag ref'
check 2 'git tag --del v1'                             'tag abbreviated delete removes tag ref'
check 0 'git tag --list'                               'tag listing remains usable'

# GUARD-C5/C6: named descriptor redirections and both Bash coproc spellings still expose the literal
# git invocation to the classifier. These are inert strings; the fixture never executes them.
check 2 '{fd}>&1 git push origin main'                  'leading named-fd duplication before push'
check 2 '{input}</dev/null git push origin main'        'leading named-fd input before push'
check 2 '{log}>/dev/null git reset --hard'              'leading named-fd output before hard reset'
check 2 'coproc git push origin main'                   'anonymous coproc executes git push'
check 2 'coproc WORKER { git reset --hard; }'           'named coproc group executes hard reset'

# GUARD-C7/C8: strict mode rejects parameter-driven Git grammar it cannot prove. Advisory mode stays
# compatible, quoted ordinary operands remain usable, and a variable in a non-Git command is inert.
# shellcheck disable=SC2016 # literal attack strings; the test must not execute them
check_strict 2 'git re${UNSET}set --hard'               'strict blocks unquoted mid-token parameter splice'
# shellcheck disable=SC2016
check_strict 2 'git reset --hard${UNSET:-}'             'strict blocks unquoted option parameter splice'
# shellcheck disable=SC2016
check_strict 2 'X=push; git $X origin main'             'strict blocks unquoted variable subcommand dispatch'
# shellcheck disable=SC2016
check_strict 2 'X=status; git "$X"'                    'strict blocks quoted variable subcommand dispatch'
# shellcheck disable=SC2016
check_strict 2 'g${UNSET}it push origin main'           'strict blocks parameter-spliced command word'
# shellcheck disable=SC2016
check_strict 2 'X=git; "$X" push origin main'          'strict blocks quoted variable command dispatch'
# shellcheck disable=SC2016
check 0 'X=status; git $X'                              'advisory mode retains variable-dispatch compatibility'
# shellcheck disable=SC2016
check_strict 0 'git status "$PATHSPEC"'                'strict allows quoted variable in ordinary operand'
# shellcheck disable=SC2016
check_strict 0 'echo $HOME'                             'strict ignores parameter expansion outside Git'
check_strict 0 "git commit -m '\$HOME'"               'strict allows single-quoted literal dollar text'

# GUARD-C9: the hook streams command text to the classifier over a file descriptor, so a command
# above Linux MAX_ARG_STRLEN must not fail open at an environment-variable exec boundary.
oversized_git_push="git push # $(printf '%*s' 1100000 '' | tr ' ' A)"
check 2 "$oversized_git_push"                          'advisory oversized command avoids E2BIG handoff'
check_strict 2 "$oversized_git_push"                   'strict oversized dangerous command fails closed'

check_inherited 0 'git status' 'PARAMETERS parser never evaluates config bytes' \
  "GIT_CONFIG_PARAMETERS='user.name=\$(touch $CANARY_DIR/gcp-pwned)'"
if [ -e "$CANARY_DIR/gcp-pwned" ]; then
  fail=$((fail + 1)); printf '  FAIL  PARAMETERS no-eval canary created a file\n'
else
  pass=$((pass + 1)); printf '  ok    [0] PARAMETERS no-eval canary\n'
fi
check_inherited 0 'git status' 'COUNT parser never evaluates config bytes' \
  'GIT_CONFIG_COUNT=1' 'GIT_CONFIG_KEY_0=user.name' "GIT_CONFIG_VALUE_0=\$(touch $CANARY_DIR/count-pwned)"
if [ -e "$CANARY_DIR/count-pwned" ]; then
  fail=$((fail + 1)); printf '  FAIL  COUNT no-eval canary created a file\n'
else
  pass=$((pass + 1)); printf '  ok    [0] COUNT no-eval canary\n'
fi

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
