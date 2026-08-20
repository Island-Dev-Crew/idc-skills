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
# option value for flags (`checkout -bfeature` creates a branch, not a force), decodes forced branch
# (re)creation (`checkout -B`, `switch -C`) AND forced ref updates (`branch -f/-M/-C`, which move or
# clobber refs destructively), and whole-tree pathspecs (`.`, `./`, `./.`, `:/`, `*`, `**`, pathless
# `:(top)`, and EVERY exclude-magic spec — `:!x`, `:^x`, `:(exclude)x`, `:(top,exclude)x` — because an
# exclude-only pathspec means "everything EXCEPT x" = a whole-tree discard). Every non-literal
# wildcard restore/checkout also blocks conservatively (`?*`, `[a-z]*`, `:(glob)**/*`); explicit
# `:(literal)` keeps a concrete wildcard-named file usable. Opaque `--pathspec-from-file` input is
# blocked because its visible argv cannot prove that `.`/wildcards/every tracked path are absent.
# Concrete single-file restores/checkouts stay intentionally ALLOWED (`restore README.md`, `restore --worktree
# README.md`, `checkout HEAD -- README.md`) and their magic pathspecs (`:(top)README.md`,
# `:/README.md`). It reaches git through more leading
# grammar — a redirection (`>/x git push`), an fd-duplication (`2>&1 git push`, `>&2 git push`), a
# `+=`/array assignment (`VAR+=x git push`, `A[0]=x git push`), `!`, a `{ }` group, an `if/then`,
# `|&`, and recognized wrappers (`command -p`, `nice -n 5`, `env --unset X`, `exec -a name`,
# `env -S 'git push'` — env's split-string VALUE is word-split and re-classified, both GNU and BSD
# execute it) — while treating a pure query (`command -v git`, bundled `command -pv git`) as no
# invocation. It resolves alias DEFINITIONS to a blocked op (`-c alias.x=push`, glued
# `-calias.x=push`, `config alias.x '!git push'`) — tested by the alias VALUE actually expanding to a
# guarded subcommand, so `alias.sb=show-branch` is NOT a false positive — PLUS alias values that only
# become dangerous once COMBINED with call-site args (`-c alias.n=reset n --hard`), git's official
# config-injection surfaces (`--config-env=alias.p=P`, inherited `GIT_CONFIG_COUNT` + indexed
# `GIT_CONFIG_KEY_*/VALUE_*`, and inherited `GIT_CONFIG_PARAMETERS`), Bash `NAME+=value`, static
# export/declare/typeset/set-a/unset state across separators, `env -u/-i/-` (including bundled `-iS`),
# Git's escaped quote/bang PARAMETERS encoding, and NESTED alias chains
# (`-c alias.n='-c alias.p=push p' n`). Runtime layers follow Git precedence (COUNT, PARAMETERS,
# then argv-ordered `-c`/`--config-env`, last duplicate wins), case-fold alias names, and apply visible
# assignments plus `env -u/-i` before classification. Linear lists have exact carried state;
# conditional/pipeline/subshell syntax conservatively retains old and updated variants, capped at 32,
# so a skipped safe override cannot launder inherited danger. Malformed/oversized runtime config is
# an explicit block, with 256-entry/64-KiB parser bounds; values are parsed as data and never evaluated.
# Alias expansion is recursive, bounded by a depth cap (deeper chains block as evasion) and a cycle
# set (git refuses a pure alias loop, so it allows).
#
# It is NOT a sandbox and CANNOT be one. Documented residuals a string classifier cannot
# close (keep a real OS/repo-level control underneath — this is one layer):
#   - dynamic/indirect invocation or state: `C=git; $C push`, `$(printf push)`, `eval "git push"`,
#     sourced files, and shell functions,
#     `sh -c "git push"`, a renamed/copied git binary, base64-then-decode
#   - command substitution used to ASSEMBLE a subcommand token (`git $(echo)push` rejoins at
#     runtime), and command substitution INSIDE double quotes (`"$(git push)"`)
#   - git reached only via an UNRECOGNIZED wrapper (`xargs -I{} git push`, a shell function) or an
#     abbreviated GLOBAL value-option in separate form (`git --git-di /x push`)
#   - an alias stored in repo/global/system config (rather than one of the inspected runtime-config
#     environment/argv layers), then invoked later
#   - malformed hook payloads / missing interpreters: extraction fails or python3/jq is
#     absent -> guard OPENS (announces it, allows), by design, so a parse error cannot wedge
#     every command.
# Conservative OVER-blocks (SAFE direction — the human runs it): a heredoc BODY line that is itself a
# git command (`cat <<EOF`/`git push`/`EOF`) is blocked (segmentation can't tell heredoc data from a
# command without a full parser); `git push --dry-run` is blocked ON PURPOSE (still contacts the
# remote — an authority boundary); a wildcard pathspec is blocked even when it would match only a
# subtree (use `:(literal)` for a wildcard-named file); aliasing a discard-capable subcommand
# (`alias.co=checkout`) is blocked as the evasion pattern even though `checkout <branch>` alone is safe.
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
# NOTE: env's -S/--split-string is NOT listed here — its value is a hidden COMMAND LINE, so the
# wrapper skipper word-splits it back into the token stream instead of skipping it as a value.
WRAPPER_VOPTS = {
    "env": {"-u", "--unset", "-C", "--chdir"},
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
# a redirection token: optional fd number then a >/>>/<{1,3} operator (incl. herestring <<<),
# target possibly glued.
REDIR_RE = re.compile(r"^[0-9]*(>>?|<<?<?)(.*)$")
# bounded recursive alias resolution: a chain deeper than this blocks as evasion (safe over-block).
MAX_ALIAS_DEPTH = 8
# Runtime Git config is attacker-controlled inherited state. Bound both entry count and individual
# serialized values before parsing so a hook cannot be held in an unbounded loop. Crossing either
# ceiling is a positive block reason, not an exception that could fall into the wrapper's fail-open.
MAX_RUNTIME_CONFIG_ENTRIES = 256
MAX_RUNTIME_CONFIG_BYTES = 65536
# Cross-segment shell state is exact for a linear `;`/newline list. Conditional, pipeline, loop,
# background, and subshell syntax can leave either the old or the visibly updated exported state in
# force. Retain both possibilities, but bound the conservative state lattice so adversarial command
# text cannot turn this advisory hook into an exponential parser.
MAX_SHELL_STATE_VARIANTS = 32

# Keep shell assignment semantics separate from `env` utility operands. Bash's `NAME+=value`
# prefix appends to NAME for the command it launches; `/usr/bin/env NAME+=value ...` instead sets
# an unrelated variable literally named NAME+. Conflating them creates either a bypass or a false
# block, so the two grammars intentionally have different matchers.
SHELL_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)(\+?=)(.*)$", re.DOTALL)
ENV_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_+]*?)=(.*)$", re.DOTALL)

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
            magics = [x.strip().split("=", 1)[0].lower() for x in m.group(1).split(",")]
            if "exclude" in magics or "!" in magics or "^" in magics:
                # exclude magic means "everything EXCEPT this path": with no positive pathspec the
                # command discards the WHOLE tree (`restore ':(exclude)nope'` reverts everything),
                # so any exclude spec is treated as whole-tree (positive+exclude over-blocks — safe).
                return True
            path = m.group(2)
            if path == "" or path in ("*", "**", ".", "./"):
                return True
            if "literal" in magics:
                return False                         # explicit concrete wildcard-named path
            # A Git pathspec wildcard can address the entire tree without spelling `*` exactly:
            # `?*`, `[!.]*`, `:(glob)**/*`, and many equivalents. Conservatively treat every
            # non-literal wildcard restore/checkout as broad; `:(literal)` is the usable escape.
            return any(ch in path for ch in ("*", "?", "["))
        return True                            # malformed :( ... -> treat as whole-tree (safe over-block)
    if tok.startswith(":/") and tok != ":/:":  # :/  handled above; :/path-from-root is a single path
        rest = tok[2:]
        return (
            rest == ""
            or rest in ("*", "**", ".", "./")
            or any(ch in rest for ch in ("*", "?", "["))
        )
    return any(ch in tok for ch in ("*", "?", "["))


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


