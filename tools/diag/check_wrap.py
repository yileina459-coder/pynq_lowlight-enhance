"""Is the frame wrapped? Look for the pattern's borders on both sides.

Diagnosis it encodes
    The captured pattern showed the source shifted by a large amount with the left edge reappearing on the
    right - a horizontally wrapped frame. That happens when the output core starts reading the stream at an
    arbitrary pixel, which is exactly what the SOF marker is meant to prevent.

    So the question this answers, cheaply and without any rectangle or scale assumptions: are the pattern's
    white borders present at *both* the left and the right edge of the video area?

        both present   -> the frame is aligned
        only one/no    -> the frame is wrapped or shifted

    It uses the white border of the test pattern, which is 4 source pixels wide at the very edges.

    python tools/diag/check_wrap.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import show, shot  # noqa: E402

WORK = REPO / ".tmp" / "fl"


def main() -> int:
    pattern = WORK / "frame_lines.png"
    black = WORK / "black.png"
    if not pattern.exists():
        print("run measure_frame_lines.py once first (it creates the pattern)")
        return 1

    if not show(black, "pass", no_tone=True):
        return 1
    time.sleep(3)
    shot(WORK / "wrap_black.png")
    if not show(pattern, "pass", no_tone=True):
        return 1
    time.sleep(3)
    shot(WORK / "wrap_pattern.png")

    a = np.asarray(Image.open(WORK / "wrap_black.png").convert("L")).astype(int)
    b = np.asarray(Image.open(WORK / "wrap_pattern.png").convert("L")).astype(int)
    diff = (b - a) > 80
    if diff.sum() < 500:
        print(f"pattern did not reach the screen (changed pixels: {int(diff.sum())})")
        return 1

    rows = np.where(diff.sum(axis=1) > 3)[0]
    cols = np.where(diff.sum(axis=0) > 3)[0]
    y0, y1, x0, x1 = rows[0], rows[-1], cols[0], cols[-1]
    sub = diff[y0:y1 + 1, x0:x1 + 1]
    height, width = sub.shape

    # Border columns: bright over most of the frame height.
    coverage = sub.sum(axis=0) / height
    left_edge = coverage[:max(3, width // 25)].max() if width > 25 else coverage.max()
    right_edge = coverage[-max(3, width // 25):].max() if width > 25 else coverage.max()
    print(f"frame {width}x{height} in the capture")
    print(f"coverage at the left edge  region: {left_edge:.2f}")
    print(f"coverage at the right edge region: {right_edge:.2f}")

    aligned = left_edge > 0.6 and right_edge > 0.6
    print("frame is ALIGNED (both borders at the edges)" if aligned
          else "frame is WRAPPED or shifted (a border is missing from an edge)")
    return 0 if aligned else 2


if __name__ == "__main__":
    raise SystemExit(main())
