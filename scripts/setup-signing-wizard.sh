#!/usr/bin/env bash
# setup-signing-wizard.sh — walk a human through standing up the IDC Skills signing
# key IN 1Password (SSH-agent signing), so the integrity gate's green light is anchored
# to a key that never touches disk. Only the steps a human must do live here (creating
# the key in the 1Password app, approving with biometrics); everything scriptable is
# scripted. Writes ONLY public artifacts into the repo. Never sees the private key.
#
# What it produces (public, committed):
#   keys/idc-skills-signing.pub   the public signing key
#   keys/allowed_signers          the verifier's allow-list (principal + public key)
# The private key stays in 1Password. To re-sign after any change:
#   ssh-keygen -Y sign -f keys/idc-skills-signing.pub -U -n file <manifest.json>
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KEYDIR="$REPO/keys"
PRINCIPAL="idc-skills"
NAMESPACE="file"
EXPECTED_FINGERPRINT="SHA256:LBkF4ekX2Z1XQ08gjjExnku92wAgmyFA04YJqPiczbA"

bold(){ printf '\033[1m%s\033[0m\n' "$*"; }
dim(){ printf '\033[2m%s\033[0m\n' "$*"; }
ok(){ printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$*"; }
die(){ printf '  \033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }
pause(){ printf '\n\033[36m→ %s\033[0m\n   Press Enter when done…' "$*"; read -r _; }

bold "IDC Skills — signing key setup (1Password SSH agent)"
dim  "The private key is BORN and HELD in 1Password. This wizard only exports the"
dim  "PUBLIC key into the repo and proves a sign/verify round-trip works."
echo

# ── 1. prerequisites the agent CAN check ──────────────────────────────────
bold "1. Checking prerequisites"
command -v ssh-keygen >/dev/null || die "ssh-keygen not found (install OpenSSH ≥ 8.2 for -Y signing)."
ok "ssh-keygen present ($(ssh-keygen -V 2>/dev/null || echo OpenSSH))"
sshver=$(ssh -V 2>&1 | grep -oE 'OpenSSH_[0-9]+\.[0-9]+' | head -1)
ok "ssh: ${sshver:-unknown}"
if command -v op >/dev/null; then ok "1Password CLI ('op') present"; else
  warn "1Password CLI ('op') not found. Not required for agent signing, but handy."
  dim  "   Install: https://developer.1password.com/docs/cli/get-started/"
fi
mkdir -p "$KEYDIR"

# ── 2. human step: confirm the existing SSH key in 1Password ─────────────
bold "2. Confirm the existing signing key IN 1Password (human-only)"
dim  "The stable key already exists; this wizard must never create, rotate, or export its private half."
echo "   a) Open the 1Password SSH Key item \"Forge 50 SSH Key\"."
echo "   b) Confirm its fingerprint is: $EXPECTED_FINGERPRINT"
echo "   c) Open Settings → Developer → \"Use the SSH agent\" and ENABLE it."
echo "   d) (macOS) also enable \"Set up SSH agent\" so \$SSH_AUTH_SOCK points at 1Password."
pause "Confirm the existing key fingerprint and enable the 1Password SSH agent"

# ── 3. confirm the agent is serving the key ───────────────────────────────
bold "3. Confirming the 1Password SSH agent is serving your key"
# Known 1Password agent socket locations, most-specific first.
OP_SOCKS=(
  "$HOME/Library/Group Containers/2BUA8C4S2C.com.1password/t/agent.sock"
  "$HOME/.1password/agent.sock"
)
agent_has_keys(){ ssh-add -l >/dev/null 2>&1; }
# If the current SSH_AUTH_SOCK sees no keys (unset, or pointing at the default
# macOS agent), auto-try the known 1Password sockets before giving up.
if ! agent_has_keys; then
  for s in "${OP_SOCKS[@]}"; do
    if [ -S "$s" ] && SSH_AUTH_SOCK="$s" ssh-add -l >/dev/null 2>&1; then
      export SSH_AUTH_SOCK="$s"; break
    fi
  done
fi
if ! agent_has_keys; then
  warn "No keys visible via SSH_AUTH_SOCK=${SSH_AUTH_SOCK:-<unset>}."
  read -r -p "   Paste your 1Password agent socket path (or Enter to abort): " sock
  [ -n "$sock" ] && export SSH_AUTH_SOCK="$sock"
fi
agent_has_keys || die "No keys visible. Ensure 1Password is UNLOCKED and its SSH agent shows 'Running' (Settings -> Developer)."
ok "Agent reachable via: $SSH_AUTH_SOCK"
ssh-add -l | sed 's/^/     /'

# ── 4. select the public key ──────────────────────────────────────────────
bold "4. Selecting the public signing key"
# Collect public keys the agent serves. 3.2-safe (no mapfile). ssh-add -L lines
# are "type base64 comment"; the comment is the 1Password item title.
PUBS=()
while IFS= read -r line; do
  case "$line" in ssh-ed25519\ *|ssh-rsa\ *|ecdsa-*) PUBS+=("$line") ;; esac
done < <(ssh-add -L 2>/dev/null)
[ "${#PUBS[@]}" -ge 1 ] || die "Agent exposes no public keys (ssh-add -L empty)."
if [ "${#PUBS[@]}" -eq 1 ]; then
  PUB="${PUBS[0]}"
else
  echo "   The agent serves several keys. 1Password serves them without titles, so match by"
  echo "   FINGERPRINT: open your signing key item in 1Password — it shows a SHA256 fingerprint."
  echo "   Pick the number whose fingerprint matches."
  i=1
  for k in "${PUBS[@]}"; do
    fp="$(printf '%s\n' "$k" | ssh-keygen -lf - 2>/dev/null | awk '{print $2}')"
    title="$(printf '%s' "$k" | cut -d' ' -f3-)"
    printf "     [%d] %s  %s\n" "$i" "${fp:-<fp?>}" "${title:+— $title}"
    i=$((i+1))
  done
  read -r -p "   number: " sel
  case "$sel" in ''|*[!0-9]*) die "not a number" ;; esac
  PUB="${PUBS[$((sel-1))]:-}"
  [ -n "$PUB" ] || die "selection out of range"
