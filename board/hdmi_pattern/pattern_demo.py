#!/usr/bin/env python3
"""Internal-pattern demo: no HDMI source needed, the board generates the picture.

Why this exists
    HDMI IN negotiates EDID and HPD correctly on this board (Windows shows a
    second monitor) but never locks onto the laptop's TMDS stream. Rather than
    block the demonstration on that, this overlay feeds the kernel from an
    in-FPGA pattern generator:

        vpg_0 -> stamp_in -> enhance -> stamp_out -> HDMI OUT -> capture card

    So the capture card shows the pattern being enhanced in real time, and the
    preset switches are visible. It also isolates the output side: a picture here
    means HDMI OUT and the capture chain are good, and the only open question is
    the input path.

    The picture is *not* camera input and the documentation says so; the honest
    claim is "the pipeline runs on a synthetic source at 720p60".

    sudo python3 pattern_demo.py --preset document
    sudo python3 pattern_demo.py --cycle 4
"""

from __future__ import annotations

import argparse
import time

# same packing as hdmi_live.py / enh_cfg_split
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

GPIO_DATA, GPIO2_DATA = 0x00, 0x08


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


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_pattern.bit")
    ap.add_argument("--preset", default="document", choices=sorted(PRESETS))
    ap.add_argument("--cycle", type=float, default=0.0,
                    help="seconds per preset; 0 = stay on --preset")
    ap.add_argument("--clock-mhz", type=float, default=142.857)
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args(argv)

    if args.list:
        for k, v in PRESETS.items():
            print(f"  {k:<9} {v}")
        return 0

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}")
    ol = Overlay(args.bitstream)
    video = ol.video
    cfg = find(ol, "gpio_enh_cfg")
    lat = find(ol, "gpio_enh_lat")
    if cfg is None or lat is None:
        print("FAIL: config/latency GPIO missing")
        return 1

    # The output timing generator has to be programmed: without an input stream
    # PYNQ cannot infer the mode, so we tell it 720p60.
    mode = VideoMode(1280, 720, 24, 60)
    video.hdmi_out.configure(mode)
    print(f"hdmi_out configured: {mode.width}x{mode.height} @{mode.fps}")
    print("the capture card should now show colour bars with a white block")

    order = [args.preset] if args.cycle <= 0 else [
        "pass", "clarity", "document", "night", "invert", "binarize", "split"]
    try:
        while True:
            for name in order:
                lo, hi = pack(PRESETS[name])
                cfg.mmio.write(GPIO_DATA, lo)
                cfg.mmio.write(GPIO2_DATA, hi)
                a, b = lat.mmio.read(GPIO_DATA), lat.mmio.read(GPIO2_DATA)
                stamp = time.strftime("%H:%M:%S")
                if a == 0 and b == 0:
                    lat_txt = "no stamps yet (is the output stream running?)"
                else:
                    n = (b - a) & 0xFFFFFFFF
                    lat_txt = (f"{n} pixel clocks (~{n / args.clock_mhz:.3f} us "
                               f"at {args.clock_mhz} MHz)")
                print(f"[{stamp}] preset {name:<9} latency {lat_txt}")
                if args.cycle > 0:
                    time.sleep(args.cycle)
            if args.cycle <= 0:
                raise KeyboardInterrupt
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