def option_args_before_pathspec_separator(rest):
    # Git's `--` ends option parsing for checkout/restore pathspecs. Keep force/config
    # detection scoped to the option side so a concrete filename such as `--force` or
    # `--pathspec-from-file` remains an intentionally usable single-file recovery target.
    try:
        return rest[:rest.index("--")]
    except ValueError:
        return rest


def argv_danger(tokens):
    # tokens[0] = git word. Return a reason string or None.
    idx = find_subcommand(tokens)
    if idx is None:
        return None
    sub = tokens[idx]
    rest = tokens[idx + 1:]
    option_rest = option_args_before_pathspec_separator(rest)
    flags = effective_flags(sub, option_rest)       # decoded short-flag bundles, arg-values excluded
    if sub == "push":
        return "git push"
    if sub == "reset":
        return "git reset --hard" if has_long_opt(option_rest, "hard") else None
    if sub == "clean":
        force = "f" in flags or has_long_opt(option_rest, "force")
        dry = "n" in flags or has_long_opt(option_rest, "dry-run")
        return "git clean -f" if (force and not dry) else None
    if sub == "branch":
        force = "f" in flags or has_long_opt(option_rest, "force")
        delete = "d" in flags or has_long_opt(option_rest, "delete")
        move = "m" in flags or has_long_opt(option_rest, "move")
        copy = "c" in flags or has_long_opt(option_rest, "copy")
        if "D" in flags or (delete and force):
            return "git branch force-delete"
        if "M" in flags or (move and force):
            return "git branch -M (force rename clobbers the target ref)"
        if "C" in flags or (copy and force):
            return "git branch -C (force copy clobbers the target ref)"
        if force:
            return "git branch --force (destructive ref move)"
        return None
    if sub in ("checkout", "restore", "switch"):
        if "f" in flags or has_long_opt(option_rest, "force") or has_long_opt(option_rest, "discard-changes"):
            return "git " + sub + " --force"
        if sub in ("checkout", "restore") and has_long_opt(option_rest, "pathspec-from-file"):
            # The visible argv does not reveal whether the external file/stdin contains `.`, a
            # wildcard, or every tracked path. Do not let an opaque pathspec source bypass the
            # whole-tree rule; a concrete single-file argv remains the intentional recovery path.
            return "git " + sub + " --pathspec-from-file (opaque whole-tree-capable pathspec)"
        # forced branch (re)creation discards the ref's current tip: checkout -B / switch -C.
        if sub == "checkout" and "B" in flags:
            return "git checkout -B (force branch reset)"
        if sub == "switch" and ("C" in flags or has_long_opt(option_rest, "force-create")):
            return "git switch -C (force branch reset)"
        for t in rest:
            if whole_tree_pathspec(t):
                return "git " + sub + " <whole-tree pathspec>"
        if sub == "restore":
            staged = "S" in flags or has_long_opt(option_rest, "staged")
            worktree = "W" in flags or has_long_opt(option_rest, "worktree")
            if staged and worktree:
                return "git restore --worktree --staged"
        return None
    return None


