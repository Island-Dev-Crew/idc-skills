#!/usr/bin/env bash
# Claude Code PreToolUse guard: blocks destructive git commands before they run.
# Reads hook JSON on stdin; exit 2 blocks (with a stderr message), exit 0 allows.
#
# SCOPE (honest — advisory until wired, and a speed-bump even then): a defense-in-depth
# STRING classifier, not a sandbox. The bash here only (1) extracts the command from the
# hook payload and (2) maps the classifier's verdict to an exit code. The classification
# itself is a small Python model that is easy to read and to test:
#   segment the command on REAL shell separators (; & | && || newline, and the boundaries
#   of $(...) / `...` command substitution — quote-aware, so a separator inside quotes is
#   never one), then for each segment find the git invocation (basename git / git.exe,
#   through a path or an env/`command`/`sudo` prefix) and classify ONLY that invocation's
#   own arguments. Scoping detection to the git word is what stops a commit MESSAGE, an
#   `echo`, or `python -c` that merely mentions `alias.p=push` from tripping the guard.
# It skips git's global-option grammar (-C, -c, --git-dir, --work-tree, ..., long/`=`/glued
# forms), neutralizes ${IFS}/$IFS word-split tricks, understands quote/backslash word
# concatenation (posix tokenizer), bundled short flags (`-df` == `-d -f`), whole-tree
# pathspecs (`.`, `./`, `./.`, `:/`, `*`, `**`, `:(...)` magic), and alias DEFINITIONS to a
# blocked op (`-c alias.x=push`, glued `-calias.x=push`, `config alias.x '!git push'`) —
# tested by the alias VALUE actually expanding to a guarded subcommand, so
# `alias.sb=show-branch` is NOT a false positive.
#
# It is NOT a sandbox and CANNOT be one. Documented residuals a string classifier cannot
# close (keep a real OS/repo-level control underneath — this is one layer):
#   - dynamic/indirect invocation: `C=git; $C push`, `$(printf push)`, `eval "git push"`,
#     `sh -c "git push"`, a renamed/copied git binary, base64-then-decode
#   - command substitution used to ASSEMBLE a subcommand token (`git $(echo)push` rejoins at
#     runtime), and command substitution INSIDE double quotes (`"$(git push)"`)
#   - git reached only via an UNRECOGNIZED wrapper (`xargs -I{} git push`, a shell function) or an
#     abbreviated GLOBAL value-option in separate form (`git --git-di /x push`)
#   - a persistent alias set in a PRIOR command, then invoked in a later one
#   - malformed hook payloads / missing interpreters: extraction fails or python3/jq is
#     absent -> guard OPENS (announces it, allows), by design, so a parse error cannot wedge
#     every command.
# Conservative OVER-blocks (SAFE direction — the human runs it): a heredoc BODY line that is itself a
# git command (`cat <<EOF`/`git push`/`EOF`) is blocked (segmentation can't tell heredoc data from a
# command without a full parser); `git push --dry-run` is blocked ON PURPOSE (still contacts the
# remote — an authority boundary); aliasing a discard-capable subcommand (`alias.co=checkout`) is
# blocked as the evasion pattern even though `checkout <branch>` alone is safe.
# Requires `jq` (payload) and `python3` (classifier); if either is missing the guard fails
# OPEN rather than wedging the agent — wire it only where both exist, and never as the only
# barrier.
#
# NOTE: intentionally `set -uo pipefail` WITHOUT `-e`: the classifier exits 2 to signal a
# block, and under `set -e` that non-zero would abort the wrapper before the verdict is
# mapped. The classifier is run as a STANDALONE command (not inside $(...)): a heredoc that
# contains backticks/parens inside command substitution breaks bash's parser (3.2).
set -uo pipefail

cmd="$(cat | jq -r '.tool_input.command // .toolInput.command // .command // empty' 2>/dev/null || true)"
if [ -z "${cmd:-}" ]; then
  echo "block-dangerous-git: no command found in hook payload (guard OPEN)" >&2
  exit 0
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "block-dangerous-git: python3 not found; classifier unavailable (guard OPEN)" >&2
  exit 0
fi

