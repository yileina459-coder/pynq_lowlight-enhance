#!/usr/bin/env python3
"""Turn a video file into the numbered 640x480 frames the board's player expects.

Why on the PC
    Decoding video on the Zynq's PS is far slower than the pixel pipeline, so the board never
    decodes: it receives ready frames and pushes them through the overlay at the target rate. This
    script does the decoding where there is a real CPU, and uploads the sequence.

    python tools/make_video_frames.py clip.mp4 --out .tmp/frames --fps 30 --seconds 6
    python tools/board/play_video.ps1 -Video clip.mp4      # convenience wrapper

    Frames are written as frame_00000.png, frame_00001.png, ... with a predictable width/height so
    the player can fit them exactly (it letterboxes without distorting).

Why --seconds exists
    Each frame costs 640*480*3 bytes of DDR on the board, about 0.9 MB. A minute at 30 fps would be
    1.6 GB, which does not fit; six seconds is 166 MB and leaves the rest for the overlay, the frame
    buffers and Python. The limit is printed rather than enforced silently.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

WIDTH, HEIGHT = 640, 480


def frame_size_mb() -> float:
    return WIDTH * HEIGHT * 3 / (1024 * 1024)


def extract_with_ffmpeg(video: Path, out: Path, fps: float, seconds: float | None) -> int:
    if shutil.which("ffmpeg") is None:
        return 0            # not installed: the caller falls back to Pillow
    command = ["ffmpeg", "-y", "-i", str(video), "-vf",
               f"fps={fps},scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
               f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2:black",
               "-pix_fmt", "rgb24", str(out / "frame_%05d.png")]
    if seconds:
        command[-1:-1] = ["-t", str(seconds)]
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print("ffmpeg failed:")
        print(result.stderr[-800:])
        return 0
    return len(list(out.glob("frame_*.png")))


def extract_with_pillow(video: Path, out: Path, fps: float, seconds: float | None) -> int:
    """Fallback when ffmpeg is unavailable: Pillow handles GIF and animated formats only."""
    count = 0
    try:
        with Image.open(video) as img:
            index = 0
            while True:
                frame = img.convert("RGB")
                scale = min(WIDTH / frame.width, HEIGHT / frame.height)
                size = (max(1, round(frame.width * scale)), max(1, round(frame.height * scale)))
                canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
                canvas.paste(frame.resize(size, Image.LANCZOS),
                             ((WIDTH - size[0]) // 2, (HEIGHT - size[1]) // 2))
                canvas.save(out / f"frame_{index:05d}.png")
                count += 1
                index += 1
                if seconds and index >= int(seconds * fps):
                    break
                img.seek(img.tell() + 1)
    except EOFError:
        pass
    except Exception as exc:                       # noqa: BLE001
        print(f"Pillow could not read {video.name}: {exc}")
        return 0
    return count


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", required=True, help="directory for frame_*.png")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--seconds", type=float, default=6.0,
                    help="how much of the video to take (0 = all of it, watch DDR)")
    ap.add_argument("--max-frames", type=int, default=240)
    args = ap.parse_args(argv)

    video = Path(args.video)
    if not video.is_file():
        print(f"FRAMES FAIL: no such video: {video}")
        return 1

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("frame_*.png"):
        stale.unlink()

    seconds = args.seconds if args.seconds and args.seconds > 0 else None
    count = extract_with_ffmpeg(video, out, args.fps, seconds)
    if count == 0:
        print("falling back to Pillow (GIF / animated images only)")
        count = extract_with_pillow(video, out, args.fps, seconds)

    if count == 0:
        print("FRAMES FAIL: no frames produced - is ffmpeg installed?")
        return 1

    if count > args.max_frames:
        for extra in sorted(out.glob("frame_*.png"))[args.max_frames:]:
            extra.unlink()
        count = args.max_frames
        print(f"trimmed to {count} frames (--max-frames)")

    total_mb = count * frame_size_mb()
    print(f"wrote {count} frames of {WIDTH}x{HEIGHT} to {out}")
    print(f"board DDR needed: about {total_mb:.0f} MB, playback "
          f"{count / args.fps:.1f} s at {args.fps:g} fps")
    if total_mb > 300:
        print("WARNING: over 300 MB - the PS has 512 MB and the overlay needs headroom; "
              "reduce --seconds or --fps")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
