"""Report what a burst of screen captures shows, in terms the viewer cares about.

The question is not "how many pixels changed" but "does the picture progress smoothly, and does the
preset change once per scene rather than flapping". So this prints, for each consecutive pair, how much
changed, and flags a pair that changed far more than its neighbours - which is what a mistaken
two-frame preset change looks like.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from find_video_rect import locate  # noqa: E402

REPO = Path(__file__).resolve().parent.parent


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python tools/report_burst.py seq_1.png seq_2.png ...")
        return 2

    rect = locate(argv[0])
    if rect is None:
        print("REPORT FAIL: video rectangle not found in the first capture")
        return 1
    x0, y0, x1, y1 = rect
    print(f"video area {x0},{y0}..{x1},{y1}")

    means: list[float] = []
    changes: list[int] = []
    previous = None
    for path in argv:
        rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
        sub = rgb[y0 + 8:y1 - 8, x0 + 8:x1 - 8]
        luma = (77 * sub[..., 0] + 150 * sub[..., 1] + 29 * sub[..., 2]) >> 8
        means.append(float(luma.mean()))
        changes.append(0 if previous is None else int((np.abs(luma - previous) > 12).sum()))
        previous = luma

    for index, (mean, changed) in enumerate(zip(means, changes), 1):
        marker = "" if index == 1 else ("  <- big jump" if changed > 60000 else "")
        print(f"  {index}: mean {mean:6.1f}  changed {changed:7d}{marker}")

    moving = sum(1 for value in changes[1:] if 1000 < value <= 60000)
    jumps = sum(1 for value in changes[1:] if value > 60000)
    print(f"\npairs that moved normally: {moving}")
    print(f"pairs that jumped (scene cut): {jumps}")
    if moving == 0 and jumps == 0:
        print("VERDICT: the picture is not changing - playback is not advancing")
        return 1
    print("VERDICT: the picture advances")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
