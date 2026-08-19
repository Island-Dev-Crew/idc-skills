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
check 2 'git${IFS}push origin main'            'IFS word-split push'
check 2 'git${IFS}reset --hard'               'IFS word-split reset --hard'
check 2 'git -c alias.p=push p'                'alias injection via -c (push)'
check 2 'git -c alias.co=checkout co .'        'alias injection via -c (checkout)'
check 2 'git config alias.p push'              'persistent alias definition to push'
check 2 'git config alias.nuke "reset --hard"' 'persistent alias definition to reset --hard'

echo "== must ALLOW (exit 0) — read-only / dry-run / non-dangerous =="
check 0 'git config alias.st status'           'safe alias definition (status)'
check 0 'git config alias.lg "log --oneline"'  'safe alias definition (log)'
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
