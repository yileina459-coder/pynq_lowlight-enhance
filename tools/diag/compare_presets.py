"""Compare two presets on the board, with the video rectangle calibrated first.

Method, and why it looks the way it does
    1. capture OBS's *window*, after raising it to the front;
    2. show solid white, capture; show solid black, capture; difference gives the video rectangle,
       because those are the only pixels that change;
    3. for each preset, upload the test picture, capture, and measure.

    Two earlier versions of this measurement were wrong for the same reason, in different disguises:
    a whole-desktop capture measures whatever window happens to be on top. Once the preview was covered,
    a white and a black screenshot came back almost identical and the tool confidently reported "the
    board did not change". Capturing the OBS window by rectangle removes that failure mode; calibrating
    every run rather than caching a rectangle removes the other (window moved since last time).

    python tools/diag/compare_presets.py --image data/images/test_dim_720p.png --presets clarity,crisp
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import os

import numpy as np
from PIL import Image
from numpy.lib.stride_tricks import sliding_window_view

REPO = Path(__file__).resolve().parents[2]
ASKPASS = str(REPO / ".tmp" / "askpass" / "askpass.bat")
SHOW = REPO / "tools" / "board" / "show_image.ps1"
RECT_FILE = REPO / ".tmp" / "video_rect.txt"
BOARD = "xilinx@192.168.2.99"

SHOT_PS = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class DshWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
}
'@
$proc = Get-Process | Where-Object { $_.MainWindowTitle -like '*OBS*' } | Select-Object -First 1
if (-not $proc) { Write-Output 'NOOBS'; exit 1 }
[void][DshWin]::ShowWindow($proc.MainWindowHandle, 9)
[void][DshWin]::SetForegroundWindow($proc.MainWindowHandle)
Start-Sleep -Milliseconds 700
$r = New-Object DshWin+RECT
[void][DshWin]::GetWindowRect($proc.MainWindowHandle, [ref]$r)
$w = $r.R - $r.L
$h = $r.B - $r.T
if ($w -le 0 -or $h -le 0) { Write-Output 'BADRECT'; exit 1 }
$bmp = New-Object System.Drawing.Bitmap $w, $h
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($r.L, $r.T, 0, 0, (New-Object System.Drawing.Size($w, $h)))
$bmp.Save(PATH, [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose()
$bmp.Dispose()
Write-Output ("CAPTURED {0}x{1}" -f $w, $h)
"""


def board_preset() -> str:
    """The board's current manual preset, or '' if it cannot be read."""
    command = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
               "-o", "ConnectTimeout=10", BOARD, "cat /tmp/hdmi_preset.txt"]
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    try:
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=env, timeout=40)
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return ""


def set_board_preset(name: str) -> bool:
    if not name:
        return False
    command = ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
               "-o", "ConnectTimeout=10", BOARD, f"echo {name} > /tmp/hdmi_preset.txt"]
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    try:
        subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", env=env, timeout=40)
        return True
    except subprocess.TimeoutExpired:
        return False


def play_file() -> str:
    """What /tmp/hdmi_play.txt currently asks for ('' when nothing is playing)."""
    return _board_cmd("cat /tmp/hdmi_play.txt 2>/dev/null | tr -d '\\000' | head -c 200")


def _board_cmd(command: str) -> str:
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    try:
        result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                                 "-o", "ConnectTimeout=10", BOARD, command],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", env=env, timeout=45)
        return (result.stdout or "").strip()
    except subprocess.TimeoutExpired:
        return ""


def pause_playback() -> str:
    """Stop playback so a still picture can actually reach the screen.

    While a clip is playing, the resident pushes a video frame every 40 ms and ignores changes to the
    still image - so uploading white and then black changes /tmp/hdmi_image.txt and nothing on screen,
    which reads as "the board did not change" and sent this tool's calibration down the wrong path.
    Returns the previous play target so it can be resumed.
    """
    previous = play_file()
    if previous:
        _board_cmd(": > /tmp/hdmi_play.txt")
        time.sleep(2.5)
    return previous


def resume_playback(previous: str) -> None:
    if previous:
        _board_cmd(f"echo {previous} > /tmp/hdmi_play.txt")


def shot(path: Path) -> str:
    result = subprocess.run(["powershell", "-NoProfile", "-Command",
                             SHOT_PS.replace("PATH", f"'{path}'")],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=120)
    return ((result.stdout or "") + (result.stderr or "")).strip()


def show(image: Path, preset: str, no_tone: bool = False) -> bool:
    command = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SHOW),
               "-Image", str(image), "-Preset", preset]
    if no_tone:
        command.append("-NoTone")
    # Inherit the real environment and only add the ssh password helper. A hand-built minimal
    # environment breaks ssh: without HOME/USERPROFILE it cannot find known_hosts, the upload inside
    # show_image.ps1 fails, and because the caller ignored the return value the calibration silently
    # measured two identical screenshots and reported "the board did not change".
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=240)
    if result.returncode != 0:
        tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
        print(f"    upload failed (rc={result.returncode}): {tail[-1] if tail else 'no output'}")
    return result.returncode == 0