def alias_body_environment(config_env, alias_context, omitted_name):
    # A bang alias's shell inherits Git runtime config. Re-encode the other effective aliases through
    # COUNT so nested calls (`!git n --hard`, alias.n=reset) resolve, while omitting the alias whose
    # body is being inspected prevents a harmless `!git status` from recursively inspecting itself.
    env = dict(os.environ if config_env is None else config_env)
    for key in list(env):
        if key in ("GIT_CONFIG_COUNT", "GIT_CONFIG_PARAMETERS") or re.fullmatch(
            r"GIT_CONFIG_(?:KEY|VALUE)_[0-9]+", key
        ):
            env.pop(key, None)
    items = [(name, val) for name, val in (alias_context or {}).items() if name != omitted_name]
    env["GIT_CONFIG_COUNT"] = str(len(items))
    for idx, (name, val) in enumerate(items):
        env["GIT_CONFIG_KEY_%d" % idx] = "alias." + name
        env["GIT_CONFIG_VALUE_%d" % idx] = val
    return env


def alias_value_dangerous(value, depth=0, alias_context=None, current_name=None, config_env=None):
    # Does this alias VALUE expand to a guarded op? Precise, not a substring match:
    #  - `!<shell>`: run the shell body through the SAME segment classifier (so `!git push;` with a
    #    glued ';' and `!git status && git push` are both caught, and `!echo hi` is NOT).
    #  - otherwise it expands to `git <value>`: dangerous if the subcommand is dangerous-when-aliased
    #    (push/checkout/restore/switch) OR the expansion — resolved RECURSIVELY, so a nested chain
    #    like `-c alias.p=push p` is followed to its real endpoint — is a blocked op. A soft
    #    `reset HEAD` or a bare `log --oneline`/`show-branch` alias is NOT flagged.
    value = value.strip()
    if not value:
        return False
    if depth > MAX_ALIAS_DEPTH:
        return True                                 # can't certify a deeper chain -> safe over-block
    if value.startswith("!"):                       # shell-command alias: runs arbitrary shell
        env = alias_body_environment(config_env, alias_context, current_name)
        return classify(value[1:], depth + 1, initial_env=env) is not None
    try:
        vtoks = shlex.split(value, posix=True)
    except ValueError:
        vtoks = value.split()
    argv = ["git"] + vtoks
    idx = find_subcommand(argv)
    if idx is not None and argv[idx] in ALIAS_DANGEROUS_BARE:
        return True
    # the value may itself DEFINE or INVOKE further aliases (`-c alias.p=push p`): resolve the
    # whole expansion recursively (bounded) instead of only checking the literal argv.
    return git_invocation_danger(argv, {}, depth + 1) is not None


def is_alias_key(s):
    # A `section.name` config key whose SECTION is `alias` — case-insensitively, because git config
    # section names are case-insensitive (so ALIAS.p / Alias.p / aliaS.p all define an alias).
    return "." in s and s.split(".", 1)[0].lower() == "alias"


def alias_name(s):
    # Git config keys, including the alias subsection/name, compare case-insensitively.
    return s.split(".", 1)[1].lower()


