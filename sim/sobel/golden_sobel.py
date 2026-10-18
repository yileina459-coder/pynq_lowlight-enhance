#!/usr/bin/env python3
"""Golden reference and comparison tool for the streaming Sobel kernel.

The arithmetic and the border policy live in ``sim/common/image_ops.py`` so that
every operator in this project (Sobel, Gaussian, ...) shares one definition and
one comparison tool. This script is the Sobel-specific command line around it:

    python sim/sobel/golden_sobel.py --generate-test-image data/images/test_720p.png

    python sim/sobel/golden_sobel.py --input data/images/test_720p.png \
        --reference data/reference/sobel_720p.png \
        --preview data/reference/sobel_720p_preview.png --border wrap

    python sim/sobel/golden_sobel.py --compare board_out.png \
        --reference data/reference/sobel_720p.png --ignore-rows 2
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "common"))

from image_ops import luma, make_test_image, sobel, to_rgb  # noqa: E402,F401


def compare(got_path: str, ref_path: str, ignore_rows: int = 0) -> int:
    got = np.asarray(Image.open(got_path).convert("RGB"))
    ref = np.asarray(Image.open(ref_path).convert("RGB"))

    if got.shape != ref.shape:
        print(f"FAIL: shape mismatch got={got.shape} ref={ref.shape}")
        return 1

    if ignore_rows:
        got = got[ignore_rows:]
        ref = ref[ignore_rows:]

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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input")
    ap.add_argument("--reference")
    ap.add_argument("--preview")
    ap.add_argument("--border", default="replicate", choices=["replicate", "wrap"])
    ap.add_argument("--compare")
    ap.add_argument("--ignore-rows", type=int, default=0)
    ap.add_argument("--generate-test-image", metavar="PATH")
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
    edge = sobel(luma(rgb), border=args.border)

    if args.reference:
        Image.fromarray(to_rgb(edge)).save(args.reference)
        print(f"wrote reference: {args.reference}")

    if args.preview:
        Image.fromarray(np.hstack([rgb, to_rgb(edge)])).save(args.preview)
        print(f"wrote preview: {args.preview}")

    print(f"edge pixels (non-zero): {int(np.count_nonzero(edge))} / {edge.size}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
