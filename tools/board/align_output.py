#!/usr/bin/env python3
"""Align the board's HDMI output horizontally: measure the wrap, then write the compensation.

The problem this solves
    The stream that reaches v_axi4s_vid_out starts at an arbitrary pixel of the frame, because the
    SOF marker the output core needs (TUSER) is regenerated on the board (src/rtl/axis_sof_gen) from
    the line count and therefore anchors to whatever moment the pixel pipeline started. The picture
    is not shifted with a black border - it is *wrapped*: the frame starts partway into the image and
    the part that fell off the right edge reappears on the left.

    The phase is a property of the stream, not of the picture: measured on this bench it is exactly
    the same after re-uploads, after preset changes and after the resident's 5 Hz re-push, and it
    changes only when the pixel stream starts (a resident restart or a reboot). So it has to be
    measured once after the demo starts, which is what this tool does.

How it measures
    It displays eight saturated vertical bands, 80 source pixels each, and reads the picture back
    from the OBS preview. Every band is identified by hue, which survives the upload path's tone
    curve, and the band that is cut at the left edge says how far into the frame the wrap is:

        wrap = band_start(first band) + (80 - visible_width_of_that_band)

    Then it writes that value to /tmp/hdmi_roll.txt, which the resident applies as np.roll(pixels,
    roll, axis=1) on the next push, and measures again to confirm the residual is zero. If the first
    guess makes it worse (opposite sign convention), it tries the other candidate and keeps the
    better one. Finally the picture and preset that were on screen before are put back.

    python tools/board/align_output.py            measure, fix, verify, restore
    python tools/board/align_output.py --measure  only report what is on screen now

Why the OBS preview rather than the display
    There is no other way to see the output: the board sends TMDS to a sink, and the only sink here is
    the USB capture dongle that OBS owns. The tool therefore uses OBS's preview window, raising it to
    the foreground for the ~10 s it runs (and putting it back afterwards). It matches the process
    name obs64 rather than a window title, because the window title of *any* app that mentions OBS
    would match too - that mistake silently measured the wrong window and produced nonsense numbers.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO = Path(__file__).resolve().parents[2]
WORK = REPO / ".tmp" / "align"
BOARD = "xilinx@192.168.2.99"
ASKPASS = str(REPO / ".tmp" / "askpass" / "askpass.bat")
SHOW = REPO / "tools" / "board" / "show_image.ps1"

ROLL_FILE = "/tmp/hdmi_roll.txt"
PRESET_FILE = "/tmp/hdmi_preset.txt"
IMAGE_FILE = "/tmp/hdmi_image.txt"
STATE_FILE = "/tmp/hdmi_state.txt"

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
BAND = 80

# Capture the OBS window by rectangle, after putting it in front and (optionally) at a known place.
# Topmost is used because an ordinary foreground window can be covered by another topmost window.
CAPTURE_PS = r"""
Add-Type -AssemblyName System.Windows.Forms, System.Drawing
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class AlignCap {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern bool SetWindowPos(IntPtr h, IntPtr after, int x, int y, int cx, int cy, uint flags);
    [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h);
    [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
$obs = Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $obs) { Write-Output 'NOOBS'; exit 3 }
$hwnd = $obs.MainWindowHandle
$front = [AlignCap]::GetForegroundWindow()
[void][AlignCap]::ShowWindow($hwnd, 9)
$r = New-Object AlignCap+RECT
[void][AlignCap]::GetWindowRect($hwnd, [ref]$r)
$origL = $r.L; $origT = $r.T; $origW = $r.R - $r.L; $origH = $r.B - $r.T
# Raise OBS above everything (a plain foreground call can lose to another topmost window) and give
# it the whole screen, so the preview is not clipped and nothing of it is covered.
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
[void][AlignCap]::SetWindowPos($hwnd, [IntPtr](-1), 0, 0, $screen.Width, $screen.Height, 0x0040)
Start-Sleep -Milliseconds 600
$r2 = New-Object AlignCap+RECT
[void][AlignCap]::GetWindowRect($hwnd, [ref]$r2)
$x = $r2.L; $y = $r2.T; $cw = $r2.R - $r2.L; $ch = $r2.B - $r2.T
$bmp = New-Object System.Drawing.Bitmap $cw, $ch
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size($cw, $ch)))
$bmp.Save('PATH', [System.Drawing.Imaging.ImageFormat]::Png)
$g.Dispose(); $bmp.Dispose()
if (RESTORE -eq 1) {
    [void][AlignCap]::SetWindowPos($hwnd, [IntPtr](-2), 0, 0, 0, 0, 0x0002 -bor 0x0001)
    [void][AlignCap]::SetWindowPos($hwnd, [IntPtr](0), ORIGL, ORIGT, ORIGW, ORIGH, 0x0040)
    if (FOREGROUND -ne 0) { [void][AlignCap]::SetForegroundWindow([IntPtr]FOREGROUND) }
}
Write-Output ("CAPTURED {0},{1} {2}x{3}" -f $x, $y, $cw, $ch)
"""

# Geometry of the OBS window as the operator left it, plus whichever window had the focus. Taken once,
# before the first capture, so the tool can put the desktop back exactly as it was.
WINDOW_PS = r"""
Add-Type @'
using System;
using System.Runtime.InteropServices;
public class AlignWin {
    [StructLayout(LayoutKind.Sequential)] public struct RECT { public int L, T, R, B; }
    [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr h, out RECT r);
    [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
'@
$p = Get-Process obs64 -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $p) { Write-Output 'NOOBS'; exit 3 }
$r = New-Object AlignWin+RECT
[void][AlignWin]::GetWindowRect($p.MainWindowHandle, [ref]$r)
Write-Output ("WINDOW {0} {1} {2} {3} {4}" -f $r.L, $r.T, ($r.R - $r.L), ($r.B - $r.T),
              ([AlignWin]::GetForegroundWindow().ToInt64()))
"""


def _env() -> dict:
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    return env


def board(command: str, timeout: float = 60) -> str:
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                             "-o", "ConnectTimeout=10", BOARD, command],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            env=_env(), timeout=timeout)
    return (result.stdout or "").strip()


def board_state() -> dict:
    state = {}
    for line in board(f"cat {STATE_FILE} 2>/dev/null").splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            state[key.strip()] = value.strip()
    return state


def window_geometry() -> tuple[int, int, int, int, int] | None:
    """Where OBS is and which window has the focus, so both can be put back afterwards."""
    result = subprocess.run(["powershell", "-NoProfile", "-Command", WINDOW_PS],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=60)
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if not out.startswith("WINDOW"):
        print(f"   OBS is not running ({out.splitlines()[0] if out else 'no output'})")
        return None
    parts = out.split()[1:6]
    try:
        return tuple(int(v) for v in parts)          # left, top, width, height, foreground
    except ValueError:
        return None


def capture(path: Path, restore: bool, geometry=None) -> bool:
    script = CAPTURE_PS.replace("PATH", str(path).replace("'", "''"))
    script = script.replace("RESTORE", "1" if restore else "0")
    left, top, width, height, foreground = geometry if geometry else (0, 0, 0, 0, 0)
    script = (script.replace("ORIGL", str(left)).replace("ORIGT", str(top))
                    .replace("ORIGW", str(width)).replace("ORIGH", str(height))
                    .replace("FOREGROUND", str(foreground)))
    result = subprocess.run(["powershell", "-NoProfile", "-Command", script],
                            capture_output=True, text=True, encoding="utf-8", errors="replace",
                            timeout=120)
    out = ((result.stdout or "") + (result.stderr or "")).strip()
    if "CAPTURED" not in out:
        print(f"   capture failed: {out.splitlines()[0] if out else 'no output'}")
        return False
    return True


def show_picture(image: str, preset: str = "pass", no_tone: bool = True) -> bool:
    args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SHOW),
            "-Image", image, "-Preset", preset]
    if no_tone:
        args.append("-NoTone")
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=_env(), timeout=240)
    if result.returncode != 0:
        tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
        print(f"   upload failed (rc={result.returncode}): {tail[-1] if tail else 'no output'}")
        return False
    return True


def make_bands(path: Path) -> None:
    img = Image.new("RGB", (640, 480), (0, 0, 0))
    draw = ImageDraw.Draw(img)
    for index, (_, colour) in enumerate(COLOURS):
        draw.rectangle([index * BAND, 0, index * BAND + BAND - 1, 479], fill=colour)
    img.save(path)


def hue_of(pixel) -> float:
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


def measure_wrap(path: Path) -> float | None:
    """The wrap in source pixels, or None when the bands are not readable in this capture."""
    img = np.asarray(Image.open(path).convert("RGB")).astype(int)
    sat = (img.max(axis=2) - img.min(axis=2)) > 70
    columns = np.where(sat.sum(axis=0) > 200)[0]
    rows = np.where(sat.sum(axis=1) > 200)[0]
    if columns.size < 20 or rows.size < 20:
        return None

    # Classify the middle of the picture only: it is clear of the OBS selection border and of the
    # preview's own chrome, and both are the only things in the frame that are not a band.
    y0, y1 = int(rows[0]), int(rows[-1])
    height = y1 - y0 + 1
    left, right = int(columns[0]) + 2, int(columns[-1])
    band = img[y0 + height // 4: y1 - height // 4, left:max(left + 32, right)].mean(axis=0)

    references = [(name, hue_of(np.array(colour, dtype=float))) for name, colour in COLOURS]
    labels = []
    for x in range(band.shape[0]):
        pixel = band[x]
        if int(pixel.max()) - int(pixel.min()) < 60:
            labels.append("OTHER")
            continue
        hue = hue_of(pixel)
        best, best_delta = "OTHER", 1e9
        for name, reference in references:
            delta = min(abs(hue - reference), 360 - abs(hue - reference))
            if delta < best_delta:
                best, best_delta = name, delta
        labels.append(best if best_delta < 30 else "OTHER")

    runs = []
    current, start = labels[0], 0
    for x in range(1, len(labels)):
        if labels[x] != current:
            runs.append((current, start, x - 1))
            current, start = labels[x], x
    runs.append((current, start, len(labels) - 1))

    bands = [run for run in runs if run[0] != "OTHER" and run[2] - run[1] >= 8]
    if len(bands) < 3:
        return None
    widths = np.array([end - begin + 1 for _, begin, end in bands], dtype=float)
    full = float(np.median(widths[1:-1] if widths.size > 2 else widths))
    scale = full / BAND
    first_name, first_start, first_end = bands[0]
    index = [name for name, _ in COLOURS].index(first_name)
    cut = (full - (first_end - first_start + 1)) / scale
    return (index * BAND + cut) % 640


def residual(path: Path) -> float | None:
    """Distance from aligned, for a measurement of an already-compensated picture."""
    wrap = measure_wrap(path)
    if wrap is None:
        return None
    return min(wrap, 640.0 - wrap)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--measure", action="store_true",
                    help="only report the current wrap, change nothing")
    ap.add_argument("--keep", action="store_true",
                    help="leave the OBS window in front (for inspecting it afterwards)")
    args = ap.parse_args(argv)

    WORK.mkdir(parents=True, exist_ok=True)
    bands = WORK / "bands.png"
    make_bands(bands)
    shot = WORK / "shot.png"

    geometry = window_geometry()
    if geometry is None:
        print("OBS must be running with the capture device previewing: its preview is the only "
              "place the board's output can be read. Nothing was changed.")
        return 2

    state = board_state()
    before = {"roll": board(f"cat {ROLL_FILE} 2>/dev/null"),
              "preset": board(f"cat {PRESET_FILE} 2>/dev/null"),
              "image": board(f"cat {IMAGE_FILE} 2>/dev/null")}
    print(f"board now: roll={before['roll'] or '?'} preset={before['preset'] or '?'} "
          f"image={before['image'] or '?'}")

    # While a clip plays, the resident pushes a video frame every 40 ms and ignores the still picture,
    # so the test pattern would never reach the screen and the capture would show the video instead.
    # Say so instead of failing later with "could not read the bands".
    if state.get("playing"):
        print(f"a clip is playing ({state['playing']}), so the test pattern would not appear. "
              f"Stop playback first:\n"
              f"  tools\\board\\play_video.ps1 -Video x -Stop\n"
              f"then run this again. Nothing was changed.")
        return 2

    if args.measure:
        if not capture(shot, restore=not args.keep, geometry=geometry):
            return 2
        wrap = measure_wrap(shot)
        if wrap is None:
            print("could not read the bands - is the board showing the test pattern? "
                  "run without --measure to push it and fix the offset")
            return 2
        print(f"measured wrap {wrap:.1f} source px "
              f"({'aligned' if min(wrap, 640 - wrap) < 2 else 'offset'})")
        print(f"roll that would centre it: {(round(wrap)) % 640}")
        return 0

    keep_window = args.keep

    def restore_roll_and_content() -> None:
        board(f"echo {before['roll'] or 0} > {ROLL_FILE}")
        if before["image"]:
            board(f"echo {before['image']} > {IMAGE_FILE}")
        if before["preset"]:
            board(f"echo {before['preset']} > {PRESET_FILE}")

    try:
        # 1) measure with the compensation removed, so the number is the stream's own phase
        print("measuring (8 colour bands, preset 'pass' so the colours are untouched)...")
        board(f"echo 0 > {ROLL_FILE}")
        time.sleep(1.5)
        if not show_picture(str(bands), "pass"):
            restore_roll_and_content()
            return 2
        time.sleep(3.0)
        if not capture(shot, restore=False):
            restore_roll_and_content()
            return 2
        wrap = measure_wrap(shot)
        if wrap is None:
            capture(shot, restore=not keep_window, geometry=geometry)
            restore_roll_and_content()
            print("could not read the bands in the OBS capture - is OBS previewing the capture "
                  "device, and is the board streaming? Nothing was changed.")
            return 2
        print(f"   the picture starts {wrap:.1f} px into the frame")

        # 2) apply the compensation, then confirm it worked by measuring again
        best = None
        for candidate in (round(wrap) % 640, (640 - round(wrap)) % 640):
            board(f"echo {candidate} > {ROLL_FILE}")
            time.sleep(2.0)
            if not capture(shot, restore=False):
                continue
            left = residual(shot)
            print(f"   roll {candidate:3d} -> residual {left if left is None else round(left, 1)} px")
            if left is not None and (best is None or left < best[1]):
                best = (candidate, left)
            if best is not None and best[1] < 2:
                break

        if best is None:
            capture(shot, restore=not keep_window, geometry=geometry)
            restore_roll_and_content()
            print("no candidate aligned the picture - nothing was changed. "
                  "Check that OBS shows the board and that the preview is not frozen.")
            return 2

        roll, left = best
        board(f"echo {roll} > {ROLL_FILE}")
        time.sleep(1.5)

        # 3) put the operator's picture and preset back, and let the resident re-push them
        if before["image"]:
            board(f"echo {before['image']} > {IMAGE_FILE}")
        if before["preset"]:
            board(f"echo {before['preset']} > {PRESET_FILE}")
        time.sleep(3.0)
        if not capture(shot, restore=not keep_window, geometry=geometry):
            print(f"aligned with roll {roll} (residual {left:.1f} px on the bands), "
                  f"but the final screenshot failed")
            return 0
        print(f"\nRESULT: roll={roll}, residual {left:.1f} px on the bands")
        print(f"   the previous picture ({before['image'] or '?'}) and preset "
              f"({before['preset'] or '?'}) are back on screen")
        print(f"   the value is a property of this run of the pixel stream; it is re-measured "
              f"whenever the demo restarts")
        return 0
    except Exception as exc:                                  # noqa: BLE001
        restore_roll_and_content()
        print(f"failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