def alias_defs(tokens, depth=0, alias_context=None, config_env=None):
    # Persistent alias DEFINITIONS live only when `config` is the actual SUBCOMMAND. Runtime
    # `-c`/`--config-env` definitions are resolved together, in argv order, by
    # command_config_alias_map(); pre-scanning one would incorrectly block a lower dangerous value
    # that a later safe value overrides. Ordinary argv after the subcommand is never config input.
    n = len(tokens)
    sub_idx = find_subcommand(tokens)
    if sub_idx is not None and tokens[sub_idx] == "config":
        for j in range(sub_idx + 1, n):             # config alias.x val  /  config alias.x=val
            a = tokens[j]
            if is_alias_key(a) and "=" in a:
                key, val = a.split("=", 1)
                if alias_value_dangerous(
                    val, depth, alias_context, alias_name(key), config_env
                ):
                    return "alias injection (config alias to a blocked op)"
                break
            if is_alias_key(a):
                val = tokens[j + 1] if j + 1 < n else ""
                if alias_value_dangerous(
                    val, depth, alias_context, alias_name(a), config_env
                ):
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
    complex_flow = False
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
        if c in "<>" and i + 1 < n and s[i + 1] == "&":
            # fd-duplication / fd-move (`2>&1`, `>&2`, `<&0`, `2>&1-`) is pure plumbing: neutralize
            # it AND its glued fd prefix to whitespace so `2>&1 git push` still finds git as the
            # command word. A non-numeric target (`>&file` = redirect-both) is rewritten to a plain
            # ` > ` so the redirection skipper consumes its target token.
            j = i + 2
            while j < n and (s[j].isdigit() or s[j] == "-"):
                j += 1
            numeric = j > i + 2 and (j >= n or s[j] in " \t\n;&|()" or s[j] == BACKTICK)
            k = 0
            while k < len(out) and len(out[-1 - k]) == 1 and out[-1 - k].isdigit():
                k += 1
            before = out[-1 - k][-1] if len(out) > k else ""
            if k and (before == "" or before in " \t\n;&|()" or before == BACKTICK):
                del out[len(out) - k:]              # the fd prefix was its own word -> drop it
            if numeric:
                out.append(" ")
                i = j
            else:
                out.append(" ")
                out.append(c)
                out.append(" ")
                i += 2
            prev = " "
            continue
        if c == ">" and i + 1 < n and s[i + 1] == "|":
            # `>|file` / `2>|file` (noclobber-override clobber): the `|` is NOT a pipe. Strip any
            # glued fd-digit prefix (so `2>|`/`9>|` leave no orphan `2`/`9` command word) exactly as
            # the fd-dup branch does, then rewrite to a plain ` > ` so the redirection skipper eats
            # the target token. A SPACE-separated digit (`echo 2 >|x`) is a real arg and is untouched.
            k = 0
            while k < len(out) and len(out[-1 - k]) == 1 and out[-1 - k].isdigit():
                k += 1
            before = out[-1 - k][-1] if len(out) > k else ""
            if k and (before == "" or before in " \t\n;&|()" or before == BACKTICK):
                del out[len(out) - k:]
            out.append(" ")
            out.append(">")
            out.append(" ")
            i += 2
            prev = " "
            continue
        if c == "\n" or c == BACKTICK or c == "(" or c == ")":
            if c != "\n":
                complex_flow = True
            out.append(" ; ")
            prev = c
            i += 1
            continue
        out.append(c)
        prev = c
        i += 1
    return "".join(out), complex_flow


def segments(command):
    command = command.replace("\\\n", "")           # join backslash-newline line continuations
    command = re.sub(r"\$\{IFS[^}]*\}", " ", command)  # ${IFS}, ${IFS:...} word-split trick
    command = re.sub(r"\$IFS", " ", command)            # $IFS
    command, complex_flow = normalize_separators(command)
    try:
        lx = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lx.whitespace_split = True
        lx.commenters = ""                           # do not drop anything after '#'
        toks = list(lx)
    except ValueError:                               # unbalanced quotes etc.
        toks = command.split()
    if any(t in ("&", "|", "&&", "||", "&|", "|&") for t in toks):
        complex_flow = True
    if any(t in SHELL_KEYWORDS for t in toks):
        complex_flow = True
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
    return segs, complex_flow


