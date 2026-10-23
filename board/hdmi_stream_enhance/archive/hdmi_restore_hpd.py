#!/usr/bin/env python3
"""Assert both hot-plug lines so the PC sees the board again.

Every bitstream load resets the HPD GPIOs, and they also power up with both channels
tri-stated - writing the data register alone therefore does nothing electrically, because the
pin is still an input. Windows then behaves as if no monitor is attached: display 2 disappears
and the laptop stops sending video, and a USB capture dongle keeps its receiver disabled and
shows its own test pattern instead of the board's picture.

This script loads the overlay, switches both HPD pins to outputs and drives them high. The
registers keep their value after the process exits, so the display and the capture card come
back and stay back.

    sudo python3 hdmi_restore_hpd.py
"""

from __future__ import annotations

import argparse

import hdmi_live as hl


def describe(ol, fragment: str) -> str:
    dev = hl.find(ol, fragment)
    if dev is None:
        return f"{fragment}: not present"
    data, direction = dev.mmio.read(0x00), dev.mmio.read(0x04)
    mode = "driven" if (direction & 0x1) == 0 else "tri-stated (input)"
    return f"{fragment}: data=0x{data:08x} dir=0x{direction:08x} -> {mode}"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    args = ap.parse_args(argv)

    from pynq import Overlay

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)

    print("before:", flush=True)
    print("  " + describe(ol, "gpio_hdmiin"), flush=True)
    print("  " + describe(ol, "hpd_video"), flush=True)

    did_in = hl.raise_input_hpd(ol)
    did_out = hl.raise_output_hpd(ol)

    print("after:", flush=True)
    print("  " + describe(ol, "gpio_hdmiin"), flush=True)
    print("  " + describe(ol, "hpd_video"), flush=True)

    if not (did_in or did_out):
        print("this overlay has no HPD GPIOs; nothing to restore")
        return 2

    print("both hot-plug lines asserted: display 2 and the capture card should come back "
          "within a few seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
