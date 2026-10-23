"""Three uploads, three captures, in one run - white, a line pattern, black.

The point of doing it in one run
    Separately measured steps kept disagreeing: a white/black pair proved the capture was live, while a
    pattern uploaded minutes later appeared not to arrive. Uploads, captures and analysis in a single run
    remove everything that can change in between.

    For each capture it reports the mean and the count of bright pixels, and for the pattern capture the
    columns where bright vertical lines are found - so the answer is "the lines are at x=..., x=..." rather
    than a verdict.

    python tools/diag/triple_probe.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import show, shot  # noqa: E402

WORK = REPO / ".tmp" / "triple"


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)

    white = WORK / "white.png"
    black = WORK / "black.png"
    pattern = WORK / "pattern.png"
    Image.new("RGB", (640, 480), (255, 255, 255)).save(white)
    Image.new("RGB", (640, 480), (0, 0, 0)).save(black)
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for x in (100, 500):
        draw.rectangle([x - 2, 0, x + 1, 479], fill=(255, 255, 255))
    draw.rectangle([0, 238, 639, 241], fill=(255, 255, 255))
    img.save(pattern)

    results = {}
    for name, path in (("white", white), ("pattern", pattern), ("black", black)):
        if not show(path, "pass", no_tone=True):
            print(f"{name}: upload failed")
            return 1
        time.sleep(4)
        out = WORK / f"{name}.png"
        shot(out)
        arr = np.asarray(Image.open(out).convert("L")).astype(int)
        results[name] = arr
        print(f"{name:8s} capture mean {arr.mean():6.1f}  bright(>200) {int((arr > 200).sum()):7d}  "
              f"dark(<20) {int((arr < 20).sum()):7d}")

    # Where are the bright columns in the pattern capture, relative to the white capture's extent?
    white_mask = results["white"] > 200
    rows = np.where(white_mask.sum(axis=1) > 100)[0]
    cols = np.where(white_mask.sum(axis=0) > 80)[0]
    if rows.size < 2 or cols.size < 2:
        print("\nno video rectangle found in the white capture")
        return 1
    x0, y0, x1, y1 = cols[0], rows[0], cols[-1], rows[-1]
    print(f"\nrect from the white capture: {x0},{y0}..{x1},{y1}  {x1 - x0 + 1}x{y1 - y0 + 1}")

    sub = results["pattern"][y0:y1 + 1, x0:x1 + 1]
    mask = sub > 150
    counts = mask.sum(axis=0)
    hits = np.where(counts > mask.shape[0] * 0.5)[0]
    width = x1 - x0 + 1
    scale = width / 640.0
    if hits.size:
        runs: list[list[int]] = [[int(hits[0])]]
        for value in hits[1:]:
            if value - runs[-1][-1] <= 2:
                runs[-1].append(int(value))
            else:
                runs.append([int(value)])
        centres = [float(np.mean(run)) for run in runs]
        print(f"vertical lines in the pattern capture (source px): "
              f"{[round(c / scale, 1) for c in centres]}")
        print(f"expected: 100.0 and 500.0")
    else:
        print("no vertical lines found in the pattern capture")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