def command_word_index(tokens):
    # Index of the segment's COMMAND word (skipping leading VAR=val assignments, leading shell
    # grammar — `!` negation, `{`/`}` group, reserved words like `then`, and redirections like
    # `>/tmp/x` — and recognized command wrappers), or None. git must be the COMMAND to be an
    # invocation — so `echo git push` and `grep -r git push` (git is an ARGUMENT) are NOT run-git.
    # For `command`, a query form (`command -v git`, bundled `command -pv git`) only PRINTS git's
    # path and is not an execution, so it returns None (no invocation).
    # The assignment matcher covers plain, append, and array-element forms (`V=x`, `V+=x`, `A[0]=x`)
    # — all are pure environment prefixes the shell strips before running git.
    i, n = 0, len(tokens)
    assign = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\[[^]]*\])?\+?=")
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
                if base == "env":
                    # env's -S/--split-string VALUE is a hidden command line (GNU and BSD env both
                    # word-split and execute it, incl. the bundled `-vS'...'` form) — splice the
                    # split words back into the token stream so `env -S 'git push'` classifies.
                    sval = None
                    mS = re.match(r"^-([iv0]*)S(.*)$", w, re.DOTALL)
                    preserved = []
                    if w.startswith("--split-string="):
                        sval = w.split("=", 1)[1]
                        tokens[i:i + 1] = []
                    elif w == "--split-string" and i + 1 < n:
                        sval = tokens[i + 1]
                        tokens[i:i + 2] = []
                    elif mS and mS.group(2):
                        sval = mS.group(2)
                        preserved = ["-" + flag for flag in mS.group(1)]
                        tokens[i:i + 1] = preserved
                    elif mS and i + 1 < n:
                        sval = tokens[i + 1]
                        preserved = ["-" + flag for flag in mS.group(1)]
                        tokens[i:i + 2] = preserved
                    if sval is not None:
                        try:
                            parts = shlex.split(sval, posix=True)
                        except ValueError:
                            parts = sval.split()
                        tokens[i + len(preserved):i + len(preserved)] = parts
                        n = len(tokens)
                        continue
                if base == "env" and w == "-":
                    i += 1                              # obsolete spelling of env -i; still executes argv
                    continue
                if w.startswith("-") and len(w) > 1:
                    if base == "command" and re.fullmatch(r"-[pvV]+", w) and ("v" in w or "V" in w):
                        query = True                    # -v/-V/-pv/-pV: prints a path, runs nothing
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


def apply_shell_assignment(eff, token):
    """Apply one inert Bash assignment word to a string environment; return whether it matched."""
    mm = SHELL_ASSIGN_RE.match(token)
    if not mm:
        return False
    name, op, val = mm.groups()
    eff[name] = eff.get(name, "") + val if op == "+=" else val
    return True


def effective_environment(tokens, command_index, base_env=None):
    # Reconstruct the environment the visible git command receives. Start with the hook process
    # environment, then apply shell/wrapper assignments in order. `env -u/-i` are modeled because
    # claiming inherited-state fidelity while ignoring their removal semantics creates false blocks.
    # No value is evaluated; tokens came from the inert shell lexer above.
    eff = dict(os.environ if base_env is None else base_env)
    i, before_wrapper = 0, True
    while i < command_index:
        t = tokens[i]
        if before_wrapper and apply_shell_assignment(eff, t):
            i += 1
            continue
        # Recognized wrappers such as sudo can expose ordinary NAME=value operands. Keep the legacy
        # model for those, but do not grant Bash `+=` semantics after the wrapper command word.
        mm = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", t, re.DOTALL)
        if not before_wrapper and mm:
            eff[mm.group(1)] = mm.group(2)
            i += 1
            continue
        base = re.split(r"[\\/]", t)[-1].lower()
        if base != "env":
            if base in WRAPPERS:
                before_wrapper = False
            i += 1
            continue
        before_wrapper = False
        i += 1
        while i < command_index:
            w = tokens[i]
            mm = ENV_ASSIGN_RE.match(w)
            if mm:
                # `env NAME+=x` creates NAME+, unlike a Bash prefix assignment. Preserve that exact
                # name so it cannot poison the similarly-spelled Git runtime variable.
                eff[mm.group(1)] = mm.group(2)
                i += 1
                continue
            if w in ("-i", "--ignore-environment", "-"):
                eff.clear()
                i += 1
                continue
            if w in ("-u", "--unset"):
                if i + 1 >= command_index:
                    return {}, "malformed env --unset runtime-config wrapper"
                eff.pop(tokens[i + 1], None)
                i += 2
                continue
            if w.startswith("--unset="):
                eff.pop(w.split("=", 1)[1], None)
                i += 1
                continue
            if w.startswith("-u") and len(w) > 2:
                eff.pop(w[2:], None)
                i += 1
                continue
            if w == "--":
                i += 1
                break
            if w in ("-C", "--chdir"):
                i += 2                              # directory value; environment unchanged
                continue
            if w.startswith("--chdir=") or w.startswith("-"):
                i += 1
                continue
            break                                   # the command run by env (possibly another wrapper)
    return eff, None


