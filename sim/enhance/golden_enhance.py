#!/usr/bin/env python3
"""Software golden model of the streaming enhancer (src/hls/enhance).

Two jobs, one file
    * golden reference: the same integer chain the HLS kernel implements, so a
      board capture can be compared with 0 tolerance (skill/golden_compare)
    * demo generator: turns a photo or a video frame into a before/after image
      *today*, hours before the bitstream exists - which is what a school-round
      submission actually needs

The chain (identical to enhance.cpp, stage for stage):
    luma -> 1-2-1 local mean -> local contrast boost -> two-segment tone curve
         -> binarise/invert -> per-channel colour shift -> optional split screen

Every value is an integer and every shift is a floor shift, which is what
ap_int's ">>" does. That is why hardware and this file agree bit for bit; there
is no rounding mode to disagree about.

Border policy comes from sim/common/image_ops.py, shared with the Sobel/Gaussian/
Sharpen models:
    horizontal: replicate at the left edge, window columns (c-2, c-1, c)
    vertical  : "replicate" for a still image (default here),
                "wrap" to model the line buffers of a continuous stream

Usage
    python sim\\enhance\\golden_enhance.py --input photo.jpg --preset reading --out out.png
    python sim\\enhance\\golden_enhance.py --input photo.jpg --montage demo.png
    python sim\\enhance\\golden_enhance.py --input photo.jpg --grid grid.png
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, "..", "common"))

from image_ops import _window, luma  # noqa: E402  (shared border policy)

# -----------------------------------------------------------------------------
# Presets: these are what the PS side writes into the kernel's 59 config bits.
# Keeping them here means the Python demo, the board demo and the report table
# all quote the same numbers.
# -----------------------------------------------------------------------------
PRESETS = {
    # clarity=16, knee=255, 16/16 is the exact identity transform
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    # local contrast only: makes text edges stand out, colour untouched
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    # reading: lift the shadows hard, keep highlights from blooming. The slopes
    # were tuned on a deliberately dim test page (luma ~27); a real photo will
    # need its own numbers, which is why they are just registers.
    "reading":  dict(clarity=24, knee=48,  gain_lo=88, gain_hi=14),
    # night: stronger shadow lift, softer highlights, more local contrast
    "night":    dict(clarity=30, knee=36,  gain_lo=120, gain_hi=10),
    # inverted monochrome: the mode that keeps text legible on a bright background
    "invert":   dict(clarity=24, knee=48,  gain_lo=88, gain_hi=14,
                     invert=True, mono=True),
    # binarised: strong shadow lift first, then a hard threshold. Without the
    # lift the entire dark page collapses to black and the preset "does nothing".
    "binarize": dict(clarity=16, knee=64,  gain_lo=112, gain_hi=8,
                     thresh=112, binarize=True, mono=True),
    # split screen: left half untouched, right half enhanced
    "split":    dict(clarity=28, knee=90,  gain_lo=40, gain_hi=12, split=True),
    # document: polarity-preserving shadow lift for a dim *page* (dark ink on
    # light paper that is simply under-lit). The "reading" preset does not do
    # this: with knee=48 the paper sits below the knee and is multiplied by
    # gain_lo/16 while the ink is compressed towards the knee, so the page comes
    # out as dark-on-light. Measured on the synthetic dim page: "reading" takes
    # the contrast from +41 to -51 (flipped), this one takes it to +158 with 0.2%
    # of pixels left below luma 32 (sim/enhance/tune_document_preset.py).
    # Tuned against a synthetic page, so re-tune against real footage.
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=12),
}


def local_mean(rgb: np.ndarray, border: str = "replicate") -> np.ndarray:
    """1-2-1 Gaussian mean of the luma plane over the same 3x3 window the kernel
    keeps in its line buffers. Sum is 0..4080, so >>4 lands in 0..255 exactly."""
    y = luma(rgb).astype(np.int32)
    t0, t1, t2, m0, m1, m2, b0, b1, b2 = _window(y, border)
    return ((t0 + 2 * t1 + t2
             + 2 * m0 + 4 * m1 + 2 * m2
             + b0 + 2 * b1 + b2) >> 4).astype(np.int32)


def enhance(rgb: np.ndarray,
            clarity: int = 16,
            knee: int = 255,
            gain_lo: int = 16,
            gain_hi: int = 16,
            thresh: int = 0,
            binarize: bool = False,
            invert: bool = False,
            mono: bool = False,
            split_x: int = 0,
            border: str = "replicate") -> np.ndarray:
    """Bit-exact software twin of enhance_stream()."""
    rgb16 = rgb.astype(np.int32)
    y = luma(rgb).astype(np.int32)
    m = local_mean(rgb, border)

    # stage 2: local contrast. (clarity * (y - m)) >> 4 with floor semantics.
    d = y - m
    y1 = np.clip(m + ((clarity * d) >> 4), 0, 255)

    # stage 3: two-segment tone curve
    below = y1 <= knee
    y2 = np.where(below,
                  (y1 * gain_lo) >> 4,
                  knee + (((y1 - knee) * gain_hi) >> 4))
    y2 = np.clip(y2, 0, 255)

    # stage 4: binarise / invert
    y3 = y2
    if binarize:
        y3 = np.where(y3 >= thresh, 255, 0)
    if invert:
        y3 = 255 - y3
    y3 = y3.astype(np.int32)

    # stage 5: colour. Shift all three channels by the same delta to keep chroma;
    # mono replaces the colour outright.
    delta = (y3 - y)[:, :, None]
    out = np.clip(rgb16 + delta, 0, 255)
    if mono:
        out = np.repeat(y3[:, :, None], 3, axis=2).astype(np.int32)

    # split screen: left of split_x untouched
    if split_x > 0:
        out = out.copy()
        out[:, :split_x, :] = rgb16[:, :split_x, :]

    return out.astype(np.uint8)


def render(rgb: np.ndarray, preset: str, border: str = "replicate") -> np.ndarray:
    """Apply a named preset to an RGB array."""
    if preset not in PRESETS:
        raise SystemExit(f"unknown preset {preset!r}, choose from {sorted(PRESETS)}")
    cfg = dict(PRESETS[preset])
    split = cfg.pop("split", False)
    if split:
        cfg["split_x"] = min(320, rgb.shape[1] // 2)
    return enhance(rgb, border=border, **cfg)


# -----------------------------------------------------------------------------
# Reporting helpers: the numbers that go into the design report
# -----------------------------------------------------------------------------
def stats(name: str, img: np.ndarray) -> dict:
    y = luma(img).astype(np.float64)
    return {
        "image": name,
        "luma_mean": round(float(y.mean()), 2),
        "luma_std": round(float(y.std()), 2),
        "pct_below_32": round(float((y < 32).mean() * 100), 2),
        "pct_above_224": round(float((y > 224).mean() * 100), 2),
    }


def montage(before: np.ndarray, after: np.ndarray, gap: int = 4) -> np.ndarray:
    """Side-by-side comparison with a thin divider, at 2x so the text stays
    legible when the image is embedded in a slide or a 5-minute video."""
    h, w = before.shape[:2]
    canvas = np.full((h, w * 2 + gap, 3), 255, dtype=np.uint8)
    canvas[:, :w] = before
    canvas[:, w + gap:] = after
    return canvas


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="source image (png/jpg)")
    ap.add_argument("--preset", default="reading", choices=sorted(PRESETS))
    ap.add_argument("--out", default="", help="write the enhanced image here")
    ap.add_argument("--montage", default="", help="write a before/after image here")
    ap.add_argument("--grid", default="", help="write one row per preset here")
    ap.add_argument("--border", default="replicate", choices=["replicate", "wrap"])
    ap.add_argument("--stats", action="store_true", help="print legibility statistics")
    args = ap.parse_args(argv)

    rgb = np.asarray(Image.open(args.input).convert("RGB"))
    print(f"input: {args.input}  {rgb.shape[1]}x{rgb.shape[0]}")

    out = render(rgb, args.preset, args.border)
    if args.out:
        Image.fromarray(out).save(args.out)
        print(f"wrote {args.out}  (preset={args.preset})")

    if args.montage:
        Image.fromarray(montage(rgb, out)).save(args.montage)
        print(f"wrote {args.montage}  (left = original, right = {args.preset})")

    if args.grid:
        rows = [montage(rgb, render(rgb, p, args.border)) for p in
                ["pass", "clarity", "reading", "night", "invert", "binarize"]]
        Image.fromarray(np.vstack(rows)).save(args.grid)
        print(f"wrote {args.grid}  (rows: {', '.join(['pass', 'clarity', 'reading', 'night', 'invert', 'binarize'])})")

    if args.stats:
        print()
        for name, img in (("original", rgb), (args.preset, out)):
            s = stats(name, img)
            print(f"  {s['image']:<10} luma mean {s['luma_mean']:>6.2f}  std {s['luma_std']:>6.2f}"
                  f"  <32: {s['pct_below_32']:>5.2f}%  >224: {s['pct_above_224']:>5.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
