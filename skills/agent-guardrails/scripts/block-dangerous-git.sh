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
# forms), neutralizes ${IFS}/$IFS word-split tricks, understands quote/backslash/$'...' word
# concatenation (posix tokenizer), honors shell comments (`git status # ... git push` -> the push
# is comment text), decodes bundled short flags (`-df` == `-d -f`) WITHOUT mistaking an attached
# option value for flags (`checkout -bfeature` creates a branch, not a force), catches forced branch
# (re)creation (`checkout -B`, `switch -C`), and whole-tree pathspecs (`.`, `./`, `./.`, `:/`, `*`,
# `**`, pathless `:(top)`) while ALLOWING a single-file magic pathspec (`:(top)README.md`,
# `:/README.md`). It reaches git through more leading grammar — a redirection (`>/x git push`), `!`,
# a `{ }` group, an `if/then`, `|&`, and recognized wrappers (`command -p`, `nice -n 5`,
# `env --unset X`, `exec -a name`) — while treating a pure query (`command -v git`) as no invocation.
# It resolves alias DEFINITIONS to a blocked op (`-c alias.x=push`, glued `-calias.x=push`,
# `config alias.x '!git push'`) — tested by the alias VALUE actually expanding to a guarded
# subcommand, so `alias.sb=show-branch` is NOT a false positive — PLUS alias values that only become
# dangerous once COMBINED with call-site args (`-c alias.n=reset n --hard`), and git's official
# config-injection surfaces (`--config-env=alias.p=P`, `GIT_CONFIG_KEY_*/VALUE_*`).
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
# wrapper options that consume a following value, PER WRAPPER — a global set is wrong (`command -p`
# does NOT take a value, so a shared `-p` would eat the git word). Only the options a given wrapper
# actually treats as value-taking are listed; everything else is a bare flag.
WRAPPER_VOPTS = {
    "env": {"-u", "--unset", "-S", "--split-string", "-C", "--chdir"},
    "command": set(),                               # -p/-v/-V are all bare flags, not value-takers
    "sudo": {"-u", "--user", "-g", "--group", "-C", "--close-from", "-p", "--prompt",
             "-U", "-r", "--role", "-t", "--type", "-h", "--host"},
    "doas": {"-u", "-C"},
    "nice": {"-n", "--adjustment"},
    "ionice": {"-c", "--class", "-n", "--classdata", "-p", "--pid"},
    "nohup": set(),
    "setsid": set(),
    "stdbuf": {"-i", "-o", "-e"},
    "time": {"-o", "--output", "-f", "--format"},
    "exec": {"-a"},
    "builtin": set(),
}
# short options that CONSUME an argument for a given subcommand: when glued (`-bfeature`) the tail is
# the option's VALUE, not more bundled flags, so `checkout -bfeature` (create branch) is NOT a force.
SHORT_ARG = {
    "checkout": set("bB"),                          # -b/-B <new-branch>
    "switch": set("cC"),                            # -c/-C <new-branch>
    "restore": set("s"),                            # -s <source-tree>
    "clean": set("e"),                              # -e <exclude-pattern>
    "branch": set("u"),                             # -u <upstream>
}
# shell reserved words that can lead a segment before the real command word (`then git push`).
SHELL_KEYWORDS = {
    "if", "then", "else", "elif", "fi", "do", "done", "while", "until",
    "for", "case", "esac", "select", "function",
}
# a redirection token: optional fd number then a >/>>/<[/<<] operator, target possibly glued.
REDIR_RE = re.compile(r"^[0-9]*(>>?|<<?)(.*)$")

BACKTICK = chr(96)


def is_git_word(tok):
    # basename after a / or \ path, case-folded; a bare `git` or Windows `git.exe`.
    base = re.split(r"[\\/]", tok)[-1].lower()
    return base in ("git", "git.exe")


def whole_tree_pathspec(tok):
    # pathspecs that address the WHOLE tree / repo root (a discard of everything). A magic prefix
    # or a `:/` that is followed by a CONCRETE single path (`:(top)README.md`, `:/README.md`) is a
    # single-file spec and NOT whole-tree; only the pathless / glob-tailed forms discard everything.
    if tok in (".", "./", "./.", ".//", "././", ":/", ":", ":/:", "*", "**"):
        return True
    if tok.startswith(":!") or tok.startswith(":^"):   # exclude magic -> "everything EXCEPT" = whole-tree discard
        return True
    if re.fullmatch(r"\.(?:/\.?)+", tok):     # ./, ./., .//, ././ ...
        return True
    if tok.startswith(":(") and not tok.startswith(":!") and not tok.startswith(":^"):
        m = re.match(r"^:\(([^)]*)\)(.*)$", tok)   # :(magic1,magic2)pathpart
        if m:
            path = m.group(2)
            return path == "" or path in ("*", "**", ".", "./")
        return True                            # malformed :( ... -> treat as whole-tree (safe over-block)
    if tok.startswith(":/") and tok != ":/:":  # :/  handled above; :/path-from-root is a single path
        rest = tok[2:]
        return rest == "" or rest in ("*", "**", ".", "./")
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