def shell_state_assignment(state, token, force_export=False):
    """Apply a static shell assignment to the carried state without evaluating its bytes."""
    mm = SHELL_ASSIGN_RE.match(token)
    if not mm:
        return False
    name, op, val = mm.groups()
    prior = state["vars"].get(name, "")
    state["vars"][name] = prior + val if op == "+=" else val
    if force_export or state["allexport"]:
        state["exported"].add(name)
    return True


def update_persistent_shell_state(tokens, state):
    # Carry only static, directly visible shell state across `;`/`&&` segments. This closes a real
    # runtime-config path (`export GIT_CONFIG_PARAMETERS=...; git p`) without pretending to evaluate
    # dynamic `eval`, sourced files, functions, or substitutions (documented classifier residuals).
    if tokens and all(SHELL_ASSIGN_RE.match(t) for t in tokens):
        for t in tokens:                              # assignment-only command persists in the shell
            shell_state_assignment(state, t)
        return

    probe = list(tokens)
    ci = command_word_index(probe)
    if ci is None:
        return
    base = re.split(r"[\\/]", probe[ci])[-1].lower()
    persistent = {":", "export", "readonly", "unset", "set", "declare", "typeset"}
    if base not in persistent:
        return

    # Assignment prefixes to POSIX special builtins persist. Preserve an inherited export attribute;
    # an unexported name becomes exported only through export/-x or `set -a`.
    for t in probe[:ci]:
        if SHELL_ASSIGN_RE.match(t):
            shell_state_assignment(state, t)

    args = probe[ci + 1:]
    if base == ":":
        return
    if base == "set":
        i = 0
        while i < len(args):
            if args[i] == "-a" or (args[i:i + 2] == ["-o", "allexport"]):
                state["allexport"] = True
                i += 2 if args[i] == "-o" else 1
                continue
            if args[i] == "+a" or (args[i:i + 2] == ["+o", "allexport"]):
                state["allexport"] = False
                i += 2 if args[i] == "+o" else 1
                continue
            i += 1
        return
    if base == "unset":
        for t in args:
            if t == "--" or t.startswith("-"):
                continue
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", t):
                state["vars"].pop(t, None)
                state["exported"].discard(t)
        return
    if base == "readonly":
        for t in args:
            if not t.startswith("-"):
                shell_state_assignment(state, t)
        return

    if base in ("declare", "typeset"):
        export_mode = None
        for t in args:
            if t.startswith("-") and "x" in t[1:]:
                export_mode = True
                continue
            if t.startswith("+") and "x" in t[1:]:
                export_mode = False
                continue
            if t.startswith("-") or t == "--":
                continue
            matched = shell_state_assignment(state, t, force_export=(export_mode is True))
            name = SHELL_ASSIGN_RE.match(t).group(1) if matched else t
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
                if export_mode is True:
                    state["exported"].add(name)
                elif export_mode is False:
                    state["exported"].discard(name)
        return

    # export [-n] NAME[=value] ...
    unexport = False
    for t in args:
        if t == "-n":
            unexport = True
            continue
        if t == "--" or t.startswith("-"):
            continue
        matched = shell_state_assignment(state, t, force_export=not unexport)
        name = SHELL_ASSIGN_RE.match(t).group(1) if matched else t
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            continue
        if unexport:
            state["exported"].discard(name)
        else:
            state["exported"].add(name)


def exported_shell_environment(state):
    return {name: state["vars"][name] for name in state["exported"] if name in state["vars"]}


def clone_shell_state(state):
    return {
        "vars": dict(state["vars"]),
        "exported": set(state["exported"]),
        "allexport": state["allexport"],
    }


def shell_state_fingerprint(state):
    # Full exported-variable values matter: `--config-env=alias.p=P` may name any visible variable,
    # not only the GIT_CONFIG_* family. The bounded variant count keeps this exact key affordable.
    return (
        tuple(sorted(state["vars"].items())),
        tuple(sorted(state["exported"])),
        state["allexport"],
    )