# The command is passed via the environment (stdin here is the heredoc program). The
# classifier prints its own two-line block message to stderr and exits 2, or exits 0 to
# allow. It self-guards EVERY internal error into a fail-OPEN (exit 0 + note), so a
# classifier bug can never wedge the agent and this wrapper only ever sees a clean 0/2.
BLOCK_DANGEROUS_GIT_CMD="$cmd" python3 - <<'PY'
import os
import re
import shlex
import sys

# git global options that CONSUME the following token as their value (separate form).
VALUE_OPTS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--super-prefix", "--exec-path", "--config-env", "--attr-source",
}
# subcommands the guard treats as an authority boundary (mutate history / working tree / remote).
# `switch` is the modern equivalent of `checkout <branch>` and can discard changes with -f/--discard-changes.
GUARDED_SUBS = {"push", "checkout", "restore", "switch", "reset", "clean", "branch"}
# subcommands that are dangerous the moment they are aliased under a new name, even with no args in
# the alias VALUE (the destructive args are supplied at call time): `alias.co=checkout` then `git co .`.
ALIAS_DANGEROUS_BARE = {"push", "checkout", "restore", "switch"}
# command wrappers that run the FOLLOWING command word (so `sudo git push` is a git invocation).
WRAPPERS = {"env", "command", "sudo", "doas", "nice", "ionice", "nohup", "setsid", "stdbuf", "time", "exec", "builtin"}
# wrapper options that consume a following value (so we don't mistake the value for the command word).
WRAPPER_VALUE_OPTS = {"-u", "--user", "-g", "--group", "-C", "-p", "--prompt", "-U", "-r", "--role", "-t", "--type", "-h", "--host"}

BACKTICK = chr(96)


def is_git_word(tok):
    # basename after a / or \ path, case-folded; a bare `git` or Windows `git.exe`.
    base = re.split(r"[\\/]", tok)[-1].lower()
    return base in ("git", "git.exe")


def whole_tree_pathspec(tok):
    # pathspecs that address the WHOLE tree / repo root (a discard of everything).
    if tok in (".", "./", "./.", ".//", "././", ":/", ":", ":/:", "*", "**"):
        return True
    if tok.startswith(":("):                # magic pathspec, e.g. :(top), :(top,glob)**
        return True
    if tok.startswith(":/"):                 # :/  or  :/path-from-root
        return True
    if tok.startswith(":!") or tok.startswith(":^"):   # exclude magic -> "everything EXCEPT" = whole-tree discard
        return True
    if re.fullmatch(r"\.(?:/\.?)+", tok):     # ./, ./., .//, ././ ...
        return True
    return False


def has_long_opt(rest, name):
    # git accepts any UNAMBIGUOUS PREFIX of a long option, so `--har`/`--ha` == `--hard`,
    # `--forc`/`--for` == `--force`. Match any non-empty prefix of `name`; over-matching a bare
    # `--f` that git would itself reject as ambiguous is a safe over-block. Strip any =value first.
    for t in rest:
        if not t.startswith("--"):
            continue
        opt = t[2:].split("=", 1)[0]
        if opt and name.startswith(opt):
            return True
    return False


def short_flags(tokens):
    # chars from single-dash bundles, so -df -> {d,f} and -d -f -> {d,f}.
    flags = set()
    for t in tokens:
        if len(t) >= 2 and t[0] == "-" and t[1] != "-":
            for ch in t[1:]:
                if ch.isalpha():
                    flags.add(ch)
    return flags


def find_subcommand(tokens):
    # tokens[0] is the git word; skip global options; return the subcommand index or None.
    i, n = 1, len(tokens)
    while i < n:
        t = tokens[i]
        if t == "--":
            i += 1
            break
        if t.startswith("--") and "=" in t:       # --opt=value (one token)
            i += 1
            continue
        if t in VALUE_OPTS:                         # -C /path, -c k=v, --git-dir <dir>
            i += 2
            continue
        if t.startswith("-") and len(t) > 1:        # -Cpath / -ck=v glued, --flag, -x bundle
            i += 1
            continue
        break
    return i if i < n else None


