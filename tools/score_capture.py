#!/usr/bin/env python3
"""Score how legible a captured frame is, so tuning can be judged instead of guessed.

Why
    "Does it look clearer?" is the question the whole enhancement exists to answer, and eyeballing
    screenshots does not scale across presets and tone curves. This turns the capture into a few
    numbers that track what a low-vision reader needs:

      contrast   p95 - p5 of luma. Too small and text stops separating from the paper.
      clip       share of pixels at 0 or 255. High means detail was thrown away.
      edge       mean |Laplacian|, i.e. how sharp the strokes are. Blown highlights reduce it.
      midtone    share of pixels in 60..200. A good reading image lives mostly here.

    The first three are reported separately on purpose: a curve can raise contrast by clipping,
    which looks punchy in a mean and terrible to read.

    python tools/score_capture.py shot.png --crop x0,y0,x1,y1
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image


def luma(rgb: np.ndarray) -> np.ndarray:
    r = rgb[..., 0].astype(np.int32)
    g = rgb[..., 1].astype(np.int32)
    b = rgb[..., 2].astype(np.int32)
    return ((77 * r + 150 * g + 29 * b) >> 8)


def score(path: str, crop: tuple[int, int, int, int] | None) -> dict:
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    if crop:
        x0, y0, x1, y1 = crop
        rgb = rgb[y0:y1, x0:x1]
    y = luma(rgb)

    contrast = float(np.percentile(y, 95) - np.percentile(y, 5))
    clip = float(((y <= 2) | (y >= 253)).mean() * 100)
    midtone = float(((y >= 60) & (y <= 200)).mean() * 100)

    # Laplacian magnitude as a sharpness proxy.
    lap = (4 * y[1:-1, 1:-1] - y[:-2, 1:-1] - y[2:, 1:-1] - y[1:-1, :-2] - y[1:-1, 2:])
    edge = float(np.abs(lap).mean())

    return {
        "mean": float(y.mean()),
        "std": float(y.std()),
        "contrast": contrast,
        "clip": clip,
        "midtone": midtone,
        "edge": edge,
    }


def legibility(s: dict) -> float:
    """One number for ranking, tuned to "can I read this": contrast and edges, minus clipping."""
    return (s["contrast"] * 0.6
            + s["edge"] * 8.0
            + s["midtone"] * 0.8
            - max(0.0, s["clip"] - 5) * 3.0
            - abs(s["mean"] - 130) * 0.25)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("shots", nargs="+")
    ap.add_argument("--crop", help="x0,y0,x1,y1 in pixels")
    args = ap.parse_args(argv)

    crop = tuple(int(v) for v in args.crop.split(",")) if args.crop else None
    results = []
    for path in args.shots:
        s = score(path, crop)
        results.append((path, s))
        print(f"{path}")
        print(f"  mean {s['mean']:5.1f}  contrast {s['contrast']:5.1f}  "
              f"clip {s['clip']:4.1f}%  midtone {s['midtone']:4.1f}%  edge {s['edge']:5.2f}  "
              f"-> legibility {legibility(s):6.1f}")

    if len(results) > 1:
        best = max(results, key=lambda item: legibility(item[1]))
        print(f"\nBEST: {best[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
