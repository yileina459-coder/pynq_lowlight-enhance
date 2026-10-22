#!/usr/bin/env python3
"""Play a sequence of frames through the overlay, so the FPGA processes real video.

Why this shape
    The kernel is a streaming pipeline fed by the AXI VDMA from DDR, so "video" here means frames
    arriving at 60 Hz. Two facts decide how such a player can work:

      * the kernel processes one pixel per pixel clock (II = 1 at 142.857 MHz) and only needs
        25.175 MHz for 640x480, so the hardware has about 7x headroom at 60 fps;
      * feeding a frame from the PS costs about 15.6 ms measured (writeframe + the VDMA consuming
        it), i.e. ~63 frames/s. A 60 fps loop therefore has almost no margin, while 30 fps is
        comfortable - which is why the frame rate is a parameter with a sane default.

    Frames are pre-decoded PNGs on the board; decoding video in the PS is far slower than the
    pipeline and would make the loop miss its deadline. tools/make_video_frames.py does the
    decoding on the PC and uploads a numbered sequence.

    sudo python3 hdmi_player.py --frames /tmp/hdmi_uploads/clip --fps 30 --preset clarity

    Controls are the same files as the resident demo, so a running player can be retuned without
    restarting it (restarting interrupts the stream, and this capture dongle only re-locks after a
    physical replug).
"""

from __future__ import annotations

import argparse
import glob
import os
import sys
import time

import numpy as np
from PIL import Image
from pynq import Overlay
from pynq.lib.video import VideoMode

import hdmi_live as hl

WIDTH, HEIGHT = 640, 480
ROLL_FILE = "/tmp/hdmi_roll.txt"
PRESET_FILE = "/tmp/hdmi_preset.txt"
STATE_FILE = "/tmp/hdmi_state.txt"


def read_text(path: str, default: str = "") -> str:
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return default


def load_frame(path: str) -> np.ndarray:
    """Read one frame and fit it to the panel without distorting it."""
    with Image.open(path) as img:
        img = img.convert("RGB")
        scale = min(WIDTH / img.width, HEIGHT / img.height)
        size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (0, 0, 0))
        canvas.paste(img.resize(size, Image.LANCZOS),
                     ((WIDTH - size[0]) // 2, (HEIGHT - size[1]) // 2))
        return np.asarray(canvas)


def roll_rows(pixels: np.ndarray, shift: int) -> np.ndarray:
    if not shift:
        return pixels
    return np.roll(pixels, shift, axis=1)


def publish(state: dict, index: int, total: int, fps: float) -> None:
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(f"image={state['frame']}\n")
            fh.write(f"roll={state['roll']}\n")
            fh.write(f"preset={state['preset']}\n")
            fh.write(f"mode={WIDTH}x{HEIGHT}\n")
            fh.write(f"playing=frame {index + 1}/{total} at {fps:.1f} fps\n")
            fh.write(f"updated={time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    except OSError:
        pass


def prepare_control_files() -> None:
    os.umask(0o000)
    for path in (ROLL_FILE, PRESET_FILE, STATE_FILE):
        try:
            with open(path, "a", encoding="utf-8"):
                pass
            os.chmod(path, 0o666)
        except OSError:
            pass


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frames", required=True,
                    help="directory containing frame_00000.png, frame_00001.png, ...")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--preset", default="clarity")
    ap.add_argument("--roll", type=int, default=0)
    ap.add_argument("--loops", type=int, default=0, help="0 = play forever")
    args = ap.parse_args(argv)

    paths = sorted(glob.glob(os.path.join(args.frames, "frame_*.png")))
    if not paths:
        print(f"PLAYER FAIL: no frame_*.png under {args.frames}")
        return 1
    print(f"{len(paths)} frame(s) from {args.frames}")

    prepare_control_files()

    ol = Overlay("enhance_hdmi.bit")
    cfg = hl.find(ol, "gpio_enh")
    out = ol.video.hdmi_out
    print(f"output mode currently {out.mode.width}x{out.mode.height}")

    state = {"roll": args.roll, "preset": args.preset, "frame": paths[0]}
    hl.start_output(ol, out, WIDTH, HEIGHT)
    hl.write_preset(cfg, state["preset"])

    # One buffer is enough: a fresh frame is written every iteration, and the VDMA pulls it as the
    # display needs it. Using the same buffer keeps the PS copy cost predictable.
    buf = out.newframe()
    deadline = time.monotonic()
    interval = 1.0 / max(args.fps, 1.0)

    print(f"playing at {args.fps:g} fps with preset '{state['preset']}' "
          f"(controls: {ROLL_FILE}, {PRESET_FILE})")
    loop = 0
    played = 0
    while args.loops == 0 or loop < args.loops:
        for index, path in enumerate(paths):
            roll_text = read_text(ROLL_FILE)
            if roll_text.lstrip("-").isdigit() and int(roll_text) != state["roll"]:
                state["roll"] = int(roll_text)
                print(f"  roll -> {state['roll']}", flush=True)

            preset_text = read_text(PRESET_FILE)
            if preset_text and preset_text != state["preset"] and preset_text in hl.PRESETS:
                state["preset"] = preset_text
                hl.write_preset(cfg, preset_text)
                print(f"  preset -> {preset_text}", flush=True)

            state["frame"] = os.path.basename(path)
            buf[:] = roll_rows(load_frame(path), state["roll"])
            out.writeframe(buf)
            played += 1

            if index % 15 == 0:
                publish(state, index, len(paths), args.fps)

            deadline += interval
            sleep = deadline - time.monotonic()
            if sleep > 0:
                time.sleep(sleep)
            else:
                # Behind schedule: resync rather than accumulate debt, and say so, because a
                # silently dropped frame rate is the difference between "video" and "slideshow".
                if -sleep > interval:
                    print(f"  behind by {-sleep * 1000:.0f} ms - resynchronising", flush=True)
                deadline = time.monotonic()

        loop += 1
        if args.loops and loop >= args.loops:
            break

    print(f"finished after {played} frames ({loop and played / max(loop, 1):.0f} per loop)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
