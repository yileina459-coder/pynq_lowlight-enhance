#!/usr/bin/env python3
"""Measure the horizontal offset of each capture against the reference card.

Method
    The reference card exists as a file (data/images/testcard_640x480.png), so the offset can be
    measured instead of estimated: resize the capture's inner area to 640x480, then try every
    horizontal shift of the reference and keep the one with the lowest mean absolute difference.
    A constant offset across captures means a fixed sampling phase; a varying one means the sink
    re-locks differently each time.

    python tools/diag/measure_capture_offset.py <capture.png> [more.png ...]
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image

REFERENCE = "data/images/testcard_640x480.png"
BORDER = 4          # OBS draws a coloured rectangle around the source; ignore that many pixels


def load_capture(path: str) -> np.ndarray:
    img = Image.open(path).convert("RGB")
    return np.asarray(img, dtype=np.int16)


def best_shift(reference: np.ndarray, capture: np.ndarray, max_shift: int = 120):
    """Shift the reference left by s and compare; return the s with the lowest error."""
    h, w, _ = capture.shape
    # Compare on a horizontal band in the middle, where the card has text and colour chips.
    band = slice(int(h * 0.15), int(h * 0.55))
    ref_band = reference[band]
    cap_band = capture[band]

    best = (None, 1e18)
    for s in range(0, max_shift + 1):
        # capture[x] should equal reference[x + s]; the tail wraps around.
        idx = (np.arange(w) + s) % w
        diff = np.abs(ref_band[:, idx, :] - cap_band).mean()
        if diff < best[1]:
            best = (s, diff)
    return best


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: measure_capture_offset.py <capture.png> [...]")
        return 2

    ref_img = Image.open(REFERENCE).convert("RGB")
    reference = np.asarray(ref_img, dtype=np.int16)
    ref_h, ref_w = reference.shape[:2]

    print(f"reference {REFERENCE} ({ref_w}x{ref_h}); error is mean |difference| per channel")
    print(f"{'capture':<28}{'shift':>7}{'error':>9}")
    shifts = []
    for path in argv:
        capture = load_capture(path)
        # Strip the border OBS draws, then scale the inside to the reference size.
        inner = capture[BORDER:capture.shape[0] - BORDER, BORDER:capture.shape[1] - BORDER]
        scaled = np.asarray(
            Image.fromarray(inner.astype(np.uint8)).resize((ref_w, ref_h), Image.BILINEAR),
            dtype=np.int16)
        shift, error = best_shift(reference, scaled)
        shifts.append(shift)
        name = path.split("\\")[-1][:26]
        print(f"{name:<28}{shift:>7}{error:>9.1f}")

    if len(shifts) > 1:
        print(f"\nspread: min {min(shifts)} max {max(shifts)} "
              f"-> {'constant' if max(shifts) - min(shifts) <= 3 else 'varies between captures'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
