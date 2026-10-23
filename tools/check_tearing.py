"""Detect display tearing while a per-frame alternating clip plays.

Method
    The clip alternates bright and dark on every frame, so a frame that reached the display intact is
    uniformly bright or uniformly dark. If the VDMA reads a buffer that the PS is still writing, one
    displayed frame contains both - a horizontal seam with bright rows above dark rows (or the reverse).

Why only the left strip
    The OBS preview is partly covered by other windows on this desktop, so measuring the whole video
    rectangle counts the covering window as "dark content" and reports tearing that is not on the
    board. The leftmost ~150 px of the video are never covered, which is enough: a horizontal seam is
    just as visible in a narrow column.

    python tools/check_tearing.py [count]
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parent.parent
RECT_FILE = REPO / ".tmp" / "video_rect.txt"
STRIP = 150

SHOT_PS = r'''
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
$b = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)
$bmp.Save(PATH, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
'''


def shot(path: Path) -> None:
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    SHOT_PS.replace("PATH", f"'{path}'")], capture_output=True, timeout=60)


def rect() -> tuple[int, int, int, int]:
    text = RECT_FILE.read_text().strip()
    x0, y0, x1, y1 = (int(v) for v in text.split(","))
    return x0, y0, x1, y1


def main(argv: list[str]) -> int:
    count = int(argv[0]) if argv else 12
    if not RECT_FILE.exists():
        print("FAIL: no calibrated rectangle in .tmp/video_rect.txt")
        return 1
    x0, y0, x1, y1 = rect()
    print(f"video area {x0},{y0}..{x1},{y1}; measuring the left {STRIP} px")

    outdir = REPO / ".tmp" / "tear"
    outdir.mkdir(parents=True, exist_ok=True)

    uniform = torn = blank = 0
    for index in range(count):
        path = outdir / f"shot_{index:02d}.png"
        shot(path)
        rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
        strip = rgb[y0 + 10:y1 - 10, x0 + 10:x0 + STRIP]
        luma = (77 * strip[..., 0] + 150 * strip[..., 1] + 29 * strip[..., 2]) >> 8

        rows_bright = ((luma > 128).mean(axis=1) > 0.5)
        fraction = float(rows_bright.mean())
        if fraction > 0.9:
            verdict, kind = "uniform bright", "uniform"
        elif fraction < 0.1:
            verdict, kind = "uniform dark", "uniform"
        elif 0.25 < fraction < 0.75:
            verdict, kind = f"TORN ({fraction * 100:.0f}% of rows bright)", "torn"
        else:
            # Mostly one shade with a narrow seam: still a tear if the minority band is not tiny.
            verdict, kind = f"partial seam ({fraction * 100:.0f}% of rows bright)", "torn"

        if kind == "torn":
            torn += 1
        elif fraction > 0.9 or fraction < 0.1:
            uniform += 1
        else:
            blank += 1
        print(f"  {path.name}: {verdict}")
        time.sleep(0.12)

    print(f"\nintact frames: {uniform}   torn: {torn}   unclear: {blank}   (of {count})")
    if torn == 0 and uniform > 0:
        print("RESULT: no tearing - every displayed frame came from a single source frame")
        return 0
    if uniform == 0:
        print("RESULT: nothing recognisable - is the clip actually playing?")
        return 2
    print("RESULT: tearing present - the display shows two frames at once")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
