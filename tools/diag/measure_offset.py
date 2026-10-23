"""Measure the picture's horizontal offset end to end, in one run.

Everything that can go stale is measured fresh here:
    1. the video rectangle, from a white frame and a black frame - those are the only pixels that change
       when only the board's output changes;
    2. the ruler image, whose real layout is a red bar at x=100..107, a blue bar at x=500..507 and a white
       bar at x=0..7 (checked against the file, not against a docstring);
    3. the bar positions in the capture, converted to source pixels with the rectangle's own scale, so
       nothing is resampled.

    Two earlier attempts produced confident nonsense by trusting something stale or wrong: a rectangle
    cached from a previous window position, and a docstring that swapped the bar colours. Both are
    avoided by calibrating every run and by verifying the ruler's layout from the image itself.

    python tools/diag/measure_offset.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "diag"))
from compare_presets import ASKPASS, SHOW, shot  # noqa: E402

WORK = REPO / ".tmp" / "cmp"
BOARD = "xilinx@192.168.2.99"


def board(command: str) -> str:
    import os
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                             "-o", "ConnectTimeout=10", BOARD, command],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=60)
    return (result.stdout or "").strip()


def show(image: Path) -> bool:
    import os
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                             str(SHOW), "-Image", str(image), "-Preset", "pass", "-NoTone"],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=300)
    if result.returncode != 0:
        tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
        print(f"    upload failed: {tail[-1] if tail else 'no output'}")
    return result.returncode == 0


def ruler_layout(path: Path) -> tuple[float, float, float]:
    """Centre columns of the ruler's red, blue and white bars - read from the image itself."""
    img = np.asarray(Image.open(path).convert("RGB")).astype(int)
    red = (img[..., 0] > 140) & (img[..., 1] < 100) & (img[..., 2] < 100)
    blue = (img[..., 2] > 140) & (img[..., 0] < 100) & (img[..., 1] < 100)
    white = img.min(axis=2) > 190

    def centre(mask: np.ndarray, fraction: float) -> float:
        columns = np.where(mask.sum(axis=0) > mask.shape[0] * fraction)[0]
        if columns.size == 0:
            raise SystemExit("ruler: expected bar not found in the source image")
        return float(columns.mean())

    return centre(red, 0.25), centre(blue, 0.25), centre(white, 0.5)


def main() -> int:
    WORK.mkdir(parents=True, exist_ok=True)
    ruler = REPO / "data" / "images" / "ruler_640x480.png"
    red_x, blue_x, white_x = ruler_layout(ruler)
    print(f"ruler layout read from the file: red {red_x:.1f}, blue {blue_x:.1f}, white {white_x:.1f}")

    playing = board("cat /tmp/hdmi_play.txt 2>/dev/null")
    if playing:
        board(": > /tmp/hdmi_play.txt")
        time.sleep(2.5)
        print("playback paused for the measurement")

    white = WORK / "m_white.png"
    black = WORK / "m_black.png"
    Image.new("RGB", (640, 480), (255, 255, 255)).save(white)
    Image.new("RGB", (640, 480), (0, 0, 0)).save(black)

    if not show(white):
        return 1
    time.sleep(4)
    shot(WORK / "m_a.png")
    if not show(black):
        return 1
    time.sleep(4)
    shot(WORK / "m_b.png")
    a = np.asarray(Image.open(WORK / "m_a.png").convert("L")).astype(int)
    b = np.asarray(Image.open(WORK / "m_b.png").convert("L")).astype(int)
    diff = np.abs(a - b) > 60
    rows = np.where(diff.sum(axis=1) > 100)[0]
    cols = np.where(diff.sum(axis=0) > 80)[0]
    if rows.size < 2 or cols.size < 2:
        raise SystemExit("no video rectangle found: is OBS previewing the board?")
    x0, y0, x1, y1 = int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1])
    width, height = x1 - x0 + 1, y1 - y0 + 1
    print(f"video rectangle {x0},{y0}..{x1},{y1}  {width}x{height}  aspect {width / height:.3f}")
    if abs(width / height - 4 / 3) > 0.02:
        print("  warning: not 4:3 - the rectangle may include something other than the video")

    if not show(ruler):
        return 1
    time.sleep(4)
    shot(WORK / "m_ruler.png")
    img = np.asarray(Image.open(WORK / "m_ruler.png").convert("RGB")).astype(int)
    sub = img[y0:y1 + 1, x0:x1 + 1]
    scale = width / 640.0

    red = (sub[..., 0] > 140) & (sub[..., 1] < 100) & (sub[..., 2] < 100)
    blue = (sub[..., 2] > 140) & (sub[..., 0] < 100) & (sub[..., 1] < 100)
    white_mask = sub.min(axis=2) > 190

    def centre(mask: np.ndarray, fraction: float) -> float | None:
        columns = np.where(mask.sum(axis=0) > mask.shape[0] * fraction)[0]
        return float(columns.mean()) if columns.size else None

    print(f"\nscale {scale:.4f} capture px per source px")
    print(f"{'bar':12s} {'expected':>10s} {'measured':>10s} {'offset':>10s}")
    estimates = []
    for name, measured, expected in (("red", centre(red, 0.25), red_x),
                                     ("blue", centre(blue, 0.25), blue_x),
                                     ("white", centre(white_mask, 0.5), white_x)):
        if measured is None:
            print(f"{name:12s} {expected * scale:10.1f} {'not found':>10s}")
            continue
        offset = (measured - expected * scale) / scale
        estimates.append(offset)
        print(f"{name:12s} {expected * scale:10.1f} {measured:10.1f} {offset:+10.2f}")

    if estimates:
        mean = float(np.mean(estimates))
        spread = float(max(estimates) - min(estimates))
        print(f"\noffset {mean:+.2f} source pixels (spread {spread:.2f}); baseline +0.30")
        print("verdict:", "no visible offset" if abs(mean) < 2.0 else f"VISIBLE offset {mean:+.1f} px")
    else:
        print("\nno bars found - the picture on screen is not the ruler")

    if playing:
        board(f"echo {playing} > /tmp/hdmi_play.txt")
        print("playback resumed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