def argv_danger(tokens):
    # tokens[0] = git word. Return a reason string or None.
    idx = find_subcommand(tokens)
    if idx is None:
        return None
    sub = tokens[idx]
    rest = tokens[idx + 1:]
    flags = short_flags(rest)                       # decoded short-flag bundles, e.g. -fq -> {f,q}
    if sub == "push":
        return "git push"
    if sub == "reset":
        return "git reset --hard" if has_long_opt(rest, "hard") else None
    if sub == "clean":
        force = "f" in flags or has_long_opt(rest, "force")
        dry = "n" in flags or has_long_opt(rest, "dry-run")
        return "git clean -f" if (force and not dry) else None
    if sub == "branch":
        force = "f" in flags or has_long_opt(rest, "force")
        delete = "d" in flags or has_long_opt(rest, "delete")
        if "D" in flags or (delete and force):
            return "git branch force-delete"
        return None
    if sub in ("checkout", "restore", "switch"):
        if "f" in flags or has_long_opt(rest, "force") or has_long_opt(rest, "discard-changes"):
            return "git " + sub + " --force"
        for t in rest:
            if whole_tree_pathspec(t):
                return "git " + sub + " <whole-tree pathspec>"
        if sub == "restore":
            staged = "S" in flags or has_long_opt(rest, "staged")
            worktree = "W" in flags or has_long_opt(rest, "worktree")
            if staged and worktree:
                return "git restore --worktree --staged"
        return None
    return None


def alias_value_dangerous(value):
    # Does this alias VALUE expand to a guarded op? Precise, not a substring match:
    #  - `!<shell>`: run the shell body through the SAME segment classifier (so `!git push;` with a
    #    glued ';' and `!git status && git push` are both caught, and `!echo hi` is NOT).
    #  - otherwise it expands to `git <value>`: skip the value's OWN global options (so `-p push` is
    #    seen as push), then dangerous if the subcommand is dangerous-when-aliased (push/checkout/
    #    restore/switch) OR the value itself is a blocked op (`reset --hard`, `clean -f`, `branch -D`).
    #    A soft `reset HEAD` or a bare `log --oneline`/`show-branch` alias is NOT flagged.
    value = value.strip()
    if not value:
        return False
    if value.startswith("!"):                       # shell-command alias: runs arbitrary shell
        return classify(value[1:]) is not None
    try:
        vtoks = shlex.split(value, posix=True)
    except ValueError:
        vtoks = value.split()
    argv = ["git"] + vtoks
    idx = find_subcommand(argv)
    if idx is None:
        return False
    return argv[idx] in ALIAS_DANGEROUS_BARE or argv_danger(argv) is not None


def is_alias_key(s):
    # A `section.name` config key whose SECTION is `alias` — case-insensitively, because git config
    # section names are case-insensitive (so ALIAS.p / Alias.p / aliaS.p all define an alias).
    return "." in s and s.split(".", 1)[0].lower() == "alias"


def alias_defs(tokens):
    # Scan a GIT invocation's tokens for alias DEFINITIONS to a guarded op.
    n = len(tokens)
    for i, t in enumerate(tokens):
        pair = None
        if t == "-c" and i + 1 < n:                 # -c alias.x=val
            pair = tokens[i + 1]
        elif t.startswith("-c") and t != "-c" and is_alias_key(t[2:]):   # -calias.x=val (glued)
            pair = t[2:]
        if pair and is_alias_key(pair) and "=" in pair:
            if alias_value_dangerous(pair.split("=", 1)[1]):
                return "alias injection (-c alias to a blocked op)"
        if t == "config":                           # config alias.x val  /  config alias.x=val
            for j in range(i + 1, n):
                a = tokens[j]
                if is_alias_key(a) and "=" in a:
                    if alias_value_dangerous(a.split("=", 1)[1]):
                        return "alias injection (config alias to a blocked op)"
                    break
                if is_alias_key(a):
                    val = tokens[j + 1] if j + 1 < n else ""
                    if alias_value_dangerous(val):
                        return "alias injection (config alias to a blocked op)"
                    break
    return None


