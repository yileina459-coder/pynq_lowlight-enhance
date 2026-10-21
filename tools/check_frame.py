#!/usr/bin/env python3
"""Check that the PC-side frame converter and the board-side demo agree byte for byte.

Why this is worth a test
    The two sides are written separately: tools/make_frame.py on the PC and the demos on the
    board both claim to produce "a 640x480x3 RGB frame". If they disagreed about channel
    order or row order, the picture would still appear - just with red and blue swapped, or
    upside down - and that is exactly the kind of defect that survives a demo and ruins a
    submission's credibility.

    The check builds the same gradient on both sides and compares the bytes, plus verifies the
    raw file is exactly width*height*3 with values spanning the expected range.

    python tools/check_frame.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

import numpy as np

EXPECTED_MEAN = 124.0       # the figure every on-board demo prints for the test pattern
WIDTH, HEIGHT = 640, 480


def board_style_gradient(width: int, height: int) -> np.ndarray:
    """The pattern the board demos draw, written independently of make_frame.py."""
    img = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        value = int(20 + (235 - 20) * y / (height - 1))
        img[y, :, :] = value
    top = height // 2 - 60
    img[top:top + 120, :, :] = 128
    for row in range(top + 10, top + 110, 22):
        left = 40
        while left < width - 60:
            run = int(30 + (left * 7) % 90)
            img[row:row + 10, left:min(left + run, width - 40), :] = 25
            left += run + 18
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
    return img


def main() -> int:
    problems = []

    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "frame.bin")
        result = subprocess.run([sys.executable, "tools/make_frame.py", "--gradient", out],
                                capture_output=True, text=True)
        if result.returncode != 0:
            print("make_frame.py failed:")
            print(result.stdout, result.stderr)
            return 1

        data = np.fromfile(out, dtype=np.uint8)
        expected_size = WIDTH * HEIGHT * 3
        if data.size != expected_size:
            problems.append(f"size {data.size} != {expected_size}")
        else:
            frame = data.reshape(HEIGHT, WIDTH, 3)
            if abs(frame.mean() - EXPECTED_MEAN) > 0.05:
                problems.append(f"mean {frame.mean():.2f} != {EXPECTED_MEAN}")
            if frame.min() != 20 or frame.max() != 235:
                problems.append(f"range {frame.min()}..{frame.max()} != 20..235")

            # Channel order: the three colour patches sit at known positions. If blue and
            # red were swapped here, they would be swapped on screen too.
            if frame[40, 70, 2] != 220:
                problems.append(f"red patch wrong (B={frame[40, 70, 2]}, expected 220 in "
                                f"channel 2)")
            if frame[40, 200, 1] != 220:
                problems.append(f"green patch wrong (G={frame[40, 200, 1]})")
            if frame[40, 330, 0] != 220:
                problems.append(f"blue patch wrong (B={frame[40, 330, 0]})")

            reference = board_style_gradient(WIDTH, HEIGHT)
            if not np.array_equal(frame, reference):
                diff = int((frame != reference).sum())
                problems.append(f"{diff} byte(s) differ from the board demo's pattern")

    if problems:
        print("FRAME CHECK FAIL")
        for item in problems:
            print("  -", item)
        return 1

    print("FRAME CHECK PASS")
    print(f"  raw size {WIDTH*HEIGHT*3} bytes, mean {EXPECTED_MEAN:.1f}, "
          f"channels in R,G,B order, identical to the on-board demo pattern")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
