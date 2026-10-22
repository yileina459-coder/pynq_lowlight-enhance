#!/usr/bin/env python3
"""Suggest the exact ``--roll`` value from a screenshot of the ruler.

Why a separate tool
    The horizontal offset is the pipeline's latency expressed in pixels, so compensating it needs
    a number rather than a guess. The reference card and the ruler both exist as files, so one
    screenshot is enough: cross-correlate it against the pattern, take the best shift, and print
    the value to pass to hdmi_show_image.py / hdmi_tour.py.

    Measuring rather than eyeballing matters - an earlier estimate from counting preview pixels
    was wrong by more than 10 pixels, and it was the user who caught it.

    python tools/calibrate_roll.py capture.png
    python tools/calibrate_roll.py capture1.png capture2.png capture3.png
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image

CARD = "data/images/testcard_640x480.png"
BORDER = 4


def build_ruler(width: int, height: int) -> np.ndarray:
    """The same ruler hdmi_ruler.py draws, for reference-based matching."""
    img = np.zeros((height, width, 3), dtype=np.int16)
    img[:, 0:8, :] = 255
    img[:, 100:108, 0] = 255
    img[:, 500:508, 2] = 255
    for x in range(0, width, 100):
        img[0:20, x:x + 4, :] = 0
        img[0:20, x:x + 4, 1] = 255
        img[height - 20:height, x:x + 4, :] = 0
        img[height - 20:height, x:x + 4, 1] = 255
    img[height // 2 - 10:height // 2 + 10, :, :] = 90
    img[:, 0:2, :] = 255
    img[:, width - 2:width, :] = 255
    return img


def best_shift(reference: np.ndarray, capture: np.ndarray, max_shift: int = 160):
    h, w, _ = capture.shape
    band = slice(int(h * 0.10), int(h * 0.90))
    ref_band = reference[band]
    cap_band = capture[band]

    best = (None, 1e18)
    for s in range(0, max_shift + 1):
        idx = (np.arange(w) + s) % w
        diff = np.abs(ref_band[:, idx, :] - cap_band).mean()
        if diff < best[1]:
            best = (s, diff)
    return best


def measure(path: str, reference: np.ndarray):
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    inner = img[BORDER:img.shape[0] - BORDER, BORDER:img.shape[1] - BORDER]
    h, w = reference.shape[:2]
    scaled = np.asarray(
        Image.fromarray(inner.astype(np.uint8)).resize((w, h), Image.BILINEAR),
        dtype=np.int16)
    return best_shift(reference, scaled)


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    use_ruler = "--pattern=ruler" in argv or any("ruler" in p.lower() for p in argv)
    argv = [a for a in argv if not a.startswith("--pattern")]
    if use_ruler:
        reference = build_ruler(640, 480)
        print("reference: the ruler pattern (hdmi_ruler.py)")
    else:
        reference = np.asarray(Image.open(CARD).convert("RGB"), dtype=np.int16)
        print(f"reference: {CARD}")

    shifts = []
    print(f"{'capture':<34}{'roll':>6}{'error':>9}")
    for path in argv:
        shift, error = measure(path, reference)
        shifts.append((shift, error))
        print(f"{path.split(chr(92))[-1][:32]:<34}{shift:>6}{error:>9.1f}")

    good = [s for s, e in shifts if e < 60]
    if not good:
        print("\nno capture matched well enough to trust; was the picture on screen?")
        return 1

    lo, hi = min(good), max(good)
    mean = sum(good) / len(good)
    print(f"\nmeasured roll: min {lo}  max {hi}  mean {mean:.0f}")
    print(f"recommended:   --roll {round(mean)}")
    if hi - lo > 4:
        print("note: the spread exceeds a few pixels, which points at the capture chain rather "
              "than the pipeline; re-measure after the sink has been stable for a while")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
