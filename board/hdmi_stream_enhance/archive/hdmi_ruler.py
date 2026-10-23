#!/usr/bin/env python3
"""Measure the horizontal offset of the picture with a ruler pattern.

Why
    Several captures show the card shifted left, with the missing left edge reappearing on the
    right - a wrap-around. Two very different causes produce that look:

      * the capture dongle re-locked with a different sampling phase (it happens after every
        signal interruption and is not our problem), or
      * the kernel's fixed pipeline delay moved the frame relative to the video timing.

    A ruler settles it in one glance: three bars at known columns, plus markers every 100
    pixels. If the bars land where they should, the pipeline is aligned and the shift is in the
    capture chain; if they are displaced by a constant amount, that amount is the offset.

    sudo python3 -u hdmi_ruler.py --hold 120
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl


def ruler(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Bars at known columns: 0 (white), 100 (red), 500 (blue). If the leftmost bar shows up on
    # the right edge instead, the picture is wrapped by the offset.
    img[:, 0:8, :] = 255
    img[0:40, 0:8, :] = 255
    img[:, 100:108, 0] = 255
    img[:, 500:508, 2] = 255

    # Tick marks every 100 columns, 20 px tall, at the top and bottom.
    for x in range(0, width, 100):
        img[0:20, x:x + 4, :] = 0
        img[0:20, x:x + 4, 1] = 255
        img[height - 20:height, x:x + 4, :] = 0
        img[height - 20:height, x:x + 4, 1] = 255

    # A grey band across the middle so a vertical shift would also be obvious.
    img[height // 2 - 10:height // 2 + 10, :, :] = 90

    # Left and right borders make the wrap unmistakable.
    img[:, 0:2, :] = 255
    img[:, width - 2:width, :] = 255
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--preset", default="pass")
    ap.add_argument("--roll", type=int, default=0,
                    help="shift the pattern right by N px (compensates pipeline latency)")
    ap.add_argument("--hold", type=float, default=120.0)
    args = ap.parse_args(argv)

    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    ol = hl.open_overlay(args.bitstream)
    out = ol.video.hdmi_out
    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    picture = ruler(width, height)
    if args.roll:
        picture = hl.roll_frame(picture, args.roll)
        print(f"ruler rolled right by {args.roll} px", flush=True)
    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    for _ in range(4):
        buf = out.newframe()
        buf[:] = picture
        out.writeframe(buf)

    hl.write_preset(cfg, args.preset)
    print(f"ruler on screen, preset {args.preset}, latency {hl.read_latency(lat)}", flush=True)
    print("bars to look for: white at column 0, red at 100, blue at 500,", flush=True)
    print("green ticks at 0/100/200/.../600, thin white border on both edges", flush=True)
    print(f"holding {args.hold:.0f} s", flush=True)
    time.sleep(args.hold)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
