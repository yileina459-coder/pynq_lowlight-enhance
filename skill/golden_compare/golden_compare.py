#!/usr/bin/env python3
"""Bit-exact image comparison for hardware-vs-golden verification.

Why not just PSNR
    A "looks close enough" check hides exactly the bugs that matter in an image
    pipeline: a wrong luma coefficient, a border policy that differs by one pixel,
    a saturation that clamps a little too early. This tool defaults to
    ``tolerance = 0`` and reports the first differing pixels with coordinates, so
    the failure points at the bug instead of summarising it.

Typical use
    python golden_compare.py --got board_out.png --ref reference.png
    python golden_compare.py --got board_out.png --ref reference.png \
        --ignore-rows 2 --diff-out diff.png --json report.json

Exit code is 0 only when the images match within the requested tolerance, so it
can be dropped into a shell script or CI.
"""

from __future__ import annotations

import argparse
import json
import sys

import numpy as np
from PIL import Image


def load_rgb(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"))


def compare(got_path: str,
            ref_path: str,
            tolerance: int = 0,
            ignore_rows: int = 0,
            ignore_cols: int = 0,
            max_report: int = 5) -> dict:
    """Compare two RGB images.

    tolerance      max per-channel absolute difference still counted as a match
    ignore_rows    skip the first N rows (streaming warm-up, filters, ...)
    ignore_cols    skip the first N columns (same reason, horizontal)
    """
    got_full = load_rgb(got_path)
    ref_full = load_rgb(ref_path)

    if got_full.shape != ref_full.shape:
        return {
            "ok": False,
            "error": f"shape mismatch: got {got_full.shape}, ref {ref_full.shape}",
            "got_shape": list(got_full.shape),
            "ref_shape": list(ref_full.shape),
        }

    got = got_full[ignore_rows:, ignore_cols:]
    ref = ref_full[ignore_rows:, ignore_cols:]
    diff = np.abs(got.astype(np.int32) - ref.astype(np.int32))

    exceed = diff > tolerance
    n_bad = int(np.count_nonzero(exceed))
    total = int(diff.size)
    mse = float(np.mean(diff.astype(np.float64) ** 2))
    psnr = float("inf") if mse == 0 else 10.0 * np.log10(255.0 ** 2 / mse)

    first = []
    if n_bad:
        yy, xx, cc = np.nonzero(exceed)
        for k in range(min(max_report, len(yy))):
            y, x, c = int(yy[k]), int(xx[k]), int(cc[k])
            first.append({
                "y": y + ignore_rows,
                "x": x + ignore_cols,
                "channel": "RGB"[c],
                "got": int(got[y, x, c]),
                "ref": int(ref[y, x, c]),
            })

    return {
        "ok": n_bad == 0,
        "pixels_compared": int(got.shape[0] * got.shape[1]),
        "channels_compared": total,
        "mismatched_channels": n_bad,
        "mismatch_ratio": (n_bad / total) if total else 0.0,
        "max_abs_diff": int(diff.max()) if total else 0,
        "mse": mse,
        "psnr_db": psnr,
        "tolerance": tolerance,
        "ignore_rows": ignore_rows,
        "ignore_cols": ignore_cols,
        "first_diffs": first,
    }


def write_diff(got_path: str, ref_path: str, out_path: str,
               ignore_rows: int = 0, ignore_cols: int = 0) -> None:
    """Save an amplified absolute-difference image (white = identical)."""
    got = load_rgb(got_path)[ignore_rows:, ignore_cols:].astype(np.int32)
    ref = load_rgb(ref_path)[ignore_rows:, ignore_cols:].astype(np.int32)
    diff = np.abs(got - ref).astype(np.uint8)
    Image.fromarray(diff).save(out_path)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--got", required=True, help="image produced by hardware / DUT")
    ap.add_argument("--ref", required=True, help="golden reference image")
    ap.add_argument("--tolerance", type=int, default=0,
                    help="max per-channel abs diff still accepted (default 0)")
    ap.add_argument("--ignore-rows", type=int, default=0)
    ap.add_argument("--ignore-cols", type=int, default=0)
    ap.add_argument("--diff-out", help="write an amplified difference image here")
    ap.add_argument("--json", help="write the full report as JSON here")
    args = ap.parse_args(argv)

    report = compare(args.got, args.ref, args.tolerance,
                     args.ignore_rows, args.ignore_cols)

    if report.get("error"):
        print(f"FAIL: {report['error']}")
    else:
        print(f"pixels          : {report['pixels_compared']}")
        print(f"channels        : {report['channels_compared']}")
        print(f"mismatched      : {report['mismatched_channels']} "
              f"({report['mismatch_ratio'] * 100:.4f}%)")
        print(f"max abs diff    : {report['max_abs_diff']}")
        print(f"PSNR            : {report['psnr_db']:.2f} dB")
        for d in report["first_diffs"]:
            print(f"  diff at y={d['y']} x={d['x']} ch={d['channel']}: "
                  f"got={d['got']} ref={d['ref']}")
        print("COMPARE PASS" if report["ok"] else "COMPARE FAIL")

    if args.diff_out and not report.get("error"):
        write_diff(args.got, args.ref, args.diff_out, args.ignore_rows, args.ignore_cols)
        print(f"wrote diff image: {args.diff_out}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(report, fh, indent=2)
        print(f"wrote json report: {args.json}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
