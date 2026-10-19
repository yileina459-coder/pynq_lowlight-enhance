#!/usr/bin/env python3
"""Generate a deliberately dim, text-like test page.

Why a synthetic page instead of a photo
    The enhancement presets were tuned for reading: dark background, small dark
    text, no colour. A photo would not exercise that. This page is deterministic
    (fixed seed), so the board test, the numpy golden model and the report figure
    all look at exactly the same input - which is what makes a zero-tolerance
    comparison meaningful.

    Average luma lands around 27, i.e. the "too dark to read comfortably" range
    the presets are meant to fix.

    python sim/enhance/make_dim_page.py            # 1280x720 -> data/images/test_dim_720p.png
    python sim/enhance/make_dim_page.py --width 1920 --height 1080 --out big.png
"""

from __future__ import annotations

import argparse
import os

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_OUT = os.path.join(REPO, "data", "images", "test_dim_720p.png")


def make_page(width: int = 1280, height: int = 720, seed: int = 20261019) -> np.ndarray:
    rng = np.random.default_rng(seed)

    bg = np.array([20, 22, 26], dtype=np.int32)      # luma ~22
    ink = np.array([58, 60, 64], dtype=np.int32)     # luma ~60, still very dim

    page = np.empty((height, width, 3), dtype=np.int32)
    page[:] = bg

    margin = width // 16
    line_h = max(6, height // 90)
    pitch = line_h * 3
    y = margin

    block = 0
    while y + line_h < height - margin:
        # occasional heading: brighter, shorter line
        heading = (block % 9 == 0)
        colour = (ink + 40) if heading else ink
        x = margin
        right = width - margin - (width // 3 if heading else 0)
        while x < right:
            word = int(rng.integers(width // 40, width // 12))
            word = min(word, right - x)
            if word > width // 60:
                page[y:y + line_h, x:x + word] = colour
            x += word + int(rng.integers(width // 90, width // 45))
        y += pitch
        block += 1

    noise = rng.integers(-2, 3, size=page.shape, dtype=np.int32)
    return np.clip(page + noise, 0, 255).astype(np.uint8)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--height", type=int, default=720)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    page = make_page(args.width, args.height)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    Image.fromarray(page).save(args.out)

    # uint8 arithmetic would wrap here (20*77 mod 256 is not 1540), so widen first.
    rgb = page.astype(np.int32)
    luma = (rgb[:, :, 0] * 77 + rgb[:, :, 1] * 150 + rgb[:, :, 2] * 29) >> 8
    print(f"wrote {args.out}  {args.width}x{args.height}")
    print(f"  luma mean {luma.mean():.1f}  min {luma.min()}  max {luma.max()}"
          f"  below 32: {(luma < 32).mean() * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
