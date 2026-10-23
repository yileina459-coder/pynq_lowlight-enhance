#!/usr/bin/env python3
"""Measure the residual offset of one capture against the ruler, trying both channel orders.

Why both orders
    The frame buffer PYNQ hands out is BGR while PNG files are RGB. The ruler's "red" bar is
    written into channel 0, which the panel shows as blue - and any reference PNG produced from
    that array is interpreted as RGB, so reference and capture end up with red and blue swapped.
    Cross-correlating a colour-shifted pair gives a nonsense shift (the earlier binarised capture
    scored 111 with a huge error for the same class of reason), so both orders are tried and the
    one with the lower error is reported.

    python tools/diag/measure_residual.py capture.png
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image

RULER = "data/images/ruler_640x480.png"
BORDER = 4


def load(path: str) -> np.ndarray:
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)


def best_shift(reference: np.ndarray, capture: np.ndarray, max_shift: int = 160):
    h, w, _ = capture.shape
    band = slice(int(h * 0.10), int(h * 0.90))
    ref_band, cap_band = reference[band], capture[band]
    best = (None, 1e18)
    for s in range(0, max_shift + 1):
        idx = (np.arange(w) + s) % w
        diff = np.abs(ref_band[:, idx, :] - cap_band).mean()
        if diff < best[1]:
            best = (s, diff)
    return best


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2

    reference = load(RULER)
    swapped = reference[:, :, ::-1]

    for path in argv:
        img = load(path)
        inner = img[BORDER:img.shape[0] - BORDER, BORDER:img.shape[1] - BORDER]
        h, w = reference.shape[:2]
        scaled = np.asarray(
            Image.fromarray(inner.astype(np.uint8)).resize((w, h), Image.BILINEAR),
            dtype=np.int16)

        s_a, e_a = best_shift(reference, scaled)
        s_b, e_b = best_shift(swapped, scaled)
        order = "as saved" if e_a <= e_b else "channels swapped"
        shift, error = (s_a, e_a) if e_a <= e_b else (s_b, e_b)

        print(f"{path.split(chr(92))[-1][:30]}")
        print(f"  as saved         shift {s_a:>4}  error {e_a:8.1f}")
        print(f"  channels swapped shift {s_b:>4}  error {e_b:8.1f}")
        print(f"  -> best: {order}, residual shift {shift}, error {error:.1f}")
        if error > 60:
            print("  warning: high error, the pattern may not be what the reference describes")
        elif shift <= 2:
            print("  -> compensated: the picture sits where it should")
        else:
            print(f"  -> still off by {shift} px; adjust --roll accordingly")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