def parse_git_config_parameters(raw):
    # Strictly parse Git's own serialized `-c` environment: quoted entries only, each
    # `'section.key'='value'`, `'section.key=value'`, or `'section.key'`. A malformed or oversized
    # channel returns an explicit BLOCK reason; it never throws into the wrapper's fail-open.
    if len(raw) > MAX_RUNTIME_CONFIG_BYTES:
        return {}, "GIT_CONFIG_PARAMETERS exceeds the bounded parser"
    out = {}
    i, n, entries = 0, len(raw), 0

    def read_sq_component(pos, stop_on_equals):
        # Git serializes each shell word as one or more adjacent single-quoted chunks. Outside a
        # chunk, sq_quote_buf uses `\'` for a literal quote and `\!` for a literal bang (the latter
        # appears as `''\!'text'`). Parse that data grammar directly; never hand it to a shell.
        if pos >= n or raw[pos] != "'":
            return "", pos, "malformed GIT_CONFIG_PARAMETERS quoted component"
        buf = []
        while pos < n and raw[pos] not in " \t" and not (stop_on_equals and raw[pos] == "="):
            if raw[pos] == "'":
                pos += 1
                while pos < n and raw[pos] != "'":
                    buf.append(raw[pos])
                    pos += 1
                if pos >= n:
                    return "", pos, "unterminated GIT_CONFIG_PARAMETERS quote"
                pos += 1
                continue
            if raw[pos] == "\\" and pos + 1 < n and raw[pos + 1] in ("'", "!"):
                buf.append(raw[pos + 1])
                pos += 2
                continue
            return "", pos, "malformed GIT_CONFIG_PARAMETERS quoted continuation"
        return "".join(buf), pos, None

    while i < n:
        while i < n and raw[i] in " \t":
            i += 1
        if i >= n:
            break
        entries += 1
        if entries > MAX_RUNTIME_CONFIG_ENTRIES:
            return {}, "GIT_CONFIG_PARAMETERS exceeds the entry bound"
        if raw[i] != "'":
            return {}, "malformed GIT_CONFIG_PARAMETERS entry"
        key, i, issue = read_sq_component(i, True)
        if issue:
            return {}, issue
        val = ""
        if i < n and raw[i] == "=":
            i += 1
            val, i, issue = read_sq_component(i, False)
            if issue:
                return {}, issue
        elif "=" in key:                           # serialized one-token `key=value` form
            key, val = key.split("=", 1)
        if not key or len(key) > MAX_RUNTIME_CONFIG_BYTES or len(val) > MAX_RUNTIME_CONFIG_BYTES:
            return {}, "GIT_CONFIG_PARAMETERS key/value exceeds the bound"
        if i < n and raw[i] not in " \t":
            return {}, "malformed GIT_CONFIG_PARAMETERS separator"
        if is_alias_key(key):
            out[alias_name(key)] = val              # last duplicate in this layer wins
    return out, None


def inherited_runtime_alias_map(eff):
    # Git applies indexed COUNT entries first, then GIT_CONFIG_PARAMETERS. Preserve that precedence
    # and last-duplicate-wins behavior exactly for aliases; stray indexed vars outside COUNT are inert.
    out = {}
    if "GIT_CONFIG_COUNT" in eff and eff.get("GIT_CONFIG_COUNT", "") != "":
        raw_count = eff.get("GIT_CONFIG_COUNT", "")
        if len(raw_count) > 32 or not re.fullmatch(r"[ \t]*\+?[0-9]+[ \t]*", raw_count):
            return {}, "malformed GIT_CONFIG_COUNT"
        count = int(raw_count, 10)
        if count > MAX_RUNTIME_CONFIG_ENTRIES:
            return {}, "GIT_CONFIG_COUNT exceeds the entry bound"
        for idx in range(count):
            kname, vname = "GIT_CONFIG_KEY_%d" % idx, "GIT_CONFIG_VALUE_%d" % idx
            if kname not in eff or vname not in eff:
                return {}, "GIT_CONFIG_COUNT entry is missing key/value"
            key, val = eff[kname], eff[vname]
            if len(key) > MAX_RUNTIME_CONFIG_BYTES or len(val) > MAX_RUNTIME_CONFIG_BYTES:
                return {}, "GIT_CONFIG_COUNT key/value exceeds the bound"
            if is_alias_key(key):
                out[alias_name(key)] = val           # ascending index => last duplicate wins
    if "GIT_CONFIG_PARAMETERS" in eff:
        params, issue = parse_git_config_parameters(eff.get("GIT_CONFIG_PARAMETERS", ""))
        if issue:
            return {}, issue
        out.update(params)                           # PARAMETERS has higher precedence than COUNT
    return out, None


def command_config_alias_map(git_slice, eff, lower):
    # Overlay the highest runtime-config layer in actual argv order. Only Git GLOBAL options before
    # the resolved subcommand count; `git status -- -c alias.p=push` is ordinary argv, not config.
    out = dict(lower)
    n = len(git_slice)
    sub_idx = find_subcommand(git_slice)
    end = sub_idx if sub_idx is not None else n
    i, entries = 1, 0
    while i < end:
        t, pair, spec = git_slice[i], None, None
        if t == "-c":
            if i + 1 >= end:
                return {}, "malformed git -c runtime config"
            pair = git_slice[i + 1]
            i += 2
        elif t.startswith("-c") and t != "-c":
            pair = t[2:]
            i += 1
        elif t == "--config-env":
            if i + 1 >= end:
                return {}, "malformed git --config-env runtime config"
            spec = git_slice[i + 1]
            i += 2
        elif t.startswith("--config-env="):
            spec = t.split("=", 1)[1]
            i += 1
        else:
            i += 1
            continue
        entries += 1
        if entries > MAX_RUNTIME_CONFIG_ENTRIES:
            return {}, "git command config exceeds the entry bound"
        if pair is not None:
            if len(pair) > MAX_RUNTIME_CONFIG_BYTES:
                return {}, "git -c value exceeds the bound"
            key, val = pair.split("=", 1) if "=" in pair else (pair, "")
        else:
            if not spec or "=" not in spec:
                return {}, "malformed git --config-env specification"
            key, env_name = spec.split("=", 1)
            if env_name not in eff:
                return {}, "git --config-env names a missing variable"
            val = eff[env_name]
            if len(key) > MAX_RUNTIME_CONFIG_BYTES or len(val) > MAX_RUNTIME_CONFIG_BYTES:
                return {}, "git --config-env key/value exceeds the bound"
        if is_alias_key(key):
            out[alias_name(key)] = val               # argv order: later -c/config-env wins
    return out, None


