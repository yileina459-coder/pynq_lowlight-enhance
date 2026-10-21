#!/usr/bin/env python3
"""Two-phase diagnosis in one run, so one observation settles it.

Phase 1 (content)  - the frame itself alternates red / green every few seconds, with
                     the kernel held at its identity setting. If the picture never
                     changes here, the display is not being updated at all.
Phase 2 (config)   - the frame is fixed and only the preset changes, pass <-> binarize.
                     If phase 1 changed the picture but phase 2 does not, the video
                     link is live and the kernel is ignoring its configuration.

    sudo python3 -u hdmi_two_phase.py
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
    ap.add_argument("--hold", type=float, default=6.0)
    ap.add_argument("--rounds", type=int, default=5)
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

    hl.write_preset(cfg, "pass")
    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}, kernel at 'pass'", flush=True)

    def push(colour_or_image) -> float:
        frame = out.newframe()
        frame[:] = colour_or_image
        t0 = time.monotonic()
        out.writeframe(frame)
        return (time.monotonic() - t0) * 1000

    print("\n===== PHASE 1: frame content red <-> green =====", flush=True)
    for rnd in range(args.rounds):
        for bgr, name in (((0, 0, 255), "RED"), ((0, 255, 0), "GREEN")):
            ms = push(bgr)
            print(f"[{time.strftime('%H:%M:%S')}] phase1 {name:<5} "
                  f"writeframe {ms:.1f} ms", flush=True)
            time.sleep(args.hold)

    print("\n===== PHASE 2: fixed image, preset pass <-> binarize =====", flush=True)
    image = test_image(width, height)
    push(image)
    print(f"[{time.strftime('%H:%M:%S')}] test image pushed once", flush=True)
    for rnd in range(args.rounds):
        for name in ("pass", "binarize"):
            lo, hi = hl.write_preset(cfg, name)
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] phase2 {name:<9} "
                  f"lo=0x{lo:08x} hi=0x{hi:08x} latency {n}", flush=True)
            time.sleep(args.hold)

    print("\ndone", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
