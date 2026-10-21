#!/usr/bin/env python3
"""Cycle only the parameters the kernel reads live - no kernel reset at all.

Reasoning
    After the reset-gate fixes the picture appears on every preset, but some presets still
    flicker. Three things are now known to be innocent: the output path (a static frame is
    rock solid), DDR traffic (writing one frame per switch changed nothing) and OBS scaling
    (the capture source is 1:1 at 640x480 again).

    What is left is the reset itself. Every preset change pulses the kernel's reset, which
    empties its line buffers and breaks the pixel stream mid-frame; the video-out core then
    has to recover while the display keeps pulling.

    So this script removes the reset: it only switches presets whose effect comes from
    clarity / gain_lo / gain_hi, the three configuration inputs HLS leaves combinational
    (see docs/hdmi_status.md - knee, thresh, binarize, invert, mono and split_x are latched
    and only change after a reset). If the picture is then completely stable, the reset is
    the last remaining cause of the flicker, and moving those six parameters into a BRAM is
    the proper fix.

    sudo python3 -u hdmi_live_only.py --cycle 10
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl

# Presets that differ only in the live parameters.
LIVE_PRESETS = ["pass", "clarity", "document", "night"]


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


def write_live_preset(cfg, name: str) -> tuple[int, int]:
    """Write a preset WITHOUT the reset pulse (bit 31 stays clear)."""
    lo, hi = hl.pack(hl.PRESETS[name])
    cfg.mmio.write(hl.GPIO_DATA, lo)
    cfg.mmio.write(hl.GPIO2_DATA, hi)
    return cfg.mmio.read(hl.GPIO_DATA), cfg.mmio.read(hl.GPIO2_DATA)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--cycle", type=float, default=10.0)
    ap.add_argument("--total", type=float, default=160.0)
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

    # One reset at the very start so the latched parameters take their values, then never
    # again: this is what the proper fix will make unnecessary.
    hl.write_preset(cfg, "pass")
    print("kernel reset once at start; no further resets in this run", flush=True)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()

    image = test_image(width, height)

    # Fill EVERY buffer in the VDMA frame list. Writing once leaves the other buffers
    # holding the all-zero frame that start() queued, and since the VDMA cycles the whole
    # list the display alternates between the image and black - which reads as flicker.
    # Four writes cover a three-buffer list plus the one being displayed.
    for index in range(4):
        frame = out.newframe()
        frame[:] = image
        out.writeframe(frame)
    print("image written into 4 buffers (frame list filled)", flush=True)

    started = time.monotonic()
    index = 0
    next_switch = 0.0

    while time.monotonic() - started < args.total:
        elapsed = time.monotonic() - started
        if elapsed >= next_switch:
            next_switch = elapsed + args.cycle
            name = LIVE_PRESETS[index % len(LIVE_PRESETS)]
            index += 1
            rb = write_live_preset(cfg, name)
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] preset {name:<9} "
                  f"lo=0x{rb[0]:08x} hi=0x{rb[1]:08x} latency {n}", flush=True)
        time.sleep(0.5)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
