#!/usr/bin/env python3
"""Find the clarity value that actually maximises legibility, offline, before touching anything.

Why this is the right knob to optimise
    `clarity` scales the kernel's local-contrast term: y' = mean + clarity/16 * (y - mean). With a 3x3
    mean that is an unsharp mask, so raising clarity sharpens - and it is a *software* parameter in the
    configuration word, not a hardware change. Sharpening therefore needs no new bitstream, no
    re-timing, and no risk to a verified deliverable.

    What it costs is noise amplification and clipping, which is exactly what the legibility score
    penalises, so the sweep below is the honest way to pick it rather than "higher looks sharper".

    python tools/tune_clarity.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preview_enhance  # noqa: E402
from prepare_image import flatten_illumination, fit, load, normalize_page  # noqa: E402
from score_capture import legibility, score_array  # noqa: E402

CASES = [
    # (name, image, tone, what a viewer wants here)
    ("dark page (page tone)", "data/images/test_dim_720p.png", "page", "text readable, paper not blown"),
    ("normal photo (page tone)", "data/images/test_720p.png", "page", "detail visible, not washed"),
    ("test card (page tone)", "data/images/testcard_640x480.png", "page", "all features preserved"),
]

CLARITY = [16, 20, 24, 28, 32, 36, 40, 44, 48, 56]


def tone(name: str, frame: Image.Image) -> Image.Image:
    if name == "page":
        return Image.fromarray(normalize_page(flatten_illumination(np.asarray(frame))))
    return frame


def local_contrast(rgb: np.ndarray) -> float:
    """p90 of the 5x5 local standard deviation - detail, not overall brightness."""
    luma = (77 * rgb[..., 0].astype(float) + 150 * rgb[..., 1] + 29 * rgb[..., 2]) / 256.0
    from numpy.lib.stride_tricks import sliding_window_view
    windows = sliding_window_view(luma, (5, 5))
    return float(np.percentile(windows.std(axis=(-1, -2)), 90))


def main() -> int:
    for label, path, tone_name, want in CASES:
        frame = fit(load(path), "letterbox", 0)
        prepared = np.asarray(tone(tone_name, frame))

        rows = []
        for clarity in CLARITY:
            out = preview_enhance.enhance(prepared, {"clarity": clarity, "knee": 255,
                                                     "gain_lo": 16, "gain_hi": 16})
            s = score_array(out)
            rows.append((clarity, legibility(s), s, local_contrast(out)))

        print(f"\n=== {label} ===")
        print(f"    期望: {want}")
        print(f"{'clarity':>8s} {'x':>5s} {'score':>8s} {'mean':>6s} {'contrast':>9s} "
              f"{'edge':>6s} {'clip%':>6s} {'local p90':>10s}")
        for clarity, value, s, lc in rows:
            print(f"{clarity:8d} {clarity / 16:5.2f} {value:8.1f} {s['mean']:6.1f} {s['contrast']:9.1f} "
                  f"{s['edge']:6.2f} {s['clip']:6.1f} {lc:10.1f}")

        best = max(rows, key=lambda row: row[1])
        current = next(row for row in rows if row[0] == 28)
        print(f"  当前 clarity=28 得分 {current[1]:.1f}；最佳 clarity={best[0]} 得分 {best[1]:.1f} "
              f"(+{best[1] - current[1]:.1f})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
