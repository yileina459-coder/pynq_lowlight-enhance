"""Drive the four switching cases and record what the board says after each.

Why the state file rather than a screenshot
    Screenshots have been an unreliable oracle tonight: a capture froze, a cached rectangle went stale, and
    one pattern appeared as three lines. The state file is written by the process that owns the pixel
    stream, so "did the switch happen, and did the previous content get replaced" is answerable from it
    plus the resident's own log lines - without any dependence on OBS geometry.

    The four cases the user cares about:
        image -> image      two different pictures back to back
        image -> video      a clip after a picture
        video -> video      a second clip after the first
        video -> image      a picture after a clip (must stop the playback, or the picture never shows)

    python tools/diag/switch_matrix.py
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ASKPASS = str(REPO / ".tmp" / "askpass" / "askpass.bat")
BOARD = "xilinx@192.168.2.99"
DESKTOP = Path.home() / "Desktop"

SHOW = REPO / "tools" / "board" / "show_image.ps1"
PLAY = REPO / "tools" / "board" / "play_video.ps1"
PYTHON = sys.executable


def board(command: str) -> str:
    import os
    env = os.environ.copy()
    env.update({"SSH_ASKPASS": ASKPASS, "SSH_ASKPASS_REQUIRE": "force", "DISPLAY": ":0"})
    result = subprocess.run(["ssh", "-o", "StrictHostKeyChecking=no", "-o", "LogLevel=ERROR",
                             "-o", "ConnectTimeout=10", BOARD, command],
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", env=env, timeout=90)
    return (result.stdout or "").strip()


def state() -> dict[str, str]:
    text = board("cat /tmp/hdmi_state.txt 2>/dev/null")
    out = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def run(label: str, args: list[str]) -> None:
    env_args = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *args]
    result = subprocess.run(env_args, capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=900)
    tail = ((result.stdout or "") + (result.stderr or "")).strip().splitlines()
    status = "ok" if result.returncode == 0 else f"rc={result.returncode}"
    print(f"  upload {label}: {status}")
    for line in tail[-2:]:
        print(f"    {line.strip()[:100]}")


def main() -> int:
    images = ["测试图1.jpg", "测试图2.jpg"]
    videos = ["测试视频1.mp4", "测试视频2.mp4"]
    for name in images + videos:
        if not (DESKTOP / name).exists():
            print(f"missing {DESKTOP / name}")
            return 1

    print("board state before anything:")
    before = state()
    print("  " + "  ".join(f"{k}={v}" for k, v in before.items() if k in ("image", "playing", "preset")))

    steps: list[tuple[str, list[str], str]] = [
        (f"image {images[0]}", [str(SHOW), "-Image", str(DESKTOP / images[0]), "-Preset", "clarity"], "image"),
        (f"image {images[1]}", [str(SHOW), "-Image", str(DESKTOP / images[1]), "-Preset", "clarity"], "image"),
        (f"video {videos[0]}", [str(PLAY), "-Video", str(DESKTOP / videos[0]), "-Fps", "24",
                                "-Seconds", "4", "-Auto", "clip"], "video"),
        (f"video {videos[1]}", [str(PLAY), "-Video", str(DESKTOP / videos[1]), "-Fps", "24",
                                "-Seconds", "4", "-Auto", "clip"], "video"),
        (f"image {images[0]} (again)", [str(SHOW), "-Image", str(DESKTOP / images[0]),
                                        "-Preset", "clarity"], "image"),
    ]

    print("\nrunning the switching matrix:")
    history = []
    for label, args, kind in steps:
        run(label, args)
        time.sleep(3)
        now = state()
        history.append((kind, label, now))
        print(f"    -> image={now.get('image', '')}")
        print(f"       playing={now.get('playing', '')}  preset={now.get('preset', '')}")

    print("\nsummary:")
    ok = True
    for index, (kind, label, now) in enumerate(history):
        playing = now.get("playing", "")
        if kind == "image":
            good = playing == "" and now.get("image", "").endswith(".png")
        else:
            good = "frames" in playing
        ok &= good
        print(f"  {'PASS' if good else 'FAIL'}  {label}  -> image={Path(now.get('image', '')).name}  "
              f"playing='{playing}'")

    if len(history) >= 5:
        same_image = history[0][2].get("image") == history[1][2].get("image")
        same_clip = history[2][2].get("playing") == history[3][2].get("playing")
        print(f"\n  two pictures produced {'the SAME upload (bug)' if same_image else 'different uploads'} ✓")
        print(f"  two clips produced {'the same frame count (check the dirs)' if same_clip else 'different frame counts'}")

    print("\nlast 8 log lines:")
    for line in board("tail -8 /tmp/res_sof_fix.log 2>/dev/null").splitlines():
        print(f"  {line}")
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
