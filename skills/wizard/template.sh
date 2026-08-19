#!/usr/bin/env bash
# ── wizard template ──────────────────────────────────────────────────────────
# Everything ABOVE the STAGES marker is a fixed library. Never hand-edit it.
# The skill's job is only to author the stages BELOW the marker.
# Helpers: stage · say/step · open_url · ask/ask_secret · write_env ·
#          set_secret/set_var · confirm · pause
set -euo pipefail
umask 077

# ── config the authored stages set ──
TOTAL_STAGES="${TOTAL_STAGES:-1}"     # set to the real number of stages
TOTAL_MINUTES="${TOTAL_MINUTES:-5}"   # honest estimate; drives time-remaining
ENV_FILE="${ENV_FILE:-.env}"
WIZARD_ALLOWED_HOSTS="${WIZARD_ALLOWED_HOSTS:-}"

# ── palette (degrade to plain if no TTY) ──
if [ -t 1 ]; then
  BOLD=$'\033[1m'; DIM=$'\033[2m'; GARNET=$'\033[38;5;131m'; GOLD=$'\033[38;5;179m'
  JADE=$'\033[38;5;72m'; STEEL=$'\033[38;5;66m'; RESET=$'\033[0m'
else
  BOLD=""; DIM=""; GARNET=""; GOLD=""; JADE=""; STEEL=""; RESET=""
fi

_stage_n=0
declare -a _SKIPPED=()

_clear() { if [ -t 1 ]; then printf '\033[2J\033[H'; fi; }

# stage "<title>" — start a stage: clear screen, print header + progress bar.
stage() {
  _stage_n=$((_stage_n + 1))
  _clear
  local done=$((_stage_n - 1))
  local remaining_min
  remaining_min=$(( TOTAL_MINUTES - (TOTAL_MINUTES * done / (TOTAL_STAGES > 0 ? TOTAL_STAGES : 1)) ))
  printf '%s◆ Stage %d of %d%s   %s~%d min left%s\n' \
    "$GOLD" "$_stage_n" "$TOTAL_STAGES" "$RESET" "$DIM" "$remaining_min" "$RESET"
  printf '%s%s%s\n\n' "$BOLD" "$1" "$RESET"
}

# say "<line>" — a plain narration line.  step "<n>. do this" — an action line.
say()  { printf '%s\n' "$1"; }
step() { printf '  %s→%s %s\n' "$JADE" "$RESET" "$1"; }

# open_url "<url>" — open in the human's browser, cross-platform incl. WSL.
open_url() {
  local url="$1" authority host allowed=""
  case "$url" in
    https://*) ;;
    http://localhost/*|http://127.0.0.1/*) ;;
    *) printf '  %srefusing non-HTTPS or malformed URL:%s %s\n' "$GARNET" "$RESET" "$url" >&2; return 2 ;;
  esac
  authority="${url#*://}"; authority="${authority%%/*}"; authority="${authority##*@}"
  host="${authority%%:*}"
  [ -n "$host" ] || { printf '  %sinvalid URL host:%s %s\n' "$GARNET" "$RESET" "$url" >&2; return 2; }
  for allowed in $WIZARD_ALLOWED_HOSTS; do
    [ "$host" = "$allowed" ] && break
  done
  if [ "$host" != "localhost" ] && [ "$host" != "127.0.0.1" ] && [ "$host" != "$allowed" ]; then
    confirm "Open reviewed external host '$host'?" || return 1
  fi
  printf '  %sopening%s %s\n' "$STEEL" "$RESET" "$url"
  if command -v open >/dev/null 2>&1; then open "$url" >/dev/null 2>&1 || true
  elif command -v wslview >/dev/null 2>&1; then wslview "$url" >/dev/null 2>&1 || true
  elif grep -qi microsoft /proc/version 2>/dev/null && command -v explorer.exe >/dev/null 2>&1; then
    explorer.exe "$url" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url" >/dev/null 2>&1 || true
  else printf '  %s(open it manually)%s\n' "$DIM" "$RESET"; fi
}

# ask "<prompt>" VARNAME — read a visible value into VARNAME.
ask() {
  local prompt="$1" __var="$2" __val=""
  printf '  %s? %s%s ' "$GOLD" "$prompt" "$RESET"
  IFS= read -r __val
  printf -v "$__var" '%s' "$__val"
}

# ask_secret "<prompt>" VARNAME — read a hidden value (no echo).
ask_secret() {
  local prompt="$1" __var="$2" __val=""
  printf '  %s? %s%s (hidden) ' "$GOLD" "$prompt" "$RESET"
  IFS= read -rs __val; printf '\n'
  printf -v "$__var" '%s' "$__val"
}