def normalize_separators(s):
    # Convert REAL, unquoted command separators to ' ; ' so the tokenizer segments on them:
    # a newline, a subshell / command-substitution boundary `(` `)`, and a backtick. Quote-aware:
    # inside single OR double quotes NOTHING is a separator — a literal `(` or newline in a commit
    # message must not split, and command substitution INSIDE double quotes (`"$(git push)"`) is a
    # disclosed residual. Treating `(` as a separator is what frees a git word glued to a subshell
    # opener — `(git push)`, `$(git push)`, `<(git push)` — which the shell would actually run.
    out = []
    i, n = 0, len(s)
    quote = None                                    # None | "'" | '"'
    while i < n:
        c = s[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = None
            i += 1
            continue
        if quote == '"':
            if c == "\\" and i + 1 < n:
                out.append(c)
                out.append(s[i + 1])
                i += 2
                continue
            if c == '"':
                quote = None
            out.append(c)
            i += 1
            continue
        # unquoted
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(s[i + 1])
            i += 2
            continue
        if c == "'" or c == '"':
            quote = c
            out.append(c)
            i += 1
            continue
        if c == "\n" or c == BACKTICK or c == "(" or c == ")":
            out.append(" ; ")
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def segments(command):
    command = command.replace("\\\n", "")           # join backslash-newline line continuations
    command = re.sub(r"\$\{IFS[^}]*\}", " ", command)  # ${IFS}, ${IFS:...} word-split trick
    command = re.sub(r"\$IFS", " ", command)            # $IFS
    command = normalize_separators(command)
    try:
        lx = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lx.whitespace_split = True
        lx.commenters = ""                           # do not drop anything after '#'
        toks = list(lx)
    except ValueError:                               # unbalanced quotes etc.
        toks = command.split()
    segs, cur = [], []
    for t in toks:
        if t in (";", "&", "|", "&&", "||", "&|", ";;"):
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def command_word_index(tokens):
    # Index of the segment's COMMAND word (skipping leading VAR=val assignments and recognized
    # command wrappers), or None. git must be the COMMAND to be an invocation — so `echo git push`
    # and `grep -r git push` (git is an ARGUMENT) are NOT treated as running git.
    i, n = 0, len(tokens)
    assign = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    while i < n:
        t = tokens[i]
        if assign.match(t):                             # VAR=value prefix
            i += 1
            continue
        base = re.split(r"[\\/]", t)[-1].lower()
        if base in WRAPPERS:                            # env/sudo/command/... -> skip it and its opts
            i += 1
            while i < n:
                w = tokens[i]
                if assign.match(w):
                    i += 1
                    continue
                if w == "--":
                    i += 1
                    break
                if w.startswith("-") and len(w) > 1:
                    i += 1
                    if w in WRAPPER_VALUE_OPTS and i < n and not tokens[i].startswith("-"):
                        i += 1                          # consume the option's value (e.g. sudo -u USER)
                    continue
                break
            continue
        return i
    return None


def classify_segment(tokens):
    ci = command_word_index(tokens)
    if ci is None or not is_git_word(tokens[ci]):
        return None
    git_slice = tokens[ci:]
    return alias_defs(git_slice) or argv_danger(git_slice)


def classify(command):
    for seg in segments(command):
        reason = classify_segment(seg)
        if reason:
            return reason
    return None


try:
    reason = classify(os.environ.get("BLOCK_DANGEROUS_GIT_CMD", ""))
except Exception as exc:                             # never crash the agent's command on a guard bug
    sys.stderr.write("block-dangerous-git: classifier error (%s) (guard OPEN)\n" % exc.__class__.__name__)
    sys.exit(0)

if reason:
    sys.stderr.write(
        "BLOCKED: you do not have authority to run destructive git commands (matched: %s).\n" % reason
    )
    sys.stderr.write("If this is intended, the human runs it.\n")
    sys.exit(2)
sys.exit(0)
PY
rc=$?

if [ "$rc" -eq 2 ]; then
  exit 2
fi
if [ "$rc" -ne 0 ]; then
  echo "block-dangerous-git: classifier unavailable rc=$rc (guard OPEN)" >&2
  exit 0
fi
exit 0
