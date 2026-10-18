#!/usr/bin/env python3
"""Golden reference and comparison tool for the streaming Gaussian blur kernel.

Shares its arithmetic and border policy with every other operator in
``sim/common/image_ops.py``, so a board capture can be compared with a
0-tolerance check.

    python sim/gaussian/golden_gaussian.py --input data/images/test_720p.png \
        --reference data/reference/gaussian_720p.png --border wrap

    python sim/gaussian/golden_gaussian.py --compare board_out.png \
        --reference data/reference/gaussian_720p.png --ignore-rows 2
"""

from __future__ import annotations

import argparse
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "common"))

from image_ops import gaussian, make_test_image  # noqa: E402


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
    print(f"pixels compared : {diff.shape[0] * diff.shape[1]}")
    print(f"channel mismatch: {n_bad}")
    print(f"max abs diff    : {int(diff.max())}")

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
    args = ap.parse_args(argv)

    if args.compare:
        if not args.reference:
            print("--compare needs --reference", file=sys.stderr)
            return 2
        return compare(args.compare, args.reference, args.ignore_rows)

    if not args.input:
        print("either --input or --compare is required", file=sys.stderr)
        return 2

    rgb = np.asarray(Image.open(args.input).convert("RGB"))
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        print(f"FAIL: expected an RGB image, got shape {rgb.shape}")
        return 2

    blur = gaussian(rgb, border=args.border)

    if args.reference:
        Image.fromarray(blur).save(args.reference)
        print(f"wrote reference: {args.reference}")

    if args.preview:
        Image.fromarray(np.hstack([rgb, blur])).save(args.preview)
        print(f"wrote preview: {args.preview}")

    # A blur must reduce local variance; if it does not, something is wrong with
    # the model (wrong normalisation, wrong tap order, ...).
    var_in = float(np.var(rgb.astype(np.float64)))
    var_out = float(np.var(blur.astype(np.float64)))
    print(f"variance: input {var_in:.2f} -> output {var_out:.2f}")
    if var_out >= var_in:
        print("FAIL: blur did not reduce variance")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
