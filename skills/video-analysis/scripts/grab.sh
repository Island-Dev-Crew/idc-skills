#!/usr/bin/env bash
# grab.sh — pull a video's transcript AND sample frames (the two channels an analysis needs).
# Usage: grab.sh <video-url> [frame-count] [out-dir]
#   frame-count default 100; 250+ for dense visual content (whiteboards, code, fast UI); ~60 for a talking head.
# Writes <out-dir>/transcript.txt and <out-dir>/frames/f_NNN.jpg. Fails closed on missing deps / failed download.
set -euo pipefail

URL="${1:?usage: grab.sh <video-url> [frame-count=100] [out-dir]}"
N="${2:-100}"
case "$N" in ''|*[!0-9]*) echo "frame-count must be a positive integer" >&2; exit 2 ;; esac
[ "$N" -ge 1 ] || { echo "frame-count must be >= 1" >&2; exit 2; }

for t in yt-dlp ffmpeg ffprobe python3; do
  command -v "$t" >/dev/null 2>&1 || { echo "missing dependency: $t (install yt-dlp + ffmpeg)" >&2; exit 3; }
done

ID="$(yt-dlp --no-playlist --get-id "$URL" 2>/dev/null | head -1 || true)"
[ -n "$ID" ] || ID="video"
OUT="${3:-./va-$ID}"
mkdir -p "$OUT/frames"

echo "[1/4] transcript…"
yt-dlp --skip-download --write-auto-subs --write-subs --sub-langs "en" --convert-subs srt \
  --no-playlist -o "$OUT/%(id)s.%(ext)s" "$URL" >/dev/null 2>&1 || true
srt="$(ls "$OUT"/*.srt 2>/dev/null | head -1 || true)"
if [ -n "$srt" ]; then
  python3 - "$srt" "$OUT/transcript.txt" <<'PY'
import re, sys
lines = open(sys.argv[1], encoding='utf-8', errors='ignore').read().splitlines()
out, prev = [], ''
for l in lines:
    if re.match(r'^\d+$', l) or '-->' in l or not l.strip():
        continue
    s = l.strip()
    if s != prev:
        out.append(s); prev = s
open(sys.argv[2], 'w').write(' '.join(out))
print("  transcript words:", len(' '.join(out).split()))
PY
else
  echo "  no captions available — frames only; say so in the analysis" >&2
fi

echo "[2/4] video (<=480p)…"
yt-dlp -f 'best[height<=480]/bestvideo[height<=480]+bestaudio/best' --no-playlist \
  -o "$OUT/source.%(ext)s" "$URL" >/dev/null
vf="$(ls "$OUT"/source.* 2>/dev/null | head -1 || true)"
[ -n "$vf" ] || { echo "download failed — check the URL and network" >&2; exit 4; }

echo "[3/4] frames (N=$N)…"
dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$vf" | cut -d. -f1)"
case "$dur" in ''|*[!0-9]*) dur=1 ;; esac
[ "$dur" -ge 1 ] || dur=1
fps="$(python3 -c "print(f'{$N/max(1,$dur):.4f}')")"
ffmpeg -v error -i "$vf" -vf "fps=$fps" -qscale:v 3 "$OUT/frames/f_%03d.jpg"

echo "[4/4] done → $OUT"
echo "  duration=${dur}s  frames=$(ls "$OUT/frames" | wc -l | tr -d ' ')  transcript=${srt:+$OUT/transcript.txt}"
