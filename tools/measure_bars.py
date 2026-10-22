#!/usr/bin/env python3
"""Locate the ruler's bars by column profile, which cannot alias on the tick period.

Why not cross-correlation here
    The ruler repeats a tick every 100 pixels, so a whole-pattern correlation is ambiguous modulo
    100: a shift of 90 scores almost as well as a shift of -10, and the tool reported 90 for what
    the bars show is about +45. Locating three individually identifiable bars removes the
    ambiguity, because their relative spacings (100 and 400) pin the phase unambiguously.

    python tools/measure_bars.py capture.png
"""

from __future__ import annotations

import sys

import numpy as np
from PIL import Image

BORDER = 4


def profiles(path: str):
    img = np.asarray(Image.open(path).convert("RGB"), dtype=np.int16)
    img = img[BORDER:img.shape[0] - BORDER, BORDER:img.shape[1] - BORDER]
    h, w, _ = img.shape
    band = img[int(h * 0.15):int(h * 0.85)]
    # Column profiles per channel, using the upper end so a bar stands out from black.
    return {
        "bright": band.mean(axis=(0, 2)),
        "ch0": band[:, :, 0].mean(axis=0),
        "ch1": band[:, :, 1].mean(axis=0),
        "ch2": band[:, :, 2].mean(axis=0),
    }, w


def peaks(profile: np.ndarray, threshold: float, min_gap: int = 20):
    hits = [x for x, v in enumerate(profile) if v > threshold]
    groups, current = [], []
    for x in hits:
        if current and x - current[-1] > min_gap:
            groups.append(current)
            current = []
        current.append(x)
    if current:
        groups.append(current)
    return [int(round(sum(g) / len(g) * (640.0 / len(profile)))) for g in groups]


def describe(path: str) -> dict:
    prof, w = profiles(path)
    scale = 640.0 / w
    result = {}
    result["white"] = peaks(prof["bright"], prof["bright"].max() * 0.7)
    result["ch0"] = peaks(prof["ch0"], max(prof["ch0"].max() * 0.6, 20))
    result["ch2"] = peaks(prof["ch2"], max(prof["ch2"].max() * 0.6, 20))
    return result


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2

    ref = describe("data/images/ruler_640x480.png")
    print("reference (data/images/ruler_640x480.png)")
    for key in ("white", "ch0", "ch2"):
        print(f"  {key}: {ref[key]}")
    print("  (bar design: white at 0, channel0 at 100, channel2 at 500)")

    for path in argv[1:]:
        cap = describe(path)
        print(f"\n{path.split(chr(92))[-1][:32]}")
        for key in ("white", "ch0", "ch2"):
            print(f"  {key}: {cap[key]}")

        deltas = []
        for key, expected in (("white", 0), ("ch0", 100), ("ch2", 500)):
            if cap[key]:
                deltas.append(cap[key][0] - expected)
        if deltas:
            mean = sum(deltas) / len(deltas)
            print(f"  bar offsets vs design: {deltas}")
            print(f"  mean offset: {mean:+.0f} px  (positive = picture sits too far right)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
