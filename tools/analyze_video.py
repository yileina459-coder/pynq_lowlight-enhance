#!/usr/bin/env python3
"""Choose the preset (or a preset schedule) for a video clip, before it is ever played.

The problem
    A clip is not one picture. A dark lecture recording with a bright whiteboard shot in the middle
    cannot be served well by a single tone curve; but choosing a preset per frame independently makes
    the picture pulse every time the score changes its mind, which is worse to watch than a slightly
    imperfect constant setting.

What this does
    Decodes the clip and evaluates every candidate preset on every frame *as the board would render
    it* (tools/preview_enhance.py models the kernel). Two modes:

      --mode clip       one preset for the whole clip, maximising the mean score. Perfectly steady,
                        and the safe default when the ask is "make the whole video reasonably clear".
      --mode adaptive   per-frame choice, then hysteresis plus a minimum segment length, so the preset
                        changes only when a genuinely better option persists. The output is a handful
                        of segments, not a switch per frame.

    The score is tools/score_capture.legibility, which centres the mean on 130 and penalises clipping,
    so "brighten everything" does not win.

Outputs
    schedule.txt    one preset name per frame, in order (the board plays this)
    analysis.json   per-frame scores, the clip-level ranking and the resulting segments

    python tools/analyze_video.py clip.gif --outdir .tmp/clip_analysis
    python tools/analyze_video.py frames/ --mode adaptive
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_video_frames  # noqa: E402
import preview_enhance  # noqa: E402
from score_capture import legibility, score_array  # noqa: E402

# Only presets that look compatible with each other: same polarity, same kind of mapping. Switching
# among these reads as an exposure change rather than a glitch. invert / binarize / split are stylistic
# and never chosen automatically - a clip that flipped to negative for six frames would be unwatchable
# no matter how high the score.
CANDIDATES = ["pass", "clarity", "bright", "night", "document", "reading"]

MARGIN = 12.0      # a challenger must win by this much to justify a visible switch
PERSIST = 4        # ... and must keep winning for this many frames
MIN_SEGMENT = 10   # no preset may be abandoned sooner than this many frames


def load_frames(source: str, limit: int = 0) -> list[Image.Image]:
    """Frames from a directory of frame_*.png, or decoded out of a video into a temp directory."""
    path = Path(source)
    if path.is_dir():
        files = sorted(path.glob("frame_*.png"))
        frames = [Image.open(f).convert("RGB") for f in files]
    else:
        tmp = tempfile.mkdtemp(prefix="clipframes_")
        count = make_video_frames.extract_with_ffmpeg(path, Path(tmp), 30.0, None)
        if count == 0:
            count = make_video_frames.extract_with_pillow(path, Path(tmp), 30.0, None)
        files = sorted(Path(tmp).glob("frame_*.png"))
        frames = [Image.open(f).convert("RGB") for f in files]
    return frames[:limit] if limit else frames


def score_frame(frame: Image.Image, preset: str) -> float:
    arr = np.asarray(frame.convert("RGB"))
    out = preview_enhance.enhance(arr, preview_enhance.PRESETS[preset])
    return legibility(score_array(out))


def runs_of(names: list[str]) -> list[tuple[int, int, str]]:
    runs: list[tuple[int, int, str]] = []
    start = 0
    for i in range(1, len(names) + 1):
        if i == len(names) or names[i] != names[start]:
            runs.append((start, i, names[start]))
            start = i
    return runs


def snap_boundaries(chosen: list[str], means: list[float], half: int) -> list[str]:
    """Move each segment boundary to the frame where the picture actually changes.

    A centred window necessarily straddles a cut, so the smoothed decision lands a frame or two after
    the scene change - which means a couple of frames rendered with the previous scene's preset. The
    cut itself is easy to find: it is where the frame-to-frame mean brightness jumps most. Snapping
    each boundary there keeps the switch on the cut.
    """
    runs = runs_of(chosen)
    if len(runs) < 2:
        return chosen

    segments = [[start, end, name] for start, end, name in runs]
    for i in range(1, len(segments)):
        centre = segments[i][0]
        low = max(1, centre - half)
        high = min(len(means) - 1, centre + half)
        if high <= low:
            continue
        best = max(range(low, high + 1), key=lambda k: abs(means[k] - means[k - 1]))
        # Keep every segment non-empty and never cross a neighbouring boundary.
        best = max(segments[i - 1][0] + 1, best)
        if i + 1 < len(segments):
            best = min(segments[i + 1][0] - 1, best)
        segments[i - 1][1] = best
        segments[i][0] = best

    result: list[str] = []
    for start, end, name in segments:
        result.extend([name] * max(0, end - start))
    return result[:len(chosen)] if len(result) >= len(chosen) else result + chosen[len(result):]


def smooth(scores: list[dict[str, float]], candidates: list[str],
           means: list[float] | None = None, window: int = 5) -> list[str]:
    """Turn per-frame scores into a small number of segments.

    Because the whole clip is available before playback, the choice can be made with a *centred*
    window rather than causal hysteresis - which removes the lag a hysteresis rule pays for at every
    scene change. Each frame takes the preset with the best mean score over the surrounding frames, so
    an isolated spike cannot win, and two presets that alternate frame by frame just average out.

    Segments shorter than MIN_SEGMENT that are enclosed by a single different preset on both sides are
    then merged into that neighbour: those are the runs that read as a flicker. A short run at the
    start or end of the clip is a real partial scene and is kept.
    """
    half = max(0, window // 2)
    smoothed: list[dict[str, float]] = []
    for index in range(len(scores)):
        low = max(0, index - half)
        high = min(len(scores), index + half + 1)
        smoothed.append({name: float(np.mean([scores[j][name] for j in range(low, high)]))
                         for name in candidates})

    chosen = [max(candidates, key=lambda name: row[name]) for row in smoothed]

    changed = True
    while changed:
        changed = False
        runs = runs_of(chosen)
        if len(runs) < 3:
            break
        for position in range(1, len(runs) - 1):
            start, end, _name = runs[position]
            if end - start >= MIN_SEGMENT:
                continue
            neighbour = runs[position - 1][2]
            for i in range(start, end):
                chosen[i] = neighbour
            changed = True
            break

    if means is not None:
        chosen = snap_boundaries(chosen, means, half)
    return chosen


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source", help="video file, animated image, or directory of frames")
    ap.add_argument("--outdir", default=".tmp/clip_analysis")
    ap.add_argument("--mode", choices=("clip", "adaptive"), default="clip")
    ap.add_argument("--presets", default=",".join(CANDIDATES))
    ap.add_argument("--limit", type=int, default=0, help="analyse at most N frames (0 = all)")
    args = ap.parse_args(argv)

    candidates = [name.strip() for name in args.presets.split(",") if name.strip()]
    unknown = [name for name in candidates if name not in preview_enhance.PRESETS]
    if unknown:
        print(f"ANALYSE FAIL: unknown preset(s) {unknown}; known: "
              f"{sorted(preview_enhance.PRESETS)}")
        return 1

    frames = load_frames(args.source, args.limit)
    if not frames:
        print("ANALYSE FAIL: no frames decoded")
        return 1
    print(f"{len(frames)} frames, candidates: {', '.join(candidates)}")

    scores: list[dict[str, float]] = []
    for index, frame in enumerate(frames):
        row = {name: score_frame(frame, name) for name in candidates}
        scores.append(row)
        if index % 10 == 0 or index == len(frames) - 1:
            best = max(candidates, key=lambda name: row[name])
            print(f"  frame {index:4d}: best {best:9s} "
                  + " ".join(f"{n}={row[n]:.0f}" for n in candidates), flush=True)

    means = {name: float(np.mean([row[name] for row in scores])) for name in candidates}
    ranked = sorted(means.items(), key=lambda item: -item[1])
    print("\nmean legibility over the clip:")
    for name, value in ranked:
        print(f"  {name:9s} {value:6.1f}")
    print(f"clip-level best: {ranked[0][0]}")

    # Mean brightness per frame, used to snap segment boundaries onto real scene cuts.
    frame_means = [float(np.asarray(frame.convert("L")).mean()) for frame in frames]
    schedule = (([ranked[0][0]] * len(frames)) if args.mode == "clip"
                else smooth(scores, candidates, frame_means))
    runs = runs_of(schedule)
    print(f"\nschedule: {len(runs)} segment(s)")
    for start, end, name in runs:
        print(f"  frames {start:4d}..{end - 1:4d}  ({end - start:3d} frames)  {name}")

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "schedule.txt").write_text("\n".join(schedule) + "\n", encoding="utf-8")
    (outdir / "analysis.json").write_text(json.dumps({
        "source": str(args.source),
        "frames": len(frames),
        "mode": args.mode,
        "candidates": candidates,
        "mean_scores": means,
        "clip_best": ranked[0][0],
        "segments": [{"start": s, "end": e, "frames": e - s, "preset": n} for s, e, n in runs],
        "per_frame": scores,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nwrote {outdir / 'schedule.txt'} and {outdir / 'analysis.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
