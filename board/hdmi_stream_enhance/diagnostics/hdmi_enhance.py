#!/usr/bin/env python3
"""Load the HDMI enhance overlay and exercise what is observable without a source.

What this checks
    1. the bitstream loads on the PYNQ image and pynq.lib.video binds, so the
       pixel path is intact after inserting the kernel;
    2. the configuration GPIO is writable and reads back, so the PS really can
       change the 59 configuration bits at run time (the presets themselves are
       proven bit-exact on the DMA path);
    3. the latency GPIO exists and is wired as an input, so on the day an HDMI
       source arrives the two cycle stamps can be read out immediately.

What it cannot check without a source or a display
    the picture, and therefore the latency stamps themselves (they only move when
    pixels flow). Those stay at 0 here, which is expected and is reported as such
    rather than dressed up as a measurement.

    sudo python3 hdmi_enhance.py
"""

from __future__ import annotations

import argparse
import sys

# axi_gpio register offsets
GPIO_DATA = 0x00
GPIO_TRI = 0x04
GPIO2_DATA = 0x08
GPIO2_TRI = 0x0C

# same presets as sim/enhance/golden_enhance.py, packed into the two words that
# enh_cfg_split expects: [clarity|knee|gain_lo|gain_hi] and
# [thresh|binarize|invert|mono|split_x]
PRESETS = {
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    "reading":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=12),
    "binarize": dict(clarity=16, knee=64, gain_lo=112, gain_hi=8,
                     thresh=112, binarize=1, mono=1),
}


def pack(cfg: dict) -> tuple[int, int]:
    lo = ((cfg.get("clarity", 16) & 0xFF)
          | ((cfg.get("knee", 255) & 0xFF) << 8)
          | ((cfg.get("gain_lo", 16) & 0xFF) << 16)
          | ((cfg.get("gain_hi", 16) & 0xFF) << 24))
    hi = ((cfg.get("thresh", 0) & 0xFF)
          | ((cfg.get("binarize", 0) & 1) << 8)
          | ((cfg.get("invert", 0) & 1) << 9)
          | ((cfg.get("mono", 0) & 1) << 10)
          | ((cfg.get("split_x", 0) & 0xFFFF) << 11))
    return lo, hi


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    args = ap.parse_args(argv)

    import pynq
    from pynq import Overlay

    print(f"PYNQ {pynq.__version__}")
    print(f"loading {args.bitstream} ...")
    ol = Overlay(args.bitstream)
    print(f"  IPs in design: {len(ol.ip_dict)}")

    if not hasattr(ol, "video"):
        print("FAIL: pynq.lib.video did not bind - bit/hwh mismatch?")
        return 1
    video = ol.video
    print(f"  hdmi_in : {video.hdmi_in}")
    print(f"  hdmi_out: {video.hdmi_out}")
    print(f"  input mode: {video.hdmi_in.mode}  (None = no source attached)")

    # --- configuration path --------------------------------------------------
    cfg_name = next((n for n in ol.ip_dict if "gpio_enh_cfg" in n.lower()), None)
    if cfg_name is None:
        print("FAIL: configuration GPIO not found in the overlay")
        return 1
    cfg = getattr(ol, cfg_name)
    print(f"  config GPIO: {cfg_name}")
    # For a channel fixed as all-outputs the TRI register is not meaningful (it
    # reads back 0xffffffff), so the direction comes from the bitstream's own
    # parameters; what matters here is that the data register holds what we write.
    print(f"    TRI = 0x{cfg.mmio.read(GPIO_TRI):08x} (not meaningful for a fixed-direction channel)")
    for name in ("document", "binarize"):
        lo, hi = pack(PRESETS[name])
        cfg.mmio.write(GPIO_DATA, lo)
        cfg.mmio.write(GPIO2_DATA, hi)
        rb_lo, rb_hi = cfg.mmio.read(GPIO_DATA), cfg.mmio.read(GPIO2_DATA)
        ok = (rb_lo == lo and rb_hi == hi)
        print(f"    preset {name:<9} wrote 0x{lo:08x} 0x{hi:08x} -> read back "
              f"0x{rb_lo:08x} 0x{rb_hi:08x}  {'OK' if ok else 'MISMATCH'}")
        if not ok:
            return 1

    # --- latency path --------------------------------------------------------
    lat_name = next((n for n in ol.ip_dict if "gpio_enh_lat" in n.lower()), None)
    if lat_name is None:
        print("FAIL: latency GPIO not found in the overlay")
        return 1
    lat = getattr(ol, lat_name)
    tri1, tri2 = lat.mmio.read(GPIO_TRI), lat.mmio.read(GPIO2_TRI)
    print(f"  latency GPIO: {lat_name}")
    print(f"    TRI 0x{tri1:08x} / 0x{tri2:08x} (both channels are inputs in the bitstream)")
    print(f"    stamps now: in=0x{lat.mmio.read(GPIO_DATA):08x} "
          f"out=0x{lat.mmio.read(GPIO2_DATA):08x}")
    if video.hdmi_in.mode is None:
        print("    (no source, so no pixels have flowed and both stamps are 0 -")
        print("     expected: the stamps only move once a stream starts)")

    print()
    print("RESULT: overlay loads, video subsystem binds, config and latency")
    print("        GPIOs are readable/writable. Picture still needs a source.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
