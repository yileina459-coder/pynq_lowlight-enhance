"""Measure the horizontal offset with a pattern whose geometry is unambiguous.

Why not the legacy ruler
    data/images/ruler_640x480.png has thin bars, scattered tick marks and colours that are easy to confuse
    with neighbouring features; measuring it produced three estimates that disagreed by 128 pixels while
    each looked plausible, and repeated attempts to identify what was on screen disagreed with the file's
    own checksum. A pattern of a few thick, isolated lines removes all of that: there is exactly one
    vertical line at each of two known positions, so the measurement can only be right or obviously wrong.

Pattern
    640x480 black, with:
      * a 4-pixel white vertical line centred on x=100
      * a 4-pixel white vertical line centred on x=500
      * a 4-pixel white horizontal line at y=240 (proves the vertical axis too)
      * a white border rectangle, 2 px, at the very edge (proves the full frame is visible)

    python tools/diag/measure_lines.py
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

WORK = REPO / ".tmp" / "lines"
LINE_X = (100.0, 500.0)
LINE_Y = 240.0


def make_pattern(path: Path) -> None:
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for x in LINE_X:
        draw.rectangle([x - 2, 0, x + 1, 479], fill=(255, 255, 255))
    draw.rectangle([0, int(LINE_Y) - 2, 639, int(LINE_Y) + 1], fill=(255, 255, 255))
    draw.rectangle([0, 0, 639, 479], outline=(255, 255, 255), width=2)
    img.save(path)


def centres(mask: np.ndarray, axis: int, min_fraction: float) -> list[float]:
    """Centre positions of the runs that cover most of the perpendicular extent."""
    counts = mask.sum(axis=axis)
    threshold = counts.max() * min_fraction
    hits = np.where(counts > threshold)[0]
    if hits.size == 0:
        return []
    runs: list[list[int]] = [[int(hits[0])]]
    for value in hits[1:]:
        if value - runs[-1][-1] <= 2:
            runs[-1].append(int(value))
        else:
            runs.append([int(value)])
    return [float(np.mean(run)) for run in runs]


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    pattern = WORK / "lines.png"
    make_pattern(pattern)

    white = WORK / "w.png"
    black = WORK / "b.png"
    Image.new("RGB", (640, 480), (255, 255, 255)).save(white)
    Image.new("RGB", (640, 480), (0, 0, 0)).save(black)

    if not show(white, "pass", no_tone=True):
        return 1
    time.sleep(4)
    shot(WORK / "cal_a.png")
    if not show(black, "pass", no_tone=True):
        return 1
    time.sleep(4)
    shot(WORK / "cal_b.png")

    a = np.asarray(Image.open(WORK / "cal_a.png").convert("L")).astype(int)
    b = np.asarray(Image.open(WORK / "cal_b.png").convert("L")).astype(int)
    diff = np.abs(a - b) > 60
    rows = np.where(diff.sum(axis=1) > 100)[0]
    cols = np.where(diff.sum(axis=0) > 80)[0]
    if rows.size < 2 or cols.size < 2:
        print("no video rectangle: is OBS previewing the board?")
        return 1
    x0, y0, x1, y1 = int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])
    width, height = x1 - x0 + 1, y1 - y0 + 1
    print(f"video rectangle {x0},{y0}..{x1},{y1}  {width}x{height}  aspect {width / height:.3f}")

    if not show(pattern, "pass", no_tone=True):
        return 1
    time.sleep(4)
    shot(WORK / "lines_shot.png")
    img = np.asarray(Image.open(WORK / "lines_shot.png").convert("L")).astype(int)
    sub = img[y0:y1 + 1, x0:x1 + 1]
    mask = sub > 150

    sx = width / 640.0
    sy = height / 480.0
    xs = centres(mask, 0, 0.7)      # vertical lines span most of the height
    ys = centres(mask, 1, 0.7)      # horizontal line spans most of the width
    print(f"found vertical lines at capture x: {[round(v, 1) for v in xs]}")
    print(f"found horizontal lines at capture y: {[round(v, 1) for v in ys]}")

    # Match detected lines to the two known ones by relative spacing, rejecting the frame border.
    inner = [v for v in xs if 20 < v < width - 20]
    if len(inner) < 2:
        print("could not find both vertical lines inside the frame")
        return 1
    pair = min(((abs((b2 - b1) - (LINE_X[1] - LINE_X[0]) * sx), b1, b2)
                for i, b1 in enumerate(inner) for b2 in inner[i + 1:]),
               key=lambda t: t[0])
    _, cap_left, cap_right = pair
    offsets = [(cap_left - LINE_X[0] * sx) / sx, (cap_right - LINE_X[1] * sx) / sx]
    print(f"\nscale {sx:.4f} x, {sy:.4f} y")
    print(f"horizontal offset from the two lines: {offsets[0]:+.2f} and {offsets[1]:+.2f} source px")
    print(f"  mean {np.mean(offsets):+.2f}  spread {abs(offsets[0] - offsets[1]):.2f}")

    inner_y = [v for v in ys if 20 < v < height - 20]
    if inner_y:
        best = min(inner_y, key=lambda v: abs(v - LINE_Y * sy))
        print(f"vertical offset: {(best - LINE_Y * sy) / sy:+.2f} source px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
