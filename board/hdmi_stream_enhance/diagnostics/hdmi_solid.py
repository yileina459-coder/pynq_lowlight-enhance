#!/usr/bin/env python3
"""Minimal, unambiguous output test: one solid colour, held.

Nothing else runs. If the capture card shows the colour, the whole output path of this
overlay works (VDMA -> kernel -> pixel_unpack -> v_axi4s_vid_out -> rgb2dvi) and any
remaining problem is in what we write. If it shows its no-signal pattern instead, the
overlay itself does not produce TMDS and the kernel insertion is what broke it.

    sudo python3 -u hdmi_solid.py --colour 0,200,0 --hold 60
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
    ap.add_argument("--colour", default="0,200,0", help="B,G,R values 0-255")
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
    print(f"hdmi_in + hdmi_out HPD asserted", flush=True)

    out.configure(VideoMode(width, height, 24, 60))
    out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    frame = out.newframe()
    frame[:] = bgr
    t0 = time.monotonic()
    out.writeframe(frame)
    elapsed = time.monotonic() - t0
    print(f"writeframe returned after {elapsed * 1000:.1f} ms "
          f"(the VDMA consumed a frame)", flush=True)
    print(f"the sink should now show a solid colour BGR={bgr}", flush=True)

    lat = hl.find(ol, "gpio_enh_lat")
    n = hl.read_latency(lat)
    print(f"pipeline latency: {'not measured' if n is None else str(n) + ' pixel clocks'}",
          flush=True)

    try:
        time.sleep(args.hold)
    except KeyboardInterrupt:
        pass
    print("done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
