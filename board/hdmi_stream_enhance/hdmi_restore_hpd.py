#!/usr/bin/env python3
"""Restore HPD so Windows shows the board as display 2 again.

Every bitstream load resets the HDMI-input HPD GPIO to 0, and while it is 0 Windows
behaves as if no monitor is attached - the second display disappears and the laptop
stops sending video at all. This script loads an overlay, raises HPD, and exits; the
register keeps its value after the process ends, so the display comes back and stays.

    sudo python3 hdmi_restore_hpd.py
"""

from __future__ import annotations

import argparse

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    args = ap.parse_args(argv)

    from pynq import Overlay

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is None:
        print("this overlay has no gpio_hdmiin; nothing to restore")
        return 2
    before = hpd.mmio.read(0x00)
    hpd.mmio.write(0x00, 0x1)
    print(f"hdmi_in HPD: 0x{before:08x} -> 0x{hpd.mmio.read(0x00):08x}")
    print("display 2 should reappear in Windows within a few seconds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
