"""Measure the offset with zero geometric assumptions.

The idea
    Stop guessing the rectangle and the scale. Upload black (frame A), then upload a pattern consisting of
    a white border around the whole 640x480 frame plus two white vertical lines at x=100 and x=500 (frame
    B). The difference B - A is exactly the pattern's white pixels, so:

        * the bounding box of that difference is the full video frame - the border guarantees it;
        * the scale follows from that box (it is 640 source pixels wide by construction);
        * the two vertical lines' centres, converted with that scale, give the offset directly.

    Nothing here depends on OBS's window geometry, on a cached rectangle, or on where the preview happens
    to sit - three assumptions that each produced wrong numbers tonight.

    python tools/diag/measure_frame_lines.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import show, shot  # noqa: E402

WORK = REPO / ".tmp" / "fl"
LINE_XS = (100.0, 500.0)


def make_pattern(path: Path) -> None:
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    # 4-pixel-wide border all the way round: this is what defines the frame extent.
    draw.rectangle([0, 0, 639, 3], fill=(255, 255, 255))
    draw.rectangle([0, 476, 639, 479], fill=(255, 255, 255))
    draw.rectangle([0, 0, 3, 479], fill=(255, 255, 255))
    draw.rectangle([636, 0, 639, 479], fill=(255, 255, 255))
    for x in LINE_XS:
        draw.rectangle([x - 3, 40, x + 2, 439], fill=(255, 255, 255))
    img.save(path)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    black = WORK / "black.png"
    pattern = WORK / "frame_lines.png"
    Image.new("RGB", (640, 480), (0, 0, 0)).save(black)
    make_pattern(pattern)

    if not show(black, "pass", no_tone=True):
        return 1
    time.sleep(4)
    shot(WORK / "a_black.png")
    if not show(pattern, "pass", no_tone=True):
        return 1
    time.sleep(4)
    shot(WORK / "b_pattern.png")

    a = np.asarray(Image.open(WORK / "a_black.png").convert("L")).astype(int)
    b = np.asarray(Image.open(WORK / "b_pattern.png").convert("L")).astype(int)
    if a.shape != b.shape:
        print("captures differ in size")
        return 1
    diff = (b - a) > 80
    if diff.sum() < 1000:
        print(f"too few changed pixels ({int(diff.sum())}) - the pattern did not reach the screen")
        return 1

    rows = np.where(diff.sum(axis=1) > 3)[0]
    cols = np.where(diff.sum(axis=0) > 3)[0]
    y0, y1 = int(rows[0]), int(rows[-1])
    x0, x1 = int(cols[0]), int(cols[-1])
    width, height = x1 - x0 + 1, y1 - y0 + 1
    print(f"frame extent in the capture: x {x0}..{x1} ({width} px), y {y0}..{y1} ({height} px)")
    print(f"aspect {width / height:.3f} (expected 1.333)")

    scale_x = width / 640.0
    scale_y = height / 480.0
    sub = diff[y0:y1 + 1, x0:x1 + 1]

    # Vertical lines: columns covered over most of the frame height, excluding the border bands.
    inner = sub[:, 8:-8]
    counts = inner.sum(axis=0)
    hits = np.where(counts > inner.shape[0] * 0.6)[0]
    if hits.size == 0:
        print("no vertical lines found inside the frame")
        return 1
    runs: list[list[int]] = [[int(hits[0])]]
    for value in hits[1:]:
        if value - runs[-1][-1] <= 2:
            runs[-1].append(int(value))
        else:
            runs.append([int(value)])
    centres = [float(np.mean(run)) for run in runs]
    measured = [((c + 8) - 0) / scale_x for c in centres]
    print(f"\nscale {scale_x:.4f} capture px per source px")
    print(f"vertical lines at source x: {[round(m, 2) for m in measured]}  (expected 100.0, 500.0)")

    if len(measured) >= 2:
        offsets = [measured[0] - LINE_XS[0], measured[1] - LINE_XS[1]]
        print(f"offsets: {offsets[0]:+.2f} and {offsets[1]:+.2f} source px")
        print(f"  mean {np.mean(offsets):+.2f}   spread {abs(offsets[0] - offsets[1]):.2f}")
        mean = float(np.mean(offsets))
        print("verdict:", "no visible offset" if abs(mean) < 2 else f"offset {mean:+.1f} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
