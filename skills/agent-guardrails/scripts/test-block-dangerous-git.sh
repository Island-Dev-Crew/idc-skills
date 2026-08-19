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
  printf '{"tool_input":{"command":%s}}' "$(printf '%s' "$cmd" | jq -R -s .)" | bash "$GUARD" >/dev/null 2>&1
  got=$?
  if [ "$got" = "$want" ]; then pass=$((pass+1)); printf '  ok    [%s] %s\n' "$got" "$label"
  else fail=$((fail+1)); printf '  FAIL  want=%s got=%s :: %s\n' "$want" "$got" "$label"; fi
}

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

echo
echo "RESULT pass=$pass fail=$fail"
[ "$fail" -eq 0 ]
