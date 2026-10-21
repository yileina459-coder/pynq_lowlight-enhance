#!/usr/bin/env python3
"""Set the preset BEFORE the kernel sees its first pixel.

Hypothesis under test
    The generated RTL uses the configuration ports directly in the datapath, but the
    kernel is a free-running ``while (1)`` pipeline. HLS is free to treat loop-invariant
    inputs as such and register them once when the pipeline starts, which would mean the
    kernel keeps the configuration that was present at start-up and ignores every later
    change. That matches every observation so far: content changes are visible (the
    stream is live), preset changes are not, and the picture looks exactly like the
    preset that was written first (``pass``).

    If the hypothesis holds, loading the overlay and writing a preset *before* any pixel
    arrives makes that preset take effect - so this script writes the preset first and
    only then pushes frames.

    sudo python3 -u hdmi_first_preset.py --preset binarize
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
    ap.add_argument("--preset", default="binarize", choices=sorted(hl.PRESETS))
    ap.add_argument("--total", type=float, default=60.0)
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

    # The whole point: configuration first, pixels afterwards.
    lo, hi = hl.write_preset(cfg, args.preset)
    print(f"preset {args.preset} written BEFORE any frame: "
          f"lo=0x{lo:08x} hi=0x{hi:08x}", flush=True)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    image = test_image(width, height)
    started = time.monotonic()
    frames = 0
    while time.monotonic() - started < args.total:
        frame = out.newframe()
        frame[:] = image
        out.writeframe(frame)
        frames += 1
        if frames % 5 == 0:
            n = hl.read_latency(lat)
            print(f"[{time.strftime('%H:%M:%S')}] frame {frames}, latency {n}",
                  flush=True)
        time.sleep(2.0)

    print(f"done, {frames} frames", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
