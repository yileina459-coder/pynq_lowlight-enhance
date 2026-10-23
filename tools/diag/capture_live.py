"""Is the capture path live? Upload two very different pictures and compare the captures.

Why this check exists
    Several measurements tonight were nonsense because the capture was frozen on an old frame while the
    board was fine - the resident log proved every upload had been applied. A stale capture also looks
    exactly like "the board ignores uploads", so the first step of any visual verification must be to
    prove the capture moves.

    python tools/diag/capture_live.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import show, shot  # noqa: E402

WORK = REPO / ".tmp" / "live"


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    bright = WORK / "live_bright.png"
    dark = WORK / "live_dark.png"
    Image.new("RGB", (640, 480), (235, 235, 235)).save(bright)
    Image.new("RGB", (640, 480), (20, 20, 20)).save(dark)

    if not show(bright, "pass", no_tone=True):
        print("upload of the bright frame failed")
        return 1
    time.sleep(4)
    shot(WORK / "live_a.png")
    if not show(dark, "pass", no_tone=True):
        print("upload of the dark frame failed")
        return 1
    time.sleep(4)
    shot(WORK / "live_b.png")

    a = np.asarray(Image.open(WORK / "live_a.png").convert("L")).astype(int)
    b = np.asarray(Image.open(WORK / "live_b.png").convert("L")).astype(int)
    if a.shape != b.shape:
        print(f"captures differ in size: {a.shape} vs {b.shape}")
        return 1
    changed = int((np.abs(a - b) > 60).sum())
    total = a.size
    print(f"bright capture mean {a.mean():6.1f}")
    print(f"dark   capture mean {b.mean():6.1f}")
    print(f"pixels that changed: {changed} of {total} ({100 * changed / total:.1f}%)")
    live = changed > total * 0.02
    print("capture is LIVE" if live else "capture is FROZEN - OBS is not showing the board")
    return 0 if live else 2


if __name__ == "__main__":
    raise SystemExit(main())
