#!/usr/bin/env python3
"""Measure the picture offset from a desktop screenshot of OBS.

Why this exists
    Measuring the offset used to need a human to take a screenshot and send it. The OBS preview is
    on the same machine, so the script can capture the screen itself and measure - which turns a
    round trip into a loop that can run unattended.

How the frame is located
    OBS paints the canvas pure black (0,0,0) while the test card's own background is (18,18,20) and
    the ruler's is (0,0,0) too. So the card is used as the probe: the bounding box of every pixel
    brighter than a small threshold is the video frame, and inside it the bright page rectangle
    gives both the scale (its width is 612 source pixels) and the offset (its left edge should sit
    14 source pixels inside the frame).

    python tools/diag/measure_from_screen.py shot.png
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image

PAGE_LEFT = 14          # the card's page rectangle, in source pixels
PAGE_WIDTH = 612
SOURCE_W = 640


def frame_bbox(rgb: np.ndarray, threshold: int = 8):
    """Bounding box of everything not pure black - i.e. the video frame inside the canvas."""
    mask = rgb.max(axis=2) > threshold
    cols = np.where(mask.any(axis=0))[0]
    rows = np.where(mask.any(axis=1))[0]
    if cols.size == 0 or rows.size == 0:
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])


def page_bbox(rgb: np.ndarray, frame, page_threshold: int = 150):
    """Bounding box of the bright page rectangle inside the frame."""
    x0, y0, x1, y1 = frame
    sub = rgb[y0:y1 + 1, x0:x1 + 1]
    mask = sub.min(axis=2) > page_threshold      # the page is near-white across all channels
    cols = np.where(mask.any(axis=0))[0]
    if cols.size == 0:
        return None
    return int(cols[0]), int(cols[-1])


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    rgb = np.asarray(Image.open(argv[0]).convert("RGB"), dtype=np.int16)

    # A desktop screenshot contains the wallpaper and OBS's own panels, which are not black, so the
    # frame has to be searched for inside the preview only.
    for arg in argv[1:]:
        if arg.startswith("--crop="):
            cx0, cy0, cx1, cy1 = (int(v) for v in arg.split("=")[1].split(","))
            rgb = rgb[cy0:cy1, cx0:cx1]
            print(f"searching inside crop x {cx0}..{cx1}, y {cy0}..{cy1}")

    frame = frame_bbox(rgb)
    if frame is None:
        print("MEASURE FAIL: no video content found (is the board streaming?)")
        return 1
    x0, y0, x1, y1 = frame
    frame_w = x1 - x0 + 1
    frame_h = y1 - y0 + 1
    print(f"video frame in screenshot: x {x0}..{x1} ({frame_w} px), y {y0}..{y1} ({frame_h} px)")

    page = page_bbox(rgb, frame)
    if page is None:
        print("MEASURE FAIL: bright page not found - is the test card on screen?")
        return 1
    px0, px1 = page
    page_w = px1 - px0 + 1
    scale = page_w / PAGE_WIDTH
    print(f"page: x {px0}..{px1} ({page_w} px) -> scale {scale:.3f} "
          f"(implied source width {frame_w / scale:.0f} px)")

    offset_px = (px0 - x0) / scale - PAGE_LEFT
    print(f"page starts {(px0 - x0) / scale:.1f} source pixels inside the frame, "
          f"expected {PAGE_LEFT}")
    print(f"OFFSET: {offset_px:+.0f} source pixels "
          f"({'picture sits right' if offset_px > 0 else 'picture sits left'})")
    if abs(offset_px) <= 3:
        print("VERDICT: aligned")
    else:
        print(f"VERDICT: compensate with --roll {abs(offset_px):.0f} "
              f"({'left' if offset_px > 0 else 'right'} shift needed)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
