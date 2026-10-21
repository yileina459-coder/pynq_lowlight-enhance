#!/usr/bin/env python3
"""Same presets, but with a low-frequency test image.

Why
    The presets that flicker on the capture card all render as 1-pixel-wide vertical
    stripes; the preset that is stable does not. Two explanations fit that pattern:

      * the board is genuinely unstable at those settings
      * the capture path (card sampling + OBS scaling 640x480 into a 16:9 canvas) aliases
        high-frequency content, which shimmers on screen

    Board-side numbers argue against the first: writeframe stays at 6.4-6.6 ms and the
    pipeline latency stays at 21 pixel clocks across every preset.

    So this script pushes a *smooth* image - a gradient plus large blocks, no one-pixel
    lines and no text bars - through the very same presets. If the flicker disappears
    with low-frequency content, it is an aliasing artefact of the capture/display chain,
    not the design.

    sudo python3 -u hdmi_smooth_demo.py --cycle 12
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl


def smooth_image(width: int, height: int) -> np.ndarray:
    img = np.zeros((height, width, 3), dtype=np.uint8)

    # Vertical gradient, 8-pixel-wide horizontal bands: low frequency on purpose.
    for y in range(0, height, 8):
        value = int(20 + (215 * y) / height)
        img[y:y + 8, :, :] = value

    # A few large blocks so the tone curve and binarisation are still obvious.
    img[40:200, 40:300, :] = 96
    img[40:200, 340:600, :] = 170
    img[260:380, 40:600, :] = 128

    # Soft colour areas (4:4:4 but smooth), for the mono/invert presets.
    img[10:70, 10:150, 2] = 210
    img[10:70, 170:310, 1] = 210
    img[10:70, 330:470, 0] = 210
    return img


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--cycle", type=float, default=12.0)
    ap.add_argument("--total", type=float, default=200.0)
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

    image = smooth_image(width, height)
    print("smooth test image pushed (no 1-pixel detail)", flush=True)

    presets = ["pass", "document", "night", "binarize", "split"]
    started = time.monotonic()
    index = 0
    next_switch = starts = 0.0

    hl.write_preset(cfg, presets[0])
    print(f"[{time.strftime('%H:%M:%S')}] preset {presets[0]}", flush=True)

    while time.monotonic() - started < args.total:
        frame = out.newframe()
        frame[:] = image
        out.writeframe(frame)

        elapsed = time.monotonic() - started
        if elapsed >= next_switch:
            next_switch = elapsed + args.cycle
            index = (index + 1) % len(presets)
            hl.write_preset(cfg, presets[index])
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] preset {presets[index]:<9} "
                  f"latency {n}", flush=True)

        time.sleep(1.0)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
