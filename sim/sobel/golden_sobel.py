#!/usr/bin/env python3
"""Golden reference and comparison tool for the streaming Sobel kernel.

The hardware kernel is defined in ``src/hls/sobel/sobel.hpp``. This script
reproduces exactly the same arithmetic in software so that a frame captured from
the board can be compared bit-for-bit:

    luma      Y   = (77*R + 150*G + 29*B) >> 8
    gradient  Gx  = (row r-2..r at col c) weighted [-1 0 +1; -2 0 +2; -1 0 +1]
              Gy  = bottom row - top row, same taps
    magnitude M   = |Gx| + |Gy|, saturated to 0..255
    output        = (M, M, M) replicated to R, G, B

Two border policies matter and they are *not* the same thing:

``--border replicate``  vertical neighbours clamped at the image edge. Correct
                        for a single still image.
``--border wrap``       vertical neighbours taken from the bottom of the frame.
                        This is what the kernel actually does on the third and
                        later frames of a continuous stream, because its line
                        buffers still hold the previous frame's last lines.

Horizontal policy is always replicate, matching the kernel's line-start reload.

Usage:
    python sim/sobel/golden_sobel.py --input data/images/test_720p.png \
        --reference data/reference/sobel_720p.png --preview data/reference/sobel_720p_preview.png

    python sim/sobel/golden_sobel.py --compare board/out/frame_sobel.png \
        --reference data/reference/sobel_720p.png --ignore-rows 2
"""

from __future__ import annotations

import argparse
import sys

import numpy as np
from PIL import Image


def luma(rgb: np.ndarray) -> np.ndarray:
    """BT.601-ish integer luma, identical to sobel_luma() in sobel.hpp."""
    r = rgb[:, :, 0].astype(np.uint32)
    g = rgb[:, :, 1].astype(np.uint32)
    b = rgb[:, :, 2].astype(np.uint32)
    return ((77 * r + 150 * g + 29 * b) >> 8).astype(np.uint8)


def sobel(y: np.ndarray, border: str = "replicate") -> np.ndarray:
    """3x3 Sobel, |Gx|+|Gy|, saturated. y is HxW uint8 luma."""
    h, w = y.shape
    y32 = y.astype(np.int32)

    if border == "wrap":
        rows = [np.mod(np.arange(h) + dy, h) for dy in (-2, -1, 0)]
    elif border == "replicate":
        rows = [np.clip(np.arange(h) + dy, 0, h - 1) for dy in (-2, -1, 0)]
    else:
        raise ValueError(f"unknown border policy: {border}")

    top, mid, bot = (y32[rows[0], :], y32[rows[1], :], y32[rows[2], :])

    # Horizontal replicate: window columns are (max(c-2,0), max(c-1,0), c).
    idx_c0 = np.clip(np.arange(w) - 2, 0, None)
    idx_c1 = np.clip(np.arange(w) - 1, 0, None)
    idx_c2 = np.arange(w)

    def col(row: np.ndarray, idx: np.ndarray) -> np.ndarray:
        return row[:, idx]

    t0, t1, t2 = col(top, idx_c0), col(top, idx_c1), col(top, idx_c2)
    m0, m1, m2 = col(mid, idx_c0), col(mid, idx_c1), col(mid, idx_c2)
    b0, b1, b2 = col(bot, idx_c0), col(bot, idx_c1), col(bot, idx_c2)

    gx = (t2 + 2 * m2 + b2) - (t0 + 2 * m0 + b0)
    gy = (b0 + 2 * b1 + b2) - (t0 + 2 * t1 + t2)
    mag = np.abs(gx) + np.abs(gy)
    return np.clip(mag, 0, 255).astype(np.uint8)


def to_rgb(m: np.ndarray) -> np.ndarray:
    """Replicate the magnitude to R, G, B, matching the kernel's output packing."""
    return np.dstack([m, m, m])


