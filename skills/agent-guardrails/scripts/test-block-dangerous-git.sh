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
