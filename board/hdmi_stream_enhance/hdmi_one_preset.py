#!/usr/bin/env python3
"""One preset, one frame, nothing else - for a full minute.

Purpose
    The preset-cycle demos reset the kernel on every switch, and they write frames into
    DDR. Both were eliminated as causes of the observed flicker, so this script removes
    them entirely: it writes a single frame, selects one preset once, and then does
    nothing at all for the hold period except read the latency counter.

    If the picture is stable here, the flicker is triggered by the switch itself (the
    kernel reset) rather than by the video path - which points at replacing the reset with
    a per-pixel configuration read from BRAM.
    If it still flickers with nothing happening, the instability is inside the kernel's
    per-frame behaviour and independent of everything the PS does.

    sudo python3 -u hdmi_one_preset.py --preset night --hold 60
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl


def test_image(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)
    ramp = np.linspace(20, 235, height, dtype=np.uint8).reshape(height, 1)
    img[:, :, 0] = ramp
    img[:, :, 1] = ramp
    img[:, :, 2] = ramp
    band_top, band_height = height // 2 - 60, 120
    img[band_top:band_top + band_height, :, :] = 128
    for row in range(band_top + 10, band_top + band_height - 10, 22):
        left = 40
        while left < width - 60:
            run = int(30 + (left * 7) % 90)
            img[row:row + 10, left:min(left + run, width - 40), :] = 25
            left += run + 18
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--preset", default="night", choices=sorted(hl.PRESETS))
    ap.add_argument("--hold", type=float, default=60.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video
    out = video.hdmi_out

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        hpd.mmio.write(0x00, 0x1)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    out.configure(VideoMode(width, height, 24, 60))
    out.start()

    frame = out.newframe()
    frame[:] = test_image(width, height)
    out.writeframe(frame)
    hl.write_preset(cfg, args.preset)
    print(f"one frame written, preset {args.preset} selected; "
          f"now completely idle for {args.hold:.0f}s", flush=True)

    held = 0.0
    while held < args.hold:
        time.sleep(5.0)
        held += 5.0
        n = hl.read_latency(lat)
        print(f"  idle {held:.0f}/{args.hold:.0f}s, latency {n}", flush=True)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