def make_test_image(width: int = 1280, height: int = 720) -> np.ndarray:
    """Deterministic edge-rich test pattern: ramps, a hard block, a fine checker,
    diagonal lines and a radial gradient-rings area."""
    yy, xx = np.mgrid[0:height, 0:width]

    r = (xx * 3 + yy) % 256
    g = (yy * 5) % 256
    b = (xx ^ yy) % 256
    img = np.dstack([r, g, b]).astype(np.uint8)

    # Hard-edged bright block: strong vertical and horizontal gradients.
    img[120:400, 200:640] = 235

    # Fine checkerboard: stresses the 3x3 window at Nyquist.
    checker = (((xx >> 2) + (yy >> 2)) & 1).astype(bool)
    region = np.zeros((height, width), dtype=bool)
    region[440:660, 700:1180] = True
    img[region & checker] = 20
    img[region & ~checker] = 220

    # Concentric rings: diagonal edges at many orientations.
    cx, cy = 320, 560
    dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
    rings = ((dist / 12.0).astype(np.int32) & 1).astype(np.uint8) * 200 + 30
    img[380:740, 80:560] = np.dstack([rings, rings, rings])[380:740, 80:560]

    return img


def compare(got_path: str, ref_path: str, ignore_rows: int = 0) -> int:
    got = np.asarray(Image.open(got_path).convert("RGB"))
    ref = np.asarray(Image.open(ref_path).convert("RGB"))

    if got.shape != ref.shape:
        print(f"FAIL: shape mismatch got={got.shape} ref={ref.shape}")
        return 1

    if ignore_rows:
        got = got[ignore_rows:, :, :]
        ref = ref[ignore_rows:, :, :]

    diff = np.abs(got.astype(np.int32) - ref.astype(np.int32))
    n_bad = int(np.count_nonzero(diff))
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    psnr = float("inf") if mse == 0 else 10.0 * np.log10(255.0 ** 2 / mse)

    print(f"pixels compared : {diff.shape[0] * diff.shape[1]}")
    print(f"channel mismatch: {n_bad}")
    print(f"max abs diff    : {int(diff.max())}")
    print(f"MSE             : {mse:.6f}")
    print(f"PSNR            : {psnr:.2f} dB")

    if n_bad == 0:
        print("COMPARE PASS (bit-exact)")
        return 0

    yy, xx, cc = np.nonzero(diff)
    for k in range(min(5, len(yy))):
        print(f"  first diffs: y={yy[k]} x={xx[k]} ch={cc[k]} "
              f"got={got[yy[k], xx[k], cc[k]]} ref={ref[yy[k], xx[k], cc[k]]}")
    print("COMPARE FAIL")
    return 1


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", help="input RGB image")
    ap.add_argument("--reference", help="reference PNG to write, or to compare against")
    ap.add_argument("--preview", help="optional side-by-side preview PNG")
    ap.add_argument("--border", default="replicate", choices=["replicate", "wrap"])
    ap.add_argument("--compare", help="frame captured from hardware, compare with --reference")
    ap.add_argument("--ignore-rows", type=int, default=0,
                    help="skip the first N rows when comparing (streaming warm-up)")
    ap.add_argument("--generate-test-image", metavar="PATH",
                    help="write the built-in 1280x720 test pattern and exit")
    args = ap.parse_args(argv)

    if args.generate_test_image:
        Image.fromarray(make_test_image()).save(args.generate_test_image)
        print(f"wrote test image: {args.generate_test_image}")
        return 0

    if args.compare:
        if not args.reference:
            print("--compare needs --reference", file=sys.stderr)
            return 2
        return compare(args.compare, args.reference, args.ignore_rows)

    if not args.input:
        print("either --input or --compare is required", file=sys.stderr)
        return 2

    rgb = np.asarray(Image.open(args.input).convert("RGB"))
    m = sobel(luma(rgb), border=args.border)

    if args.reference:
        Image.fromarray(to_rgb(m)).save(args.reference)
        print(f"wrote reference: {args.reference}")

    if args.preview:
        side = np.hstack([rgb, to_rgb(m)])
        Image.fromarray(side).save(args.preview)
        print(f"wrote preview: {args.preview}")

    print(f"edge pixels (non-zero): {int(np.count_nonzero(m))} / {m.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
