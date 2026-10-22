#!/usr/bin/env python3
"""Static-frame output test that explicitly puts the kernel in a known state.

Why this exists
    ``hdmi_solid.py`` never calls ``write_preset``, so every configuration input stays at
    its power-up value of 0. With clarity 0, knee 0 and both gains 0 the kernel's tone
    curve collapses and the output is black; and if the reset bridge's request bit happens
    to come up set, the kernel never leaves reset at all and no TMDS is produced. Either
    way the test says nothing about the output path.

    This version writes a preset first (which also clears the bridge's request bit), then
    pushes one static frame and holds it, printing a heartbeat so a dead process and a
    dead signal are distinguishable in the log.

    sudo python3 -u hdmi_static_frame.py --preset pass --colour 128,128,128 --hold 60
"""

from __future__ import annotations

import argparse
import time

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--preset", default="pass", choices=sorted(hl.PRESETS))
    ap.add_argument("--colour", default="128,128,128")
    ap.add_argument("--hold", type=float, default=60.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))
    bgr = tuple(int(v) for v in args.colour.split(","))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video
    out = video.hdmi_out

    # Both HPD GPIOs come up tri-stated; the sink has to see HPD asserted or a capture
    # dongle keeps its receiver off and shows its own test pattern.
    hl.raise_input_hpd(ol)
    hl.raise_output_hpd(ol)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    before = (cfg.mmio.read(0x00), cfg.mmio.read(0x08))
    print(f"config GPIO before any write: lo=0x{before[0]:08x} hi=0x{before[1]:08x} "
          f"(hi bit31 = the reset request)", flush=True)

    lo, hi = hl.write_preset(cfg, args.preset)
    after = (cfg.mmio.read(0x00), cfg.mmio.read(0x08))
    print(f"preset {args.preset}: wrote lo=0x{lo:08x} hi=0x{hi:08x}, "
          f"readback lo=0x{after[0]:08x} hi=0x{after[1]:08x}", flush=True)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    frame = out.newframe()
    frame[:] = bgr
    t0 = time.monotonic()
    out.writeframe(frame)
    print(f"solid frame BGR={bgr} written, writeframe "
          f"{(time.monotonic() - t0) * 1000:.1f} ms", flush=True)

    held = 0.0
    while held < args.hold:
        time.sleep(5.0)
        held += 5.0
        n = hl.read_latency(lat)
        print(f"  holding {held:.0f}/{args.hold:.0f}s, latency {n}", flush=True)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