# write_env KEY "<value>" — idempotent upsert into $ENV_FILE (KEY=value).
write_env() {
  local key="$1" val="$2" env_dir tmp="" mode=""
  case "$key" in ''|[!A-Za-z_]*|*[!A-Za-z0-9_]*) printf 'invalid env key: %s\n' "$key" >&2; return 2 ;; esac
  case "$val" in *$'\n'*|*$'\r'*) printf 'refusing multiline env value for %s\n' "$key" >&2; return 2 ;; esac
  [ ! -L "$ENV_FILE" ] || { printf 'refusing symlinked ENV_FILE: %s\n' "$ENV_FILE" >&2; return 2; }
  env_dir="$(dirname "$ENV_FILE")"
  [ -d "$env_dir" ] || { printf 'ENV_FILE directory does not exist: %s\n' "$env_dir" >&2; return 2; }
  touch "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  if grep -qE "^${key}=" "$ENV_FILE" 2>/dev/null; then
    tmp="$(mktemp "$env_dir/.wizard-env.XXXXXX")"
    chmod 600 "$tmp"
    trap 'rm -f "$tmp"' RETURN
    grep -vE "^${key}=" "$ENV_FILE" > "$tmp" || true
    printf '%s=%s\n' "$key" "$val" >> "$tmp"
    mv "$tmp" "$ENV_FILE"
    trap - RETURN
  else
    printf '%s=%s\n' "$key" "$val" >> "$ENV_FILE"
  fi
  chmod 600 "$ENV_FILE"
  if mode="$(stat -f '%Lp' "$ENV_FILE" 2>/dev/null)" || mode="$(stat -c '%a' "$ENV_FILE" 2>/dev/null)"; then
    [ "$mode" = "600" ] || { printf 'ENV_FILE mode verification failed: %s\n' "$mode" >&2; return 2; }
  fi
  printf '  %s✓ wrote %s to %s%s\n' "$JADE" "$key" "$ENV_FILE" "$RESET"
}

# set_secret NAME "<value>" — write a GitHub Actions secret (needs gh + repo).
set_secret() {
  local name="$1" val="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    if printf '%s' "$val" | gh secret set "$name" --body - >/dev/null 2>&1; then
      printf '  %s✓ set GitHub secret %s%s\n' "$JADE" "$name" "$RESET"
    else
      printf '  %s! could not set secret %s — set it manually%s\n' "$GARNET" "$name" "$RESET"
    fi
  else
    printf '  %s! gh not available — set secret %s manually%s\n' "$GARNET" "$name" "$RESET"
  fi
}

# set_var NAME "<value>" — write a GitHub Actions variable (public).
set_var() {
  local name="$1" val="$2"
  if command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; then
    gh variable set "$name" --body "$val" >/dev/null 2>&1 \
      && printf '  %s✓ set GitHub variable %s%s\n' "$JADE" "$name" "$RESET" \
      || printf '  %s! could not set variable %s%s\n' "$GARNET" "$name" "$RESET"
  else
    printf '  %s! gh not available — set variable %s manually%s\n' "$GARNET" "$name" "$RESET"
  fi
}

# confirm "<question>" — gate before an irreversible action. Returns non-zero on no.
confirm() {
  local reply=""
  printf '  %s⚠ %s%s [y/N] ' "$GARNET" "$1" "$RESET"
  IFS= read -r reply
  case "$reply" in [yY]|[yY][eE][sS]) return 0 ;; *) _SKIPPED+=("$1"); return 1 ;; esac
}

# pause "<prompt>" — wait for the human to finish a manual action.
pause() {
  printf '  %s%s%s ' "$DIM" "${1:-Press Enter when done…}" "$RESET"
  IFS= read -r _
}

_summary() {
  _clear
  printf '%s◆ Done — %d of %d stages%s\n\n' "$GOLD" "$_stage_n" "$TOTAL_STAGES" "$RESET"
  if [ "${#_SKIPPED[@]}" -gt 0 ]; then
    printf '%sSkipped:%s\n' "$GARNET" "$RESET"
    local s; for s in "${_SKIPPED[@]}"; do printf '  • %s\n' "$s"; done
  else
    printf '%sNothing skipped.%s\n' "$JADE" "$RESET"
  fi
}
trap _summary EXIT

# ── STAGES ────────────────────────────────────────────────────────────────────
# Everything below is authored per procedure. Replace this example.
# Set TOTAL_STAGES / TOTAL_MINUTES above to match what you author.

stage "Example — capture an API key"
open_url "https://dashboard.example.com/developers/api-keys"
step "Sign in, then Developers → API keys → Reveal test key → copy it."
pause
ask_secret "Paste the API key" API_KEY
write_env "EXAMPLE_API_KEY" "$API_KEY"
set_secret "EXAMPLE_API_KEY" "$API_KEY"