def effective_flags(sub, tokens):
    # Decode single-dash bundles into a flag set (-df -> {d,f}), BUT a short option that takes an
    # argument for `sub` swallows the rest of its own token as a VALUE: `checkout -bfeature` -> {b}
    # (not {b,f,e,a,t,u,r}), so an attached branch name never masquerades as a force flag.
    argtaking = SHORT_ARG.get(sub, set())
    flags = set()
    for t in tokens:
        if len(t) >= 2 and t[0] == "-" and t[1] != "-":
            j = 1
            while j < len(t):
                ch = t[j]
                if ch.isalpha():
                    flags.add(ch)
                if ch in argtaking and j + 1 < len(t):
                    break                          # tail of this token is the option's value
                j += 1
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
    flags = effective_flags(sub, rest)              # decoded short-flag bundles, arg-values excluded
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
        # forced branch (re)creation discards the ref's current tip: checkout -B / switch -C.
        if sub == "checkout" and "B" in flags:
            return "git checkout -B (force branch reset)"
        if sub == "switch" and ("C" in flags or has_long_opt(rest, "force-create")):
            return "git switch -C (force branch reset)"
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
    # Two other unquoted-only lexemes are handled here so segmentation sees what bash sees:
    #  - ANSI-C / locale quoting `$'...'` / `$"..."`: the `$` is dropped so the following quote is a
    #    plain quote, letting `$'git' push` and `git $'push'` classify (escape decoding inside the
    #    quote is a disclosed dynamic residual — only the literal text is recovered).
    #  - a `#` comment that BEGINS a word (line-start, or after whitespace / a separator) runs to end
    #    of line and is dropped, so `git status # docs; git push` treats the push as comment text; a
    #    `#` mid-word (`fix#123`) or inside quotes ("fix #1") is NOT a comment.
    out = []
    i, n = 0, len(s)
    quote = None                                    # None | "'" | '"'
    prev = None                                     # previous RAW char (for `#` word-boundary test)
    while i < n:
        c = s[i]
        if quote == "'":
            out.append(c)
            if c == "'":
                quote = None
            prev = c
            i += 1
            continue
        if quote == '"':
            if c == "\\" and i + 1 < n:
                out.append(c)
                out.append(s[i + 1])
                prev = s[i + 1]
                i += 2
                continue
            if c == '"':
                quote = None
            out.append(c)
            prev = c
            i += 1
            continue
        # unquoted
        if c == "#" and (prev is None or prev in " \t\n" or prev in ";&|()" or prev == BACKTICK):
            while i < n and s[i] != "\n":           # drop the comment body; the newline stays a separator
                i += 1
            prev = "#"
            continue
        if c == "$" and i + 1 < n and s[i + 1] in ("'", '"'):
            prev = c                                # drop the ANSI-C/locale `$`; next quote is plain
            i += 1
            continue
        if c == "\\" and i + 1 < n:
            out.append(c)
            out.append(s[i + 1])
            prev = s[i + 1]
            i += 2
            continue
        if c == "'" or c == '"':
            quote = c
            out.append(c)
            prev = c
            i += 1
            continue
        if c == "\n" or c == BACKTICK or c == "(" or c == ")":
            out.append(" ; ")
            prev = c
            i += 1
            continue
        out.append(c)
        prev = c
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
        if t in (";", "&", "|", "&&", "||", "&|", "|&", ";;"):
            if cur:
                segs.append(cur)
                cur = []
        else:
            cur.append(t)
    if cur:
        segs.append(cur)
    return segs


