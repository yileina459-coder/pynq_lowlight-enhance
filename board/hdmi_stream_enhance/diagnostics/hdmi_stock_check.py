#!/usr/bin/env python3
"""Load the STOCK PYNQ base overlay and report whether HDMI IN sees a source.

Why this exists
    Our overlay inserts the kernel between pixel_pack and pixel_unpack. If the
    laptop never detects a display when plugged into the board, there are two very
    different possibilities and this script separates them:

      * stock base.bit also reports no mode  -> the problem is the port, the cable
        or the EDID handshake, i.e. not our design;
      * stock base.bit reports 1280x720      -> our overlay broke something in the
        video hierarchy, and that is on me to fix.

    The stock overlay still has its VDMA loopback, so it also drives HDMI OUT with
    a frame buffer - which means the capture card should show something too.

    sudo python3 hdmi_stock_check.py
"""

from __future__ import annotations

import time

STOCK = "/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit"


def main() -> int:
    from pynq import Overlay

    print(f"loading stock overlay {STOCK}")
    ol = Overlay(STOCK)
    print(f"  IPs: {len(ol.ip_dict)}")
    if not hasattr(ol, "video"):
        print("FAIL: stock overlay did not bind pynq.lib.video")
        return 1

    video = ol.video
    print(f"  hdmi_in : {video.hdmi_in}")
    print(f"  hdmi_out: {video.hdmi_out}")

    # Give the source a moment: the EDID handshake happens when the cable is
    # already in place, but a source that was just plugged in can take a second.
    for attempt in range(10):
        mode = video.hdmi_in.mode
        print(f"  [{attempt}] input mode: {mode}")
        if mode is not None:
            print()
            print(f"RESULT: STOCK OVERLAY SEES THE SOURCE -> {mode.width}x{mode.height} "
                  f"@{mode.frame_rate} Hz")
            print("        The board and cable are fine; the problem is in our overlay.")
            return 0
        time.sleep(1.0)

    print()
    print("RESULT: STOCK OVERLAY SEES NOTHING EITHER")
    print("        So the port, the cable or the EDID handshake is the problem,")
    print("        not the enhance overlay. Try, in this order:")
    print("          1. the other HDMI cable")
    print("          2. the other HDMI connector on the board (IN vs OUT)")
    print("          3. unplug and replug the cable while this script runs")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
