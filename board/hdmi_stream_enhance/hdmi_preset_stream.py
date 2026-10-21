#!/usr/bin/env python3
"""Keep frames flowing while the preset changes.

The previous A/B test pushed the image once and then only changed the preset. If the
VDMA only produces a frame when writeframe() is called, the pipeline had nothing new
to process and the screen would legitimately look unchanged - a test artefact, not a
hardware result. This version pushes a frame every couple of seconds (so data is
always flowing) and toggles the preset every ``--preset-hold`` seconds, which makes any
difference attributable to the configuration alone.

    sudo python3 -u hdmi_preset_stream.py --frame 2 --preset-hold 12 --total 96
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
    ap.add_argument("--frame", type=float, default=2.0, help="seconds between frames")
    ap.add_argument("--preset-hold", type=float, default=12.0)
    ap.add_argument("--total", type=float, default=96.0)
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
    names = [args.a, args.b]
    idx = 0
    last_preset = 0.0
    started = time.monotonic()
    frames = 0

    hl.write_preset(cfg, names[0])
    print(f"[{time.strftime('%H:%M:%S')}] preset {names[0]}", flush=True)

    while time.monotonic() - started < args.total:
        frame = out.newframe()
        frame[:] = image
        t0 = time.monotonic()
        out.writeframe(frame)
        ms = (time.monotonic() - t0) * 1000
        frames += 1

        elapsed = time.monotonic() - started
        if elapsed - last_preset >= args.preset_hold:
            last_preset = elapsed
            idx = (idx + 1) % len(names)
            lo, hi = hl.write_preset(cfg, names[idx])
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] preset {names[idx]:<9} "
                  f"lo=0x{lo:08x} hi=0x{hi:08x} latency {n} "
                  f"(frame {frames}, {ms:.1f} ms)", flush=True)

        time.sleep(args.frame)

    print(f"done, {frames} frames pushed", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