def calibrate(work: Path) -> tuple[int, int, int, int]:
    white = work / "cal_white.png"
    black = work / "cal_black.png"
    Image.new("RGB", (640, 480), (255, 255, 255)).save(white)
    Image.new("RGB", (640, 480), (0, 0, 0)).save(black)

    if not show(white, "pass", True):
        raise SystemExit("calibration aborted: the white frame could not be uploaded")
    time.sleep(4)
    print("  white:", shot(work / "cal_a.png"))
    if not show(black, "pass", True):
        raise SystemExit("calibration aborted: the black frame could not be uploaded")
    time.sleep(4)
    print("  black:", shot(work / "cal_b.png"))

    a = np.asarray(Image.open(work / "cal_a.png").convert("L")).astype(int)
    b = np.asarray(Image.open(work / "cal_b.png").convert("L")).astype(int)
    diff = np.abs(a - b)
    mask = diff > 40
    rows = np.where(mask.sum(axis=1) > 100)[0]
    cols = np.where(mask.sum(axis=0) > 80)[0]
    if rows.size < 2 or cols.size < 2:
        raise SystemExit(
            "calibration failed: the preview did not change between white and black.\n"
            f"  changed pixels: {int(mask.sum())}, max difference: {int(diff.max())}\n"
            "  the capture is probably not showing the board - is OBS previewing the capture device?")
    rect = (int(cols[0]), int(rows[0]), int(cols[-1]), int(rows[-1]))
    RECT_FILE.write_text(",".join(str(v) for v in rect))
    return rect


def measure(path: Path, rect: tuple[int, int, int, int]) -> dict[str, float]:
    x0, y0, x1, y1 = rect
    rgb = np.asarray(Image.open(path).convert("RGB")).astype(float)
    sub = rgb[y0 + 12:y1 - 12, x0 + 12:x1 - 12]
    y = (77 * sub[..., 0] + 150 * sub[..., 1] + 29 * sub[..., 2]) / 256.0
    window = sliding_window_view(y, (5, 5))
    return {
        "local_p90": float(np.percentile(window.std(axis=(-1, -2)), 90)),
        "edge": float((np.abs(np.diff(y, axis=1)).mean() + np.abs(np.diff(y, axis=0)).mean()) / 2),
        "mean": float(y.mean()),
        "black": float((y <= 2).mean() * 100),
        "blown": float((y >= 253).mean() * 100),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--image", default="data/images/test_dim_720p.png")
    ap.add_argument("--presets", default="clarity,crisp")
    args = ap.parse_args(argv)

    image = REPO / args.image
    presets = [p.strip() for p in args.presets.split(",") if p.strip()]
    work = REPO / ".tmp" / "cmp"
    work.mkdir(parents=True, exist_ok=True)

    print("calibrating (white then black):")
    rect = calibrate(work)
    print(f"video area {rect[0]},{rect[1]}..{rect[2]},{rect[3]}  "
          f"({rect[2] - rect[0] + 1}x{rect[3] - rect[1] + 1})")

    # Remember what was on screen before touching anything: this tool changes both the preset and what is
    # being displayed, and leaving a dark clip running with a preset that applies no gain looks exactly
    # like a black screen.
    restore = board_preset()
    was_playing = pause_playback()
    if restore:
        print(f"(will restore preset '{restore}' when done)")
    if was_playing:
        print(f"(playback paused; will resume {was_playing})")

    results: dict[str, dict[str, float]] = {}
    for preset in presets:
        if not show(image, preset):
            print(f"  {preset}: upload failed")
            continue
        time.sleep(4)
        path = work / f"shot_{preset}.png"
        shot(path)
        results[preset] = measure(path, rect)
        print(f"  {preset:10s} " + "  ".join(f"{k}={v:7.2f}" for k, v in results[preset].items()))

    if len(results) >= 2:
        names = list(results)
        base = results[names[0]]
        print()
        for name in names[1:]:
            other = results[name]
            print(f"{name} 相对 {names[0]}: 局部对比 {100 * (other['local_p90'] / base['local_p90'] - 1):+5.1f}%  "
                  f"边缘 {100 * (other['edge'] / base['edge'] - 1):+5.1f}%  "
                  f"纯黑 {other['black'] - base['black']:+5.1f}pt  "
                  f"过曝 {other['blown'] - base['blown']:+5.1f}pt")

    if restore and set_board_preset(restore):
        print(f"preset restored to '{restore}'")
    resume_playback(was_playing)
    if was_playing:
        print(f"playback resumed: {was_playing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
