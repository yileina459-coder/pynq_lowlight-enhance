#!/usr/bin/env python3
"""Control experiment: the same ruler, but through the stock overlay with no kernel.

Why
    Captures show the picture shifted left with the missing left edge reappearing on the right -
    a wrap of roughly 30 pixels. Two candidates produce that: the capture dongle's sampling
    phase, or something in our pipeline moving the frame relative to the video timing.

    The stock PYNQ base overlay has a complete HDMI output path (its own VDMA, its own timing
    generator) and none of our logic. Showing the identical ruler through it isolates the
    question completely:

      * wrap in the same place  -> the capture chain, not our design
      * wrap gone               -> our path is what shifts the picture

    The stock overlay is only used at 640x480 because that is the only mode this board's HDMI
    output drives (800x600 and above never consume a frame - see docs/hdmi_status.md).

    sudo python3 hdmi_stock_640.py --hold 240
"""

from __future__ import annotations

import argparse
import time

import numpy as np

STOCK = ("/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/"
         "base/base.bit")


def ruler(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:, 0:8, :] = 255                     # white bar at column 0
    img[:, 100:108, 0] = 255                 # red bar at 100
    img[:, 500:508, 2] = 255                 # blue bar at 500
    for x in range(0, width, 100):           # ticks every 100 columns
        img[0:20, x:x + 4, :] = 0
        img[0:20, x:x + 4, 1] = 255
        img[height - 20:height, x:x + 4, :] = 0
        img[height - 20:height, x:x + 4, 1] = 255
    img[height // 2 - 10:height // 2 + 10, :, :] = 90
    img[:, 0:2, :] = 255                     # both borders, so a wrap is obvious
    img[:, width - 2:width, :] = 255
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--fps", type=int, default=60)
    ap.add_argument("--hold", type=float, default=240.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading stock overlay {STOCK}", flush=True)
    ol = Overlay(STOCK)
    out = ol.video.hdmi_out

    # The stock design has the same tri-stated HPD GPIO; drive it, or the capture dongle keeps
    # its receiver off and this control experiment shows nothing.
    for name in ol.ip_dict:
        if "hpd" in name.lower():
            dev = getattr(ol, name, None)
            if dev is not None and hasattr(dev, "mmio"):
                dev.mmio.write(0x04, 0x00000000)
                dev.mmio.write(0x00, 0x00000001)
                print(f"drove {name} HPD high", flush=True)

    out.configure(VideoMode(args.width, args.height, 24, args.fps))
    out.start()
    print(f"stock output at {args.width}x{args.height} @ {args.fps}", flush=True)

    picture = ruler(args.width, args.height)
    for _ in range(4):
        buf = out.newframe()
        buf[:] = picture
        out.writeframe(buf)
    print("ruler written through the STOCK path (no kernel involved)", flush=True)
    print(f"holding {args.hold:.0f} s - compare the wrap position against the enhanced path",
          flush=True)
    time.sleep(args.hold)
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
