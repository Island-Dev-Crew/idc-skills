#!/usr/bin/env bash
# scan-skill.sh — deterministic risk scan of a candidate agent skill directory.
# Emits a `file:line — class — snippet` table for the reviewer to read and cite.
# ADVISORY: a regex flags candidates, it does not prove intent. Always exits 0 —
# this produces evidence, it is not a gate. Reading every hit is the human's job.
set -euo pipefail

DIR="${1:-}"
if [ -z "$DIR" ] || [ ! -d "$DIR" ]; then
  echo "usage: scan-skill.sh <path-to-candidate-skill-dir>" >&2
  exit 1
fi

# class label -> POSIX-ERE pattern. Case-insensitive match.
CLASSES=(
  "shell-exec|(\bbash\b|\bsh -c\b|\bexec\b|\bspawn\b|\bsystem\(|subprocess|child_process|os\.system)"
  "network-egress|(\bcurl\b|\bwget\b|\bnc \b|\bfetch\(|axios|urllib|requests\.(get|post))"
  "write-out-of-scope|(~/|/etc/|/usr/|\\\$HOME|%APPDATA%|\.\./\.\.)"
  "dynamic-code|(\beval[[:space:](\"']|\bFunction\(|\batob[[:space:](\"']|base64 -d)"
  "obfuscation|(base64|fromCharCode|\\\\x[0-9a-f]{2}|eval\(atob|[A-Za-z0-9+/]{40,}={0,2})"
  "credential-access|(API_KEY|SECRET|TOKEN|PASSWORD|PRIVATE_KEY|process\.env|os\.environ|getenv)"
  "unpinned-install|(pip install|npm install|cargo install|npx |uvx |\| *sh\b)"
  "shell-profile|(\.bashrc|\.zshrc|\.profile|\.bash_profile)"
  "prompt-injection|(ignore (previous|all|prior|above)|disregard (previous|all|prior)|do not (tell|inform)|without (asking|confirmation|approval)|system prompt|as (an )?(admin|root)|jailbreak)"
)

hits=0
printf '%-28s %-20s %s\n' "LOCATION" "CLASS" "SNIPPET"
printf '%-28s %-20s %s\n' "--------" "-----" "-------"

while IFS= read -r file; do
  # A non-empty file with no text lines is binary: emit one stable finding by
  # basename instead of letting grep's "Binary file ... matches" pseudo-line
  # land in the lineno field and break the file:line citation contract.
  if [ -s "$file" ] && ! LC_ALL=C grep -Iq . "$file" 2>/dev/null; then
    printf '%-28s %-20s %s\n' "$(basename "$file")" "binary-blob" "(binary file — not text-scannable)"
    hits=$((hits + 1))
    continue
  fi
  for entry in "${CLASSES[@]}"; do
    label="${entry%%|*}"
    pat="${entry#*|}"
    while IFS=: read -r lineno text; do
      [ -z "${lineno:-}" ] && continue
      snippet="$(printf '%s' "$text" | sed 's/^[[:space:]]*//' | cut -c1-60)"
      printf '%-28s %-20s %s\n' "$(basename "$file"):$lineno" "$label" "$snippet"
      hits=$((hits + 1))
    done < <(grep -nIiE -- "$pat" "$file" 2>/dev/null || true)
  done
done < <(find "$DIR" -type f 2>/dev/null)

echo
echo "scan complete: $hits candidate finding(s) across $(find "$DIR" -type f | wc -l | tr -d ' ') file(s)."
echo "ADVISORY — every hit needs a human read; a clean table is a real result, not a pass."
exit 0
