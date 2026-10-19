"""Look for a preset that lifts a dim page without flipping its polarity.

Finding that motivated this: with `knee = 48`, everything brighter than the knee
is compressed towards the knee while everything darker is multiplied by
gain_lo/16, so on a dim page the paper (below the knee) overtakes the ink and the
page comes out as dark-on-light. Measured on the board capture:
bars 62.7 -> 62.8, paper 21.4 -> 114.1, i.e. contrast -51 instead of +41.

If the whole page sits below the knee, both are scaled by the same slope, so
polarity is preserved and the paper just clips at 255. That is what this script
searches for, scoring by legibility rather than by taste:

    contrast  = mean(text) - mean(paper)        (want positive and large)
    dark %    = share of pixels below luma 32   (want small: it was 84% before)
    clip %    = share of pixels above 250       (want small: avoid burning out)
"""

from __future__ import annotations

import itertools
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))   # sim/enhance -> repo root
sys.path.insert(0, os.path.join(REPO, "sim", "enhance"))
sys.path.insert(0, os.path.join(REPO, "sim", "common"))

import golden_enhance as golden  # noqa: E402

page = np.asarray(Image.open(os.path.join(
    REPO, "data", "images", "test_dim_720p.png")).convert("RGB"))
src_luma = golden.luma(page).astype(np.float64)
text = src_luma >= 40          # brighter marks on this synthetic page
paper = ~text


def score(img: np.ndarray) -> tuple[float, float, float, float]:
    y = golden.luma(img).astype(np.float64)
    contrast = float(y[text].mean() - y[paper].mean())
    dark = float((y < 32).mean() * 100.0)
    clip = float((y > 250).mean() * 100.0)
    return contrast, dark, clip, float(y.mean())


def main() -> int:
    base = score(page)
    print(f"input                contrast {base[0]:+6.1f}  dark {base[1]:5.1f}%  "
          f"clip {base[2]:5.1f}%  mean {base[3]:6.1f}")

    reading = score(golden.render(page, "reading"))
    print(f"preset reading       contrast {reading[0]:+6.1f}  dark {reading[1]:5.1f}%  "
          f"clip {reading[2]:5.1f}%  mean {reading[3]:6.1f}   <- polarity flipped")

    best = None
    for clarity, knee, lo, hi in itertools.product(
            (16, 20, 24, 28), (192, 224, 255), (48, 64, 80, 96), (12, 16, 20)):
        img = golden.enhance(page, clarity=clarity, knee=knee, gain_lo=lo, gain_hi=hi)
        c, dark, clip, mean = score(img)
        # want: positive contrast, few dark pixels, almost no clipping
        if c <= 20 or clip > 8.0:
            continue
        value = c - 0.8 * dark - 1.5 * clip
        if best is None or value > best[0]:
            best = (value, clarity, knee, lo, hi, c, dark, clip, mean)

    if best is None:
        print("no candidate met the constraints")
        return 1

    _, clarity, knee, lo, hi, c, dark, clip, mean = best
    print(f"best candidate       contrast {c:+6.1f}  dark {dark:5.1f}%  clip {clip:5.1f}%  "
          f"mean {mean:6.1f}")
    print(f"  clarity={clarity} knee={knee} gain_lo={lo} gain_hi={hi}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