fi
ok "selected: $(printf '%s' "$PUB" | cut -d' ' -f3- || true)"
selected_fp="$(printf '%s\n' "$PUB" | ssh-keygen -lf - 2>/dev/null | awk '{print $2}')"
[ "$selected_fp" = "$EXPECTED_FINGERPRINT" ] \
  || die "wrong signing key: expected $EXPECTED_FINGERPRINT, selected ${selected_fp:-<unknown>}"
if [ -f "$KEYDIR/idc-skills-signing.pub" ]; then
  existing_fp="$(ssh-keygen -lf "$KEYDIR/idc-skills-signing.pub" 2>/dev/null | awk '{print $2}')"
  [ "$existing_fp" = "$EXPECTED_FINGERPRINT" ] \
    || die "existing public anchor has unexpected fingerprint: ${existing_fp:-<unknown>}"
fi
# write public key + allowed_signers (public artifacts only)
printf '%s\n' "$PUB" > "$KEYDIR/idc-skills-signing.pub"
keyfield="$(printf '%s' "$PUB" | awk '{print $1" "$2}')"
printf '%s %s\n' "$PRINCIPAL" "$keyfield" > "$KEYDIR/allowed_signers"
ok "wrote keys/idc-skills-signing.pub"
ok "wrote keys/allowed_signers (principal: $PRINCIPAL)"

# ── 5. prove a sign → verify round-trip (biometric approval expected) ──────
bold "5. Proving sign → verify works end-to-end"
tmp="$(mktemp -d)"; trap 'rm -rf "$tmp"' EXIT
echo "integrity round-trip probe $(cat "$KEYDIR/idc-skills-signing.pub" | awk '{print $2}' | cut -c1-16)" > "$tmp/probe.txt"
dim  "1Password will now ask you to APPROVE the signature (biometrics) — that approval"
dim  "is the human-in-the-loop that makes the key non-forgeable."
if ssh-keygen -Y sign -f "$KEYDIR/idc-skills-signing.pub" -U -n "$NAMESPACE" "$tmp/probe.txt" >/dev/null 2>&1; then
  ok "signed probe.txt with the agent-held key"
else
  die "signing failed. Approve the 1Password prompt and re-run; ensure -U (agent) signing is supported."
fi
if ssh-keygen -Y verify -f "$KEYDIR/allowed_signers" -I "$PRINCIPAL" -n "$NAMESPACE" \
     -s "$tmp/probe.txt.sig" < "$tmp/probe.txt" >/dev/null 2>&1; then
  ok "verified the signature against keys/allowed_signers"
else
  die "verification failed — allowed_signers and the signing key do not match."
fi

# ── 6. hand-off ───────────────────────────────────────────────────────────
echo
bold "Done. The signing anchor is live."
dim  "The private key stayed in 1Password the whole time; only public artifacts were written."
echo
echo "  Commit the PUBLIC artifacts:"
echo "     git add keys/idc-skills-signing.pub keys/allowed_signers && git commit -m 'chore: add signing public key + allowed_signers'"
echo
echo "  Re-sign the manifest whenever skills change (fast; key never leaves 1Password):"
echo "     export SSH_AUTH_SOCK=\"$SSH_AUTH_SOCK\""
echo "     ssh-keygen -Y sign -f keys/idc-skills-signing.pub -U -n $NAMESPACE <manifest.json>"
echo
echo "  Bootstrap still matters: consumers must compare both public artifacts against"
echo "  the trusted out-of-band fingerprint before running repository code:"
echo "     $EXPECTED_FINGERPRINT"