def git_invocation_danger(git_slice, inherited, depth=0, seen=None, config_env=None):
    # Classify ONE git invocation (git_slice[0] is the git word), resolving an INVOKED alias
    # RECURSIVELY the way git itself expands nested aliases: the alias name is replaced by the
    # value's tokens, keeping the call-site args (`git -c alias.n='-c alias.p=push p' n X` ->
    # `git -c alias.n=... -c alias.p=push p X` -> ... -> `git ... push X`). Bounded two ways:
    # a depth cap (a deeper chain blocks as evasion — safe over-block) and a seen-set for cycles
    # (git refuses an alias loop outright, so nothing executes and a pure cycle is not danger).
    if depth > MAX_ALIAS_DEPTH:
        return "alias chain deeper than the bounded resolver (blocked as evasion)"
    if seen is None:
        seen = set()
    if config_env is None:
        config_env = {}
    # 1) Resolve COUNT/PARAMETERS (already in `inherited`) plus the single highest command-line
    #    layer (-c and --config-env in argv order), then inspect only the effective final aliases.
    amap, issue = command_config_alias_map(git_slice, config_env, inherited)
    if issue:
        return issue
    for name, val in amap.items():
        if alias_value_dangerous(val, depth, amap, name, config_env):
            return "effective runtime-config alias resolves to a blocked op"
    # A persistent `git config alias...` mutation is a separate subcommand surface.
    reason = alias_defs(git_slice, depth, amap, config_env)
    if reason:
        return reason
    # 2) An alias INVOKED here: expand it while retaining call-site args. Alias names are
    #    case-insensitive in Git config, even though real subcommand names are not.
    idx = find_subcommand(git_slice)
    invoked = git_slice[idx].lower() if idx is not None else None
    if idx is not None and invoked in amap and invoked not in seen:
        name = invoked
        val = amap[name].strip()
        if val.startswith("!"):
            if alias_value_dangerous(val, depth, amap, name, config_env):
                return "invoked bang alias resolves to a blocked op"
        else:
            try:
                vtoks = shlex.split(val, posix=True)
            except ValueError:
                vtoks = val.split()
            expanded = git_slice[:idx] + vtoks + git_slice[idx + 1:]
            r = git_invocation_danger(expanded, inherited, depth + 1, seen | {name}, config_env)
            if r:
                return r
    # 3) direct invocation.
    return argv_danger(git_slice)


def classify_segment(tokens, depth=0, base_env=None):
    ci = command_word_index(tokens)
    if ci is None or not is_git_word(tokens[ci]):
        return None
    git_slice = tokens[ci:]
    eff, issue = effective_environment(tokens, ci, base_env)
    if issue:
        return issue
    runtime_map, issue = inherited_runtime_alias_map(eff)
    if issue:
        return issue
    return git_invocation_danger(git_slice, runtime_map, depth, config_env=eff)


def classify(command, depth=0, initial_env=None):
    initial = dict(os.environ if initial_env is None else initial_env)
    initial_state = {
        "vars": initial,
        "exported": set(initial),
        "allexport": False,
    }
    segs, complex_flow = segments(command)
    states = [initial_state]
    for seg in segs:
        # A destructive invocation feasible under ANY carried shell state is enough to block.
        for state in states:
            reason = classify_segment(seg, depth, exported_shell_environment(state))
            if reason:
                return reason

        evolved = []
        for state in states:
            updated = clone_shell_state(state)
            update_persistent_shell_state(seg, updated)
            if complex_flow and shell_state_fingerprint(updated) != shell_state_fingerprint(state):
                # A conditional/pipeline/subshell mutation may or may not affect the later command.
                # Keep both possibilities; this is deliberately conservative in the safe direction.
                evolved.append(state)
            evolved.append(updated)

        unique = {}
        for state in evolved:
            unique[shell_state_fingerprint(state)] = state
            if len(unique) > MAX_SHELL_STATE_VARIANTS:
                return "ambiguous shell runtime-config state exceeds the bounded resolver"
        states = list(unique.values())
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
