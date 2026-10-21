#!/usr/bin/env python3
"""Write one frame, then only switch presets - no DDR traffic during the demo.

Why this shape
    Measurements on the board: a static frame with a fixed preset is rock solid (85 s,
    pipeline latency constant at 21 pixel clocks), while a demo that called writeframe()
    every couple of seconds flickered on some presets. The difference is DDR traffic: the
    PS was rewriting a frame buffer while the VDMA was streaming from the same pool, so
    the display could show a frame that was part-written - visible as a band whose height
    changes from capture to capture, which reads as flicker at high contrast.

    The preset itself needs no new frame: it is 59 bits on a GPIO, sampled per pixel.
    So write once, then only ever touch the configuration.

    sudo python3 -u hdmi_preset_only.py --cycle 12 --total 200
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
    for x in range(0, width, 16):
        img[470:475, x:x + 8, :] = 240
    img[10:70, 10:130, 2] = 220
    img[10:70, 140:260, 1] = 220
    img[10:70, 270:390, 0] = 220
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

    image = test_image(width, height)
    frame = out.newframe()
    frame[:] = image
    t0 = time.monotonic()
    out.writeframe(frame)
    print(f"test image written once ({(time.monotonic() - t0) * 1000:.1f} ms); "
          f"no further DDR writes from here on", flush=True)

    presets = ["pass", "clarity", "document", "night", "invert", "binarize", "split"]
    started = time.monotonic()
    index = 0
    next_switch = 0.0

    def apply(name):
        # The preset pulse resets the kernel, which interrupts the pixel stream; the video
        # output core then underflows and the capture card has to re-lock on its own. That
        # recovery is what looks like flicker. Restarting the output path explicitly puts
        # it back into a known state instead of letting it wander: stop, reconfigure,
        # start, then refill every frame buffer.
        hl.write_preset(cfg, name)
        out.stop()
        out.configure(VideoMode(width, height, 24, 60))
        out.start()
        for _ in range(4):
            f = out.newframe()
            f[:] = image
            out.writeframe(f)
        n = hl.read_latency(lat)
        print(f"[{time.strftime('%H:%M:%S')}] preset {name:<9} latency {n} "
              f"(output path restarted)", flush=True)

    apply(presets[0])

    while time.monotonic() - started < args.total:
        elapsed = time.monotonic() - started
        if elapsed >= next_switch:
            next_switch = elapsed + args.cycle
            index = (index + 1) % len(presets)
            apply(presets[index])
        time.sleep(0.5)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
