#!/usr/bin/env python3
"""Read the dynamic clock generator's registers at each output mode.

Why this is the decisive measurement
    The official design ties the clock generator's LOCKED output to rgb2dvi's
    aRst_n (active low):

        connect_bd_net -net axi_dynclk_0_LOCKED_O \
            [get_bd_pins axi_dynclk/LOCKED_O] [get_bd_pins rgb2dvi_0/aRst_n]

    and drives rgb2dvi's 5x serial clock from axi_dynclk as well. So if the clock
    generator fails to lock at a given mode, rgb2dvi stays in reset and the HDMI
    output emits no TMDS at all - which is exactly "the capture card shows its
    no-signal pattern".

    The capture card cannot tell us which of the two is at fault, but this can: the
    generator's STATUS register has a locked bit, and it either reads 1 or 0.

    sudo python3 -u hdmi_clk_probe.py
"""

from __future__ import annotations

import argparse
import time


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--modes", default="1280x720")
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video

    clk_name = [n for n in ol.ip_dict if "dynclk" in n.lower()]
    if not clk_name:
        print("no axi_dynclk in this overlay")
        return 2
    clk = getattr(ol, clk_name[0])
    print(f"axi_dynclk: {clk_name[0]} @ 0x{ol.ip_dict[clk_name[0]]['phys_addr']:08x}",
          flush=True)

    for spec in args.modes.split(","):
        w, h = (int(v) for v in spec.lower().split("x"))
        print(f"\n=== {w}x{h} ===", flush=True)
        try:
            video.hdmi_out.configure(VideoMode(w, h, 24, 60))
            video.hdmi_out.start()
        except Exception as exc:                          # noqa: BLE001
            print(f"  configure failed: {type(exc).__name__}: {exc}", flush=True)
            continue
        time.sleep(2.0)
        regs = {}
        for off in range(0x00, 0x20, 4):
            try:
                regs[off] = clk.mmio.read(off)
            except Exception as exc:                      # noqa: BLE001
                print(f"  read 0x{off:02x} failed: {exc}", flush=True)
                break
        for off, value in regs.items():
            print(f"  0x{off:02x} = 0x{value:08x}", flush=True)
        status = regs.get(0x00)
        if status is not None:
            locked = status & 0x1
            print(f"  STATUS bit0 (locked) = {locked}  -> "
                  f"{'CLOCK LOCKED, rgb2dvi out of reset' if locked else 'NOT LOCKED, rgb2dvi held in reset'}",
                  flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
