#!/usr/bin/env python3
"""Locate the video rectangle on screen from OBS's selection border, tolerating occlusion.

Why not just diff two frames
    That worked once and then failed: the desktop behind the OBS window also changes, and any
    scrolling text turns into a "changed region". The selection border is a better landmark - OBS
    draws a bright red rectangle exactly around the source.

Why the right edge is derived rather than detected
    The editor window sits on top of the right part of the preview most of the time, so only the
    left edge and the top/bottom lines are visible. The frame is 640x480, so
        width = (bottom - top + 1) * 640/480
    reconstructs the right edge from what is visible.

    python tools/diag/find_video_rect.py shot.png [--print-only]
    -> prints "RECT=x0,y0,x1,y1" and writes .tmp/userpic/video_rect.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

def _repo_root() -> Path:
    """The repository root: walk up until the directory that holds .git.

    tools/ used to be flat, so Path(__file__).parent.parent was the root. Scripts now live at different
    depths (tools/, tools/diag/, tools/archive/), and hard-coding the depth is exactly what broke when
    they moved - so the layout is discovered instead.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / ".git").exists():
            return parent
    return here.parents[2] if len(here.parents) > 2 else here.parent


REPO = _repo_root()
sys.path.insert(0, str(REPO / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

RECT_FILE = REPO / ".tmp" / "userpic" / "video_rect.txt"
ASPECT = 640 / 480


def locate(path: str) -> tuple[int, int, int, int] | None:
    a = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    red = (r > 170) & (g < 90) & (b < 90)

    # Long horizontal spans are the top and bottom edges; the long vertical span is the left edge.
    rows = np.where(red.sum(axis=1) > 150)[0]
    cols = np.where(red.sum(axis=0) > 120)[0]
    if rows.size < 2 or cols.size < 1:
        return None

    y0, y1 = int(rows[0]), int(rows[-1])
    x0 = int(cols[0])
    height = y1 - y0 + 1
    width = int(round(height * ASPECT))
    return x0, y0, x0 + width - 1, y1


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    rect = locate(argv[0])
    if rect is None:
        print("LOCATE FAIL: no red selection border found (is OBS showing the source?)")
        return 1
    x0, y0, x1, y1 = rect
    print(f"RECT={x0},{y0},{x1},{y1}  ({x1 - x0 + 1}x{y1 - y0 + 1}, aspect "
          f"{(x1 - x0 + 1) / (y1 - y0 + 1):.3f})")
    RECT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RECT_FILE.write_text(f"{x0},{y0},{x1},{y1}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
