"""Measure the offset with the whole frame visible in the OBS preview.

Why this version can be trusted
    Every earlier measurement assumed something about the preview: a cached rectangle, a scale derived from
    a guessed region, or that the preview showed the whole frame when it was zoomed into a corner. With the
    canvas now 640x480 and the source at scale 1.0, the preview contains the entire frame, so:

        1. take a desktop screenshot;
        2. the preview is the only bright region on an otherwise dark OBS background, so its bounding box
           is the picture;
        3. crop it, resample to 640x480 (uniform, because the whole frame is there), and report where the
           pattern's lines actually are.

    python tools/diag/measure_offset_final.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import show  # noqa: E402

WORK = REPO / ".tmp" / "final"
LINE_XS = (100.0, 500.0)

SHOT = (
    "Add-Type -AssemblyName System.Windows.Forms, System.Drawing\n"
    "$b = [System.Windows.Forms.SystemInformation]::VirtualScreen\n"
    "$bmp = New-Object System.Drawing.Bitmap $b.Width, $b.Height\n"
    "$g = [System.Drawing.Graphics]::FromImage($bmp)\n"
    "$g.CopyFromScreen($b.Left, $b.Top, 0, 0, $bmp.Size)\n"
    "$bmp.Save('OUTPATH', [System.Drawing.Imaging.ImageFormat]::Png)\n"
    "$g.Dispose()\n"
    "$bmp.Dispose()\n"
)


def screenshot(path: Path) -> None:
    script = SHOT.replace("OUTPATH", str(path))
    subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=120)


def make_pattern(path: Path) -> None:
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, 639, 7], fill=(255, 255, 255))
    draw.rectangle([0, 472, 639, 479], fill=(255, 255, 255))
    draw.rectangle([0, 0, 7, 479], fill=(255, 255, 255))
    draw.rectangle([632, 0, 639, 479], fill=(255, 255, 255))
    for x in LINE_XS:
        draw.rectangle([x - 4, 60, x + 3, 419], fill=(255, 255, 255))
    img.save(path)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    pattern = WORK / "pattern.png"
    make_pattern(pattern)

    if not show(pattern, "pass", no_tone=True):
        print("upload failed")
        return 1
    time.sleep(4)
    shot_path = WORK / "desktop.png"
    screenshot(shot_path)

    img = Image.open(shot_path).convert("RGB")
    arr = np.asarray(img).astype(int)
    # Locate the preview by finding the longest run of rows/columns that contain a lot of bright pixels.
    # A single global threshold box does not work here: OBS's own menu bar and panels are also bright, so
    # the bounding box swallowed the whole desktop. Runs over a high threshold isolate the picture.
    bright = arr.mean(axis=2) > 100

    def longest_run(flags: np.ndarray) -> tuple[int, int] | None:
        best = None
        start = None
        for index, flag in enumerate(flags):
            if flag and start is None:
                start = index
            elif not flag and start is not None:
                if best is None or index - start > best[1] - best[0]:
                    best = (start, index - 1)
                start = None
        if start is not None and (best is None or len(flags) - start > best[1] - best[0]):
            best = (start, len(flags) - 1)
        return best

    row_run = longest_run(bright.sum(axis=1) > 150)
    if row_run is None:
        print("could not find the preview")
        return 1
    y0, y1 = row_run
    col_run = longest_run(bright[y0:y1 + 1].sum(axis=0) > 60)
    if col_run is None:
        print("could not find the preview horizontally")
        return 1
    x0, x1 = col_run
    width, height = x1 - x0 + 1, y1 - y0 + 1
    print(f"preview picture region: x {x0}..{x1} ({width} px), y {y0}..{y1} ({height} px)")
    print(f"aspect {width / height:.3f} (expected 1.333)")

    crop = img.crop((x0, y0, x1 + 1, y1 + 1)).resize((640, 480), Image.LANCZOS)
    crop.save(WORK / "preview_640.png")
    grey = np.asarray(crop.convert("L")).astype(int)
    mask = grey > 150
    counts = mask.sum(axis=0)

    # Vertical lines: columns covered over a good part of the height, away from the border bands.
    inner = counts[20:-20]
    hits = np.where(inner > 480 * 0.5)[0] + 20
    if hits.size == 0:
        print("no vertical lines found")
        return 1
    runs: list[list[int]] = [[int(hits[0])]]
    for value in hits[1:]:
        if value - runs[-1][-1] <= 3:
            runs[-1].append(int(value))
        else:
            runs.append([int(value)])
    centres = [float(np.mean(run)) for run in runs]
    print(f"vertical lines at x: {[round(c, 1) for c in centres]}  (expected {LINE_XS})")

    if len(centres) >= 2:
        # Match the two innermost runs to the two expected lines by best spacing fit.
        best = None
        for i in range(len(centres) - 1):
            for j in range(i + 1, len(centres)):
                spacing = centres[j] - centres[i]
                error = abs(spacing - (LINE_XS[1] - LINE_XS[0]))
                if best is None or error < best[0]:
                    best = (error, centres[i], centres[j])
        _, left, right = best
        offsets = [left - LINE_XS[0], right - LINE_XS[1]]
        print(f"\noffset from the two lines: {offsets[0]:+.1f} and {offsets[1]:+.1f} source px")
        print(f"  mean {np.mean(offsets):+.1f}   agreement {abs(offsets[0] - offsets[1]):.1f}")
        mean = float(np.mean(offsets))
        print("verdict:", "no visible offset" if abs(mean) <= 3 else f"offset {mean:+.1f} px")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
