"""Watch a full playback loop and find the frames that flare or change abruptly.

"After the video finishes there is a flash" could be three different things, and they look alike from
the sofa:

  * the loop point - the clip wraps from its last frame to its first, and if those two differ a lot the
    jump reads as a flash;
  * a stale buffer - one VDMA buffer still holding an older picture;
  * a static re-push - the resident drawing its still image over the video for a frame or two.

They can be told apart by the numbers: a loop point gives one bright/dark outlier per cycle at a fixed
position; a stale buffer repeats every fourth frame; a re-push shows the still image's mean.

    python tools/watch_loop.py --seconds 14
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seconds", type=float, default=14.0)
    ap.add_argument("--interval", type=float, default=0.15)
    args = ap.parse_args(argv)

    if not RECT_FILE.exists():
        print("FAIL: no calibrated rectangle")
        return 1
    x0, y0, x1, y1 = (int(v) for v in RECT_FILE.read_text().strip().split(","))

    outdir = REPO / ".tmp" / "loopwatch"
    outdir.mkdir(parents=True, exist_ok=True)
    for stale in outdir.glob("*.png"):
        stale.unlink()

    count = max(4, int(args.seconds / args.interval))
    means: list[float] = []
    stamps: list[float] = []
    start = time.monotonic()
    for index in range(count):
        path = outdir / f"f_{index:03d}.png"
        shot(path)
        rgb = np.asarray(Image.open(path).convert("RGB")).astype(np.int32)
        strip = rgb[y0 + 10:y1 - 10, x0 + 10:x0 + STRIP]
        luma = (77 * strip[..., 0] + 150 * strip[..., 1] + 29 * strip[..., 2]) >> 8
        means.append(float(luma.mean()))
        stamps.append(time.monotonic() - start)
        time.sleep(args.interval)

    arr = np.array(means)
    print(f"{count} samples over {stamps[-1]:.1f} s")
    print(f"mean level: min {arr.min():.1f}  median {np.median(arr):.1f}  max {arr.max():.1f}")
    print("\nper sample (relative time, level, change from previous):")
    for index, (t, value) in enumerate(zip(stamps, means)):
        delta = "" if index == 0 else f"  {value - means[index - 1]:+7.1f}"
        flag = ""
        if index > 0 and abs(value - means[index - 1]) > 25:
            flag = "  <- jump"
        print(f"  {t:5.2f}s  {value:6.1f}{delta}{flag}")

    jumps = [i for i in range(1, len(means)) if abs(means[i] - means[i - 1]) > 25]
    print(f"\njumps (>25 levels): {len(jumps)} at indices {jumps}")
    if not jumps:
        print("RESULT: no flare or jump in this window - the picture is steady")
        return 0
    gaps = [jumps[i] - jumps[i - 1] for i in range(1, len(jumps))]
    if gaps:
        print(f"spacing between jumps (samples): {gaps}")
        if all(3 <= g <= 5 for g in gaps):
            print("-> spacing of ~4 samples matches the VDMA's four buffers: a stale buffer is being"
                  " displayed")
        elif len(set(gaps)) == 1:
            print("-> evenly spaced: this is the clip's loop point, not a defect")
    else:
        print("-> a single jump: likely a one-off, e.g. the moment playback started or stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
