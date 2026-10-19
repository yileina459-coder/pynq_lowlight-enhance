#!/usr/bin/env python3
"""Live demo on real HDMI: apply presets and read the measured latency.

For the day the capture card is connected:

    HDMI source -> PYNQ HDMI IN -> enhance -> PYNQ HDMI OUT -> capture card -> PC

Nothing here reads pixels back: the pipeline deliberately bypasses the frame
buffer, so what you look at is the capture card's window on your PC. What this
script does is drive the kernel and report what the hardware says.

    # one preset, watch it on the capture card
    sudo python3 hdmi_live.py --preset document

    # cycle through presets every 4 s (nice for the demo video)
    sudo python3 hdmi_live.py --cycle 4

    # list the presets and exit
    python3 hdmi_live.py --list

Everything it prints comes from the hardware: the input mode from dvi2rgb, the
two cycle stamps from axis_cycle_stamp. If there is no source, it says so and
keeps waiting instead of pretending.
"""

from __future__ import annotations

import argparse
import sys
import time

# The 59 configuration bits, packed the way enh_cfg_split expects.
PRESETS = {
    "pass":     dict(clarity=16, knee=255, gain_lo=16, gain_hi=16),
    "clarity":  dict(clarity=28, knee=255, gain_lo=16, gain_hi=16),
    "reading":  dict(clarity=24, knee=48, gain_lo=88, gain_hi=14),
    "document": dict(clarity=20, knee=192, gain_lo=64, gain_hi=12),
    "night":    dict(clarity=30, knee=36, gain_lo=120, gain_hi=10),
    "invert":   dict(clarity=24, knee=48, gain_lo=88, gain_hi=14, invert=1, mono=1),
    "binarize": dict(clarity=16, knee=64, gain_lo=112, gain_hi=8,
                     thresh=112, binarize=1, mono=1),
    "split":    dict(clarity=28, knee=90, gain_lo=40, gain_hi=12, split_x=320),
}

GPIO_DATA, GPIO_TRI, GPIO2_DATA, GPIO2_TRI = 0x00, 0x04, 0x08, 0x0C


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


def find(ol, fragment: str):
    for name in ol.ip_dict:
        if fragment in name.lower():
            dev = getattr(ol, name, None)
            if dev is not None and hasattr(dev, "mmio"):
                return dev
    return None


def write_preset(cfg_ip, name: str) -> tuple[int, int]:
    lo, hi = pack(PRESETS[name])
    cfg_ip.mmio.write(GPIO_DATA, lo)
    cfg_ip.mmio.write(GPIO2_DATA, hi)
    rb = (cfg_ip.mmio.read(GPIO_DATA), cfg_ip.mmio.read(GPIO2_DATA))
    if rb != (lo, hi):
        print(f"  WARNING: config readback {rb[0]:#010x},{rb[1]:#010x} "
              f"!= written {lo:#010x},{hi:#010x}")
    return lo, hi


def read_latency(lat_ip) -> tuple[int, int] | None:
    a, b = lat_ip.mmio.read(GPIO_DATA), lat_ip.mmio.read(GPIO2_DATA)
    if a == 0 and b == 0:
        return None
    return (b - a) & 0xFFFFFFFF


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--preset", default="document", choices=sorted(PRESETS))
    ap.add_argument("--cycle", type=float, default=0.0,
                    help="seconds per preset; 0 = stay on --preset")
    ap.add_argument("--order", default="pass,clarity,document,night,invert,binarize,split",
                    help="preset order used by --cycle")
    ap.add_argument("--clock-mhz", type=float, default=142.857,
                    help="pixel-domain clock of the kernel (clk_142M)")
    ap.add_argument("--seconds", type=float, default=0.0,
                    help="stop after this many seconds (0 = run until Ctrl-C)")
    ap.add_argument("--wait-source", type=float, default=20.0,
                    help="how long to wait for an HDMI input mode before warning")
    ap.add_argument("--list", action="store_true", help="print presets and exit")
    args = ap.parse_args(argv)

    if args.list:
        for name, cfg in PRESETS.items():
            print(f"  {name:<9} {cfg}")
        return 0

    from pynq import Overlay

    print(f"loading {args.bitstream} ...")
    ol = Overlay(args.bitstream)
    if not hasattr(ol, "video"):
        print("FAIL: pynq.lib.video did not bind")
        return 1
    video = ol.video

    cfg_ip = find(ol, "gpio_enh_cfg")
    lat_ip = find(ol, "gpio_enh_lat")
    if cfg_ip is None or lat_ip is None:
        print("FAIL: configuration or latency GPIO missing from the overlay")
        return 1

    # Wait for the source, but do not lie if it never arrives.
    deadline = time.monotonic() + args.wait_source
    mode = video.hdmi_in.mode
    while mode is None and time.monotonic() < deadline:
        time.sleep(0.5)
        mode = video.hdmi_in.mode
    if mode is None:
        print("no HDMI input detected yet - check that the source is powered and")
        print("set to a mode the PYNQ-Z2 can lock (1280x720 is the safe one).")
        print("continuing anyway; the picture will appear when the source locks.")
    else:
        print(f"input detected: {mode.width}x{mode.height} @{mode.frame_rate} Hz")

    order = [p.strip() for p in args.order.split(",") if p.strip() in PRESETS]
    start = time.monotonic()
    preset = args.preset
    try:
        while True:
            for name in (order if args.cycle > 0 else [preset]):
                lo, hi = write_preset(cfg_ip, name)
                stamp = time.strftime("%H:%M:%S")
                print(f"[{stamp}] preset {name:<9} cfg=0x{lo:08x} 0x{hi:08x}")
                lat = read_latency(lat_ip)
                if lat is None:
                    print("           latency: not measured yet (no pixels have "
                          "passed since the PL was configured)")
                else:
                    print(f"           latency: {lat} pixel clocks "
                          f"(~{lat / args.clock_mhz:.3f} us at {args.clock_mhz} MHz)")
                if args.cycle > 0:
                    time.sleep(args.cycle)
                if args.seconds and (time.monotonic() - start) > args.seconds:
                    raise KeyboardInterrupt
            if args.cycle <= 0:
                # stay on the single preset and report the stamps once a second
                while True:
                    time.sleep(1.0)
                    lat = read_latency(lat_ip)
                    if lat is not None:
                        print(f"           latency: {lat} pixel clocks "
                              f"(~{lat / args.clock_mhz:.3f} us)")
                    if args.seconds and (time.monotonic() - start) > args.seconds:
                        raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
