#!/usr/bin/env python3
"""Measure the horizontal offset by locating the ruler's bars in a screen capture.

Why a dedicated tool
    The offset is the difference between where a feature should be and where it lands, so it needs a
    reference with known positions: data/images/ruler_640x480.png has a white edge bar at x=0, a blue
    bar at x=100 and a red bar at x=500. Finding those three in a capture and converting back to
    source pixels gives the offset directly, and the three estimates cross-check each other.

    The video rectangle comes from OBS's selection border (tools/find_video_rect.py), which works
    even when part of the preview is covered.

    python tools/measure_offset_screen.py shot.png
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
from find_video_rect import locate  # noqa: E402

DESIGN = {"left_edge": 0, "blue": 100, "red": 500}


def column_profile(rgb: np.ndarray) -> np.ndarray:
    return ((77 * rgb[..., 0].astype(np.int32)
             + 150 * rgb[..., 1].astype(np.int32)
             + 29 * rgb[..., 2].astype(np.int32)) >> 8).mean(axis=0)


def find_peaks(cols: np.ndarray, count: int = 6, min_gap: int = 8) -> list[int]:
    """Bright narrow bars: local maxima above a relative threshold, greedily de-duplicated."""
    threshold = cols.max() * 0.45
    order = np.argsort(cols)[::-1]
    picked: list[int] = []
    for index in order:
        if cols[index] < threshold:
            break
        if all(abs(int(index) - p) >= min_gap for p in picked):
            picked.append(int(index))
        if len(picked) >= count:
            break
    return sorted(picked)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    rect = locate(argv[0])
    if rect is None:
        print("MEASURE FAIL: video rectangle not found")
        return 1
    x0, y0, x1, y1 = rect
    print(f"video rect: {x0},{y0} .. {x1},{y1}")

    rgb = np.asarray(Image.open(argv[0]).convert("RGB")).astype(np.int32)
    # Inset to stay clear of the selection border, and skip the top/bottom rows where the ruler's
    # short ticks are, so only the long bars remain.
    inner = rgb[y0 + 40:y1 - 40, x0 + 6:x1 - 6]
    cols = column_profile(inner)
    peaks = find_peaks(cols)
    width = inner.shape[1]
    if not peaks:
        print("MEASURE FAIL: no bars found")
        return 1

    source = [round(p / max(width - 1, 1) * 639) for p in peaks]
    print(f"bars at source columns: {source}")
    print(f"design expects 0, 100, 500")

    # Match each design position to the nearest detected bar and report the difference.
    offsets = []
    for name, expected in DESIGN.items():
        nearest = min(source, key=lambda s: abs(s - expected))
        delta = nearest - expected
        if abs(delta) < 60:
            offsets.append(delta)
            print(f"  {name:9s} expected {expected:3d}, found {nearest:3d} -> offset {delta:+d}")
        else:
            print(f"  {name:9s} expected {expected:3d}, nearest {nearest:3d} (too far, ignored)")

    if offsets:
        mean = sum(offsets) / len(offsets)
        print(f"OFFSET={mean:+.1f} source pixels")
    else:
        print("OFFSET=unknown (no matching bars)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
