#!/usr/bin/env bash
# grab.sh — pull a video's transcript AND sample frames (the two channels an analysis needs).
# Usage: grab.sh <video-url> [frame-count] [out-dir] [dedup]
#   frame-count default 100; 250+ for dense visual content (whiteboards, code, fast UI); ~60 for a talking head.
# Writes <out-dir>/transcript.txt and <out-dir>/frames/f_NNN.jpg. Fails closed on missing deps / failed download.
set -euo pipefail

URL="${1:?usage: grab.sh <video-url> [frame-count=100] [out-dir] [dedup=1]}"
N="${2:-100}"
case "$N" in ''|*[!0-9]*) echo "frame-count must be a positive integer" >&2; exit 2 ;; esac
[ "$N" -ge 1 ] || { echo "frame-count must be >= 1" >&2; exit 2; }
DEDUP="${4:-1}"   # 1 = drop near-duplicate frames that carry no new information; 0 = keep the raw cadence

for t in yt-dlp ffmpeg ffprobe python3; do
  command -v "$t" >/dev/null 2>&1 || { echo "missing dependency: $t (install yt-dlp + ffmpeg)" >&2; exit 3; }
done

ID="$(yt-dlp --no-playlist --get-id "$URL" 2>/dev/null | head -1 || true)"
[ -n "$ID" ] || ID="video"
OUT="${3:-./va-$ID}"
if [ -e "$OUT" ] && [ ! -d "$OUT" ]; then
  echo "output path exists and is not a directory: $OUT" >&2
  exit 2
fi
if [ -d "$OUT" ] && [ -n "$(find "$OUT" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  echo "output directory must be new or empty (refusing stale evidence): $OUT" >&2
  exit 2
fi
mkdir -p "$OUT/frames"

echo "[1/4] transcript…"
yt-dlp --skip-download --write-auto-subs --write-subs --sub-langs "en" --convert-subs srt \
  --no-playlist -o "$OUT/%(id)s.%(ext)s" "$URL" >/dev/null 2>&1 || true
srt="$(find "$OUT" -maxdepth 1 -type f -name '*.srt' -print | sort | head -1)"
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
  -o "$OUT/source.%(ext)s" "$URL" >/dev/null \
  || { echo "download failed — check the URL and network" >&2; exit 4; }
if find "$OUT" -maxdepth 1 -type f -name '*.part' -print -quit | grep -q .; then
  echo "download left a partial file; evidence is invalid" >&2
  exit 4
fi
sources=("$OUT"/source.*)
if [ "${#sources[@]}" -ne 1 ] || [ ! -s "${sources[0]}" ]; then
  echo "download did not produce exactly one non-empty source file" >&2
  exit 4
fi
vf="${sources[0]}"

echo "[3/4] frames (N=$N, dedup=$DEDUP)…"
dur="$(ffprobe -v error -show_entries format=duration -of csv=p=0 "$vf" | cut -d. -f1)" \
  || { echo "ffprobe could not validate the downloaded source" >&2; exit 4; }
case "$dur" in ''|*[!0-9]*) echo "invalid or missing video duration" >&2; exit 4 ;; esac
[ "$dur" -ge 1 ] || { echo "video duration must be at least one second" >&2; exit 4; }
fps="$(python3 -c "print(f'{$N/max(1,$dur):.4f}')")"
if [ "$DEDUP" = "1" ]; then
  # Sample evenly at the cadence, then mpdecimate drops any frame too similar to the last
  # KEPT one — so a frame is written only when it carries new on-screen information.
  # -fps_mode vfr actually drops the decimated frames (older ffmpeg: -vsync vfr).
  ffmpeg -v error -i "$vf" -vf "fps=$fps,mpdecimate=hi=768:lo=320:frac=0.33,setpts=N/TB" \
    -fps_mode vfr -qscale:v 3 "$OUT/frames/f_%04d.jpg" 2>/dev/null \
  || ffmpeg -v error -i "$vf" -vf "fps=$fps,mpdecimate,setpts=N/TB" \
       -vsync vfr -qscale:v 3 "$OUT/frames/f_%04d.jpg"
else
  ffmpeg -v error -i "$vf" -vf "fps=$fps" -qscale:v 3 "$OUT/frames/f_%04d.jpg"
fi
kept="$(find "$OUT/frames" -maxdepth 1 -type f -name 'f_*.jpg' -print | wc -l | tr -d ' ')"
[ "$kept" -ge 1 ] || { echo "frame extraction produced no evidence" >&2; exit 5; }

echo "[4/4] done → $OUT"
if [ "$DEDUP" = "1" ]; then
  echo "  duration=${dur}s  sampled≈${N}  kept=${kept} informative frames (near-duplicates dropped)  transcript=${srt:+$OUT/transcript.txt}"
else
  echo "  duration=${dur}s  frames=${kept}  transcript=${srt:+$OUT/transcript.txt}"
fi
