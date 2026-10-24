"""Measure the horizontal wrap precisely and verify the compensation.

Why this pattern
    Earlier attempts mixed white, black and grey into the pattern. OBS's own background is dark grey and its
    chrome has white, so the picture's edges could not be told apart from the interface, and the estimates
    that came out were inconsistent.

    This pattern uses eight saturated colours only, so (a) its extent is exactly the set of saturated pixels
    and (b) every band is identifiable without ambiguity. Eight bands of 80 px each span the full 640 width.

How the wrap is derived
    Let the leftmost visible band be B with measured width w and full-band width f (both in capture pixels).
    The picture starts (f - w) capture pixels into band B, which is (f - w) * 640/f source pixels. So

        W = band_start(B) + (80 - w * 80/f)

    with band_start from the known colour order. No rectangle, no scale assumption, and the same arithmetic
    for every band, so a wrong classification shows up as an inconsistent W rather than a confident guess.

    python tools/diag/verify_offset.py [--set]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import ASKPASS, SHOW, shot  # noqa: E402

WORK = REPO / ".tmp" / "verify"
BOARD = "xilinx@192.168.2.99"

# Eight saturated colours, in a fixed order, 80 px each.
COLOURS = [
    ("RED", (255, 0, 0)),
    ("GREEN", (0, 210, 0)),
    ("BLUE", (0, 60, 255)),
    ("YELLOW", (250, 250, 0)),
    ("CYAN", (0, 230, 230)),
    ("MAGENTA", (235, 0, 235)),
    ("ORANGE", (255, 130, 0)),
    ("PURPLE", (120, 0, 200)),
]


def board(command: str) -> str:
    import os
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                             "-o", "ConnectTimeout=10", BOARD, command],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=90)
    return (result.stdout or "").strip()


def show(path: Path) -> bool:
    import os
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                             str(SHOW), "-Image", str(path), "-Preset", "pass"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=300)
    return result.returncode == 0


def make_pattern(path: Path) -> None:
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for index, (_, colour) in enumerate(COLOURS):
        x0 = index * 80
        draw.rectangle([x0, 0, x0 + 79, 479], fill=colour)
    img.save(path)


def hue_of(pixel: np.ndarray) -> float:
    """Hue in degrees (0-360)."""
    r, g, b = float(pixel[0]), float(pixel[1]), float(pixel[2])
    high, low = max(r, g, b), min(r, g, b)
    if high == low:
        return -1.0
    delta = high - low
    if high == r:
        hue = (60 * ((g - b) / delta)) % 360
    elif high == g:
        hue = 60 * ((b - r) / delta) + 120
    else:
        hue = 60 * ((r - g) / delta) + 240
    return hue % 360


def classify(row: np.ndarray) -> list[str]:
    """Name each column's colour by hue, or 'OTHER' when it is not one of the eight bands.

    Hue rather than RGB distance: the upload path applies a tone curve, which shifts brightness but leaves
    hue alone, so hue identifies the band while exact values no longer match.
    """
    refs = [(name, hue_of(np.array(colour, dtype=float))) for name, colour in COLOURS]
    labels = []
    for x in range(row.shape[0]):
        pixel = row[x]
        if (int(pixel.max()) - int(pixel.min())) < 70:
            labels.append("OTHER")
            continue
        hue = hue_of(pixel)
        best_name, best_delta = "OTHER", 1e9
        for name, reference in refs:
            delta = min(abs(hue - reference), 360 - abs(hue - reference))
            if delta < best_delta:
                best_name, best_delta = name, delta
        labels.append(best_name if best_delta < 25 else "OTHER")
    return labels


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--set", action="store_true", help="write the measured compensation to the board")
    args = ap.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    pattern = WORK / "eight.png"
    make_pattern(pattern)

    if not show(pattern):
        print("upload failed")
        return 1
    time.sleep(4)
    shot(WORK / "shot.png")

    img = np.asarray(Image.open(WORK / "shot.png").convert("RGB")).astype(int)
    saturation = img.max(axis=2) - img.min(axis=2)
    saturated = saturation > 70
    rows = np.where(saturated.sum(axis=1) > 200)[0]
    if rows.size < 10:
        print(f"picture not found (saturated rows: {rows.size})")
        return 1
    y_mid = (int(rows[0]) + int(rows[-1])) // 2
    band = img[y_mid - 10:y_mid + 10].mean(axis=0)

    labels = classify(band)
    runs: list[tuple[str, int, int]] = []
    current = labels[0]
    start = 0
    for x in range(1, len(labels)):
        if labels[x] != current:
            runs.append((current, start, x - 1))
            current = labels[x]
            start = x
    runs.append((current, start, len(labels) - 1))

    picture = [run for run in runs if run[0] != "OTHER" and run[2] - run[1] >= 10]
    if len(picture) < 3:
        print("not enough colour bands found in the capture")
        for name, s, e in runs:
            print(f"   {name:8s} {s}..{e}")
        return 1

    widths = [e - s + 1 for _, s, e in picture]
    # Full bands are those not touching the picture's ends.
    inner = widths[1:-1] if len(widths) > 2 else widths
    full = float(np.median(inner))
    scale = full / 80.0            # capture pixels per source pixel

    print(f"video picture spans capture x {picture[0][1]}..{picture[-1][2]}")
    print(f"full band width {full:.1f} capture px  ->  scale {scale:.4f}")
    print("bands left to right:")
    for (name, s, e) in picture:
        print(f"   {name:8s} capture x {s:4d}..{e:4d}   width {e - s + 1:4d}")

    first_name, first_start, first_end = picture[0]
    order = [name for name, _ in COLOURS]
    band_index = order.index(first_name)
    cut = (full - (first_end - first_start + 1)) / scale
    wrap = (band_index * 80 + cut) % 640
    print(f"\nfirst visible band {first_name} (starts at source x {band_index * 80}); "
          f"it is cut by {cut:.1f} source px")
    print(f"measured wrap W = {wrap:.1f} source px")

    if wrap < 3 or wrap > 637:
        print("RESULT: aligned - the picture starts at source x 0")
        return 0

    needed = (640 - round(wrap)) % 640
    print(f"needed compensation roll = {needed}")
    if args.set:
        board(f"echo {needed} > /tmp/hdmi_roll.txt")
        print(f"wrote /tmp/hdmi_roll.txt = {needed}; run this again to confirm the residual is zero")
    else:
        print("pass --set to apply it")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
