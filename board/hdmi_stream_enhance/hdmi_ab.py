#!/usr/bin/env python3
"""A/B two presets on the HDMI output, with the config readback printed.

``pass`` and ``binarize`` are as different as two settings can be on the same image
(colour gradient versus a hard black/white split), so if the picture does not flip
between them, the configuration is not reaching the kernel - and printing the GPIO
readback separates "the write did not land" from "the write landed but the kernel
ignored it".

    sudo python3 -u hdmi_ab.py --a pass --b binarize --hold 6
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
    ap.add_argument("--a", default="pass")
    ap.add_argument("--b", default="binarize")
    ap.add_argument("--hold", type=float, default=6.0)
    ap.add_argument("--rounds", type=int, default=8)
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
    print(f"hdmi_out running at {width}x{height}", flush=True)

    image = test_image(width, height)
    frame = out.newframe()
    frame[:] = image
    out.writeframe(frame)
    print("test image written once; the VDMA repeats it", flush=True)

    for rnd in range(args.rounds):
        for name in (args.a, args.b):
            lo, hi = hl.write_preset(cfg, name)
            rb = (cfg.mmio.read(0x00), cfg.mmio.read(0x08))
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] {name:<9} "
                  f"wrote lo=0x{lo:08x} hi=0x{hi:08x}  readback lo=0x{rb[0]:08x} "
                  f"hi=0x{rb[1]:08x}  latency {n}", flush=True)
            time.sleep(args.hold)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
