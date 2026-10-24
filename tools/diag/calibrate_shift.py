"""Calibrate the board's horizontal wrap compensation, robustly.

Why the pattern is a staircase of unequal bars
    Two earlier attempts used a single thin line and produced correlations of 0.3-0.6 with inconsistent
    answers. The flaw was in the method: the shift is estimated by correlating column profiles, and a field
    with one thin feature has an almost flat profile, so the correlation has no sharp peak and noise wins.

    Unequal bar widths and stepped brightness give a profile that is unique along x, so one peak dominates.
    Equal widths would alias at their own period - the failure a regular bar pattern invites.

Method
    1. upload the staircase, capture the OBS window, locate the picture (its brightest large rectangle);
    2. crop, resample to 640x480, and find the circular shift whose rotation of the source profile best
       matches the capture's - that shift is the wrap;
    3. with --apply, write it to /tmp/hdmi_roll.txt, re-upload, re-measure, and report the residual, so a
       correct compensation is demonstrated rather than assumed.

    python tools/diag/calibrate_shift.py [--apply]
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

WORK = REPO / ".tmp" / "shift"
BOARD = "xilinx@192.168.2.99"

BARS = [(0, 30, 40), (30, 50, 90), (80, 80, 150), (160, 40, 210), (200, 100, 60),
        (300, 60, 130), (360, 90, 190), (450, 70, 30), (520, 120, 250)]


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
                             str(SHOW), "-Image", str(path), "-Preset", "pass", "-NoTone"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=300)
    return result.returncode == 0


def make_pattern(path: Path) -> np.ndarray:
    img = Image.new("RGB", (640, 480), (245, 245, 245))
    draw = ImageDraw.Draw(img)
    for x, width, level in BARS:
        draw.rectangle([x, 0, x + width - 1, 479], fill=(level, level, level))
    img.save(path)
    return np.asarray(img.convert("L")).astype(float)


def find_picture(img: np.ndarray) -> tuple[int, int, int, int]:
    bright = img > 100

    def longest_run(flags: np.ndarray, minimum: int) -> tuple[int, int] | None:
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
        if best and best[1] - best[0] >= minimum:
            return best
        return None

    rows = longest_run(bright.sum(axis=1) > 300, 100)
    if rows is None:
        raise SystemExit("preview not found vertically (is the board showing the staircase?)")
    y0, y1 = rows
    cols = longest_run(bright[y0:y1 + 1].sum(axis=0) > 60, 100)
    if cols is None:
        raise SystemExit("preview not found horizontally")
    return cols[0], y0, cols[1], y1


def estimate(capture: np.ndarray, source: np.ndarray) -> tuple[int, float, float]:
    cap = capture.mean(axis=0)
    src = source.mean(axis=0)
    cap = cap - cap.mean()
    src = src - src.mean()
    scores = np.array([
        float(np.dot(np.roll(src, shift), cap) /
              (np.linalg.norm(np.roll(src, shift)) * np.linalg.norm(cap) + 1e-9))
        for shift in range(640)
    ])
    best_shift = int(np.argmax(scores))
    best = float(scores[best_shift])
    mask = np.abs(np.arange(640) - best_shift) > 20
    runner_up = float(scores[mask].max())
    return best_shift, best, best - runner_up


def measure(source: np.ndarray) -> tuple[int, float, float]:
    time.sleep(4)
    shot(WORK / "shot.png")
    img = np.asarray(Image.open(WORK / "shot.png").convert("L")).astype(float)
    x0, y0, x1, y1 = find_picture(img)
    crop = Image.fromarray(img[y0:y1 + 1, x0:x1 + 1].astype(np.uint8)).resize((640, 480), Image.LANCZOS)
    return estimate(np.asarray(crop).astype(float), source)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="write the measured value to the board")
    args = ap.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    pattern = WORK / "staircase.png"
    source = make_pattern(pattern)

    if not show(pattern):
        print("upload failed")
        return 1
    shift, score, margin = measure(source)
    print(f"measured shift {shift} px   correlation {score:.3f}   margin {margin:.3f}")
    if margin < 0.05:
        print("WARNING: weak peak - the capture probably is not the pattern")
    if not args.apply:
        print("dry run; pass --apply to write it to the board")
        return 0

    board(f"echo {shift} > /tmp/hdmi_roll.txt")
    print(f"wrote /tmp/hdmi_roll.txt = {shift}")
    if not show(pattern):
        return 1
    residual, score2, margin2 = measure(source)
    print(f"residual {residual} px   correlation {score2:.3f}   margin {margin2:.3f}")
    if residual == 0:
        print("RESULT: aligned")
    elif residual > 320:
        print(f"RESULT: aligned (residual {residual} reads as {(residual - 640)} px)")
    else:
        print(f"RESULT: still off by {residual} px; try roll = {(shift + residual) % 640}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
