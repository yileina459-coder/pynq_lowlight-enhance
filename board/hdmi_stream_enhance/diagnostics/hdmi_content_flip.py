#!/usr/bin/env python3
"""Is the HDMI output live? Flip the frame content between two solid colours.

This separates two explanations that look identical on a monitor:

  * the link is frozen / the display shows a stale frame  -> the colour never changes
  * the link is live but the kernel ignores its config    -> the colour flips, the
                                                             preset-based tests just
                                                             were not visible

Content is written from the PS, so no kernel configuration is involved at all.

    sudo python3 -u hdmi_content_flip.py --hold 2 --rounds 10
"""

from __future__ import annotations

import argparse
import time

import numpy as np

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="640x480")
    ap.add_argument("--hold", type=float, default=2.0)
    ap.add_argument("--rounds", type=int, default=10)
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

    # Put the kernel in pass-through so this test measures the display, not the filter:
    # clarity 16 / knee 255 / gain 16,16 is exactly the identity setting.
    cfg = hl.find(ol, "gpio_enh_cfg")
    if cfg is not None:
        hl.write_preset(cfg, "pass")
        print("kernel set to 'pass' (identity)", flush=True)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    colours = [((0, 0, 255), "RED"), ((0, 255, 0), "GREEN")]     # BGR order
    for rnd in range(args.rounds):
        for bgr, name in colours:
            frame = out.newframe()
            frame[:] = bgr
            t0 = time.monotonic()
            out.writeframe(frame)
            elapsed = time.monotonic() - t0
            print(f"[{time.strftime('%H:%M:%S')}] wrote {name:<5} "
                  f"writeframe {elapsed * 1000:.1f} ms", flush=True)
            time.sleep(args.hold)

    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