def command_word_index(tokens):
    # Index of the segment's COMMAND word (skipping leading VAR=val assignments, leading shell
    # grammar — `!` negation, `{`/`}` group, reserved words like `then`, and redirections like
    # `>/tmp/x` — and recognized command wrappers), or None. git must be the COMMAND to be an
    # invocation — so `echo git push` and `grep -r git push` (git is an ARGUMENT) are NOT run-git.
    # For `command`, a `-v`/`-V` query form (`command -v git`) only PRINTS git's path and is not an
    # execution, so it returns None (no invocation).
    i, n = 0, len(tokens)
    assign = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
    while i < n:
        t = tokens[i]
        if t in ("!", "{", "}") or t in SHELL_KEYWORDS:  # leading shell grammar -> look past it
            i += 1
            continue
        if t[:1] in "<>0123456789" and REDIR_RE.match(t):  # redirection: skip operator (+ its target)
            m = REDIR_RE.match(t)
            if m.group(2) == "" and i + 1 < n:          # operator only -> target is the next token
                i += 2
            else:
                i += 1                                  # operator+target glued in one token
            continue
        if assign.match(t):                             # VAR=value prefix
            i += 1
            continue
        base = re.split(r"[\\/]", t)[-1].lower()
        if base in WRAPPERS:                            # env/sudo/command/... -> skip it and its opts
            vopts = WRAPPER_VOPTS.get(base, set())
            query = False
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
                    if base == "command" and w in ("-v", "-V"):
                        query = True
                    i += 1
                    if w in vopts and i < n and not tokens[i].startswith("-"):
                        i += 1                          # consume the option's value (e.g. nice -n 5)
                    continue
                break
            if base == "command" and query:
                return None                             # `command -v git` prints a path, runs nothing
            continue
        return i
    return None


def inline_c_alias_map(git_slice):
    # {name: value} for inline `-c alias.X=Y` and glued `-calias.X=Y` on THIS invocation.
    m = {}
    n = len(git_slice)
    for i, t in enumerate(git_slice):
        pair = None
        if t == "-c" and i + 1 < n:
            pair = git_slice[i + 1]
        elif t.startswith("-c") and t != "-c":
            pair = t[2:]
        if pair and is_alias_key(pair) and "=" in pair:
            key, val = pair.split("=", 1)
            m[key.split(".", 1)[1]] = val
    return m


def env_config_alias_map(assigns, git_slice):
    # {name: value} for git's OFFICIAL env/config-env injection surfaces, resolved against the
    # segment's leading assignments:
    #   - GIT_CONFIG_COUNT / GIT_CONFIG_KEY_<i> / GIT_CONFIG_VALUE_<i>  (env config injection)
    #   - `--config-env=alias.x=ENVVAR` / `--config-env alias.x=ENVVAR` (value read from $ENVVAR)
    m = {}
    keys, vals = {}, {}
    for var, val in assigns.items():
        mk = re.match(r"GIT_CONFIG_KEY_(\d+)$", var)
        if mk:
            keys[mk.group(1)] = val
        mv = re.match(r"GIT_CONFIG_VALUE_(\d+)$", var)
        if mv:
            vals[mv.group(1)] = val
    for idx, k in keys.items():
        if is_alias_key(k) and idx in vals:
            m[k.split(".", 1)[1]] = vals[idx]
    n = len(git_slice)
    for i, t in enumerate(git_slice):
        spec = None
        if t.startswith("--config-env="):
            spec = t.split("=", 1)[1]
        elif t == "--config-env" and i + 1 < n:
            spec = git_slice[i + 1]
        if spec and is_alias_key(spec) and "=" in spec:
            k, env = spec.split("=", 1)
            if is_alias_key(k) and env in assigns:
                m[k.split(".", 1)[1]] = assigns[env]
    return m


def classify_segment(tokens):
    ci = command_word_index(tokens)
    if ci is None or not is_git_word(tokens[ci]):
        return None
    git_slice = tokens[ci:]
    # leading `VAR=val` env assignments before the git word (for GIT_CONFIG_* / --config-env).
    assign = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$")
    assigns = {}
    for t in tokens[:ci]:
        mm = assign.match(t)
        if mm:
            assigns[mm.group(1)] = mm.group(2)
    # 1) alias DEFINITIONS whose value alone is a blocked op (inline -c, persistent config).
    reason = alias_defs(git_slice)
    if reason:
        return reason
    # 2) env / config-env alias definitions to a blocked op (official injection surfaces).
    env_map = env_config_alias_map(assigns, git_slice)
    for name, val in env_map.items():
        if alias_value_dangerous(val):
            return "alias injection (env/config-env alias to a blocked op)"
    # 3) an alias INVOKED here whose value COMBINES with call-site args into a blocked op
    #    (`git -c alias.n=reset n --hard` -> `git reset --hard`).
    amap = dict(inline_c_alias_map(git_slice))
    amap.update(env_map)
    idx = find_subcommand(git_slice)
    if idx is not None and git_slice[idx] in amap:
        val = amap[git_slice[idx]].strip()
        rest = git_slice[idx + 1:]
        if val.startswith("!"):
            r = classify(val[1:])
            if r:
                return r
        else:
            try:
                vtoks = shlex.split(val, posix=True)
            except ValueError:
                vtoks = val.split()
            r = argv_danger(["git"] + vtoks + rest)
            if r:
                return r
    # 4) direct invocation.
    return argv_danger(git_slice)


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
