---
name: video-analysis
description: Turn a video URL into a grounded, structured analysis by pulling its transcript AND sampling frames at a chosen cadence — because the transcript captures only what was said, and the frames recover what was shown (diagrams, code, UI, demos). Use when the user drops a YouTube or other video link to analyze, says "analyze this video", "watch this", "what's in this talk", "pull the transcript and frames", or wants a video turned into notes. Differentiator - two channels not one; every claim is cited to a transcript line or a frame number, never invented, and the frame count scales to how visually dense the video is.
---

# Video Analysis — two channels, not one

A transcript is what was *said*; the frames are what was *shown*. Analyze a video from both, or you miss everything shown-not-said — the diagram on the whiteboard, the code on screen, the UI in the demo, the number on the chart behind the claim. This island pulls both channels and synthesizes them into grounded notes, every point cited to a transcript line or a frame.

## The one insight

Auto-transcripts drop all visual signal and mangle names — a real capture rendered `CLAUDE.md` as "claw.md" and "routing" as "rootle". The frames put the visual channel back *and* let you correct the transcript against what is literally on screen. Neither channel alone is trustworthy; together they cross-check.

## Pull both — one command

[scripts/grab.sh](scripts/grab.sh) takes a URL, a frame count, and an out-dir; it writes `transcript.txt` and `frames/f_NNN.jpg`, choosing the frame cadence as count ÷ duration so the frames spread evenly across the whole runtime.

```bash
<this-skill-dir>/scripts/grab.sh <video-url> [frame-count] [out-dir] [dedup]
# e.g. grab.sh https://youtu.be/ID 250 ./va-talk      # 250-frame cadence, near-duplicates dropped
# e.g. grab.sh https://youtu.be/ID 250 ./va-talk 0    # keep the raw cadence (no dedup)
```

Needs `yt-dlp`, `ffmpeg` (ships `ffprobe`), and `python3` — the script fails loudly if any is missing.

**Dedup keeps only informative frames.** By default the script samples at the cadence, then `mpdecimate` drops any frame too visually similar to the last *kept* one — so a held slide sampled 60 times collapses to the one frame where it appeared, and the frame count reported is *informative frames*, not raw cadence. This is a **pixel-level** near-duplicate drop, not a semantic one: it removes visually-static repeats (held slides, a paused screen), but two frames that differ visually yet say the same thing still both survive — judging *relevance* stays yours. On a genuinely dynamic video (a moving whiteboard, constant camera motion) almost nothing is a duplicate and the set stays dense; that is correct, not a failure. Pass `dedup=0` to keep the raw cadence when you want a fixed, evenly-timed sample.

## Choose the frame count to the video, not a default

The cadence is count ÷ duration — so the count is really *how much visual detail do I need to not miss anything?*

- **~60** — a talking head with almost nothing on screen.
- **~100** — a normal explainer with occasional slides.
- **250+** — dense visual content: whiteboards being drawn, code being typed, fast UI, rapid cuts. When a single moment carries the point (a full architecture diagram appears once), sample dense enough to land on it.

A frame every few seconds still misses a one-frame flash — state that the frames are a sample, not the whole video. The count is a target, not a guarantee — `fps=count÷duration` may land a few frames over.

## Synthesize — the spine from words, the detail from frames

1. **Read the transcript for the spine** — the thesis and the order of the argument. Fix obvious auto-caption garbles against the frames (names, paths, jargon).
2. **Sample the frames for what the words skip** — architecture diagrams, on-screen code and file paths, UI states, numbers on a chart. Record the frame number for each.
3. **Write the analysis** grounded in both: thesis · section-by-section · **what the frames add that the transcript never said** (the highest-value section) · claims worth verifying · the so-what or decision. Cite every point to a transcript quote or a frame number.
4. **Cite or flag.** A claim you cannot ground in a transcript line or a frame is `unverified` — never fill the gap from memory. Same rule as [`research`](../research/SKILL.md): sourced or flagged, no third state.

## Honest boundaries

- The transcript may be auto-generated and wrong; the frames are a fixed-cadence sample that can skip a brief on-screen moment. Both are evidence to cross-check, not ground truth — state which claims rest on which channel.
- Downloading the media is the one side-effect; it lands in a scratch out-dir, never the repo. On a metered or shared machine, confirm before pulling a long or large video.
- `enforced`: the script fails closed on a missing dependency, an unparseable frame count, or a failed download (non-zero exit). `advisory`: judging *what a frame shows* is yours — say which claims are your read of a frame versus a transcript quote.

## Where this sits

A video is a primary source — this is the media-extraction leaf that feeds [`research`](../research/SKILL.md) (cite the video the way research cites any source). To make the write-up readable, [`wait-what`](../wait-what/SKILL.md) is the tool — but it is **user-invoked**, so you cannot trigger it; tell the human to invoke it on the finished write-up. Reach for [`folder-workspace`](../folder-workspace/SKILL.md) when a batch of videos becomes a knowledge bundle.

**No authority without evidence. The transcript is what was said; the frame is what was shown; cite which.**
