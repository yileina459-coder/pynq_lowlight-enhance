#!/usr/bin/env python3
"""Write the enhancement configuration directly, bypassing the preset table.

Why
    The presets bundle clarity together with the tone curve, so a test cannot tell which stage
    causes an artefact. This writes the four tone values straight into the configuration GPIO, so
    clarity and gain can be varied one at a time while the demo keeps streaming.

Why raw MMIO and not Overlay()
    Calling Overlay() from a second process re-downloads the bitstream when PYNQ thinks the loaded
    one differs, which reconfigures the PL, kills the VDMA and takes the picture down with
    "RuntimeError: DMA channel not started" in the demo. That is exactly what happened the first
    time this probe was written. Only pynq.MMIO is used here: it touches four registers and cannot
    disturb anything else.

    sudo python3 probe_cfg.py --gain-lo 56      # gain only, no local contrast
    sudo python3 probe_cfg.py --clarity 28      # local contrast only, unity gain

    Addresses come from the .hwh: gpio_enh_cfg at 0x40010000, channels at +0x00 (data) and
    +0x04 (direction), second channel at +0x08 / +0x0C.
"""

from __future__ import annotations

import argparse
import sys

from pynq import MMIO

CFG_BASE = 0x40010000
GPIO_DATA = 0x00
GPIO2_DATA = 0x08


def pack(clarity: int, knee: int, gain_lo: int, gain_hi: int) -> tuple[int, int]:
    lo = ((clarity & 0xFF)
          | ((knee & 0xFF) << 8)
          | ((gain_lo & 0xFF) << 16)
          | ((gain_hi & 0xFF) << 24))
    return lo & 0xFFFFFFFF, 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clarity", type=int, default=16, help="16 = identity")
    ap.add_argument("--knee", type=int, default=255)
    ap.add_argument("--gain-lo", type=int, default=16, help="16 = identity, 56 = 3.5x")
    ap.add_argument("--gain-hi", type=int, default=16)
    ap.add_argument("--read", action="store_true", help="just print the current registers")
    args = ap.parse_args(argv)

    dev = MMIO(CFG_BASE, 0x1000)
    if args.read:
        print(f"data  = 0x{dev.read(GPIO_DATA):08x}")
        print(f"data2 = 0x{dev.read(GPIO2_DATA):08x}")
        return 0

    lo, hi_extra = pack(args.clarity, args.knee, args.gain_lo, args.gain_hi)
    # keep the flag bits (binarize/invert/mono/split_x) and the SOF enable from the live word
    hi = dev.read(GPIO2_DATA) & 0xFFFFFFFF
    hi = (hi & 0xFFFFFF00) | (hi & 0xFF)     # flags untouched
    dev.write(GPIO_DATA, lo)
    dev.write(GPIO2_DATA, hi | hi_extra)

    print(f"clarity={args.clarity} knee={args.knee} "
          f"gain_lo={args.gain_lo} ({args.gain_lo / 16:.2f}x) gain_hi={args.gain_hi}")
    print(f"wrote lo=0x{lo:08x} hi=0x{hi:08x}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
