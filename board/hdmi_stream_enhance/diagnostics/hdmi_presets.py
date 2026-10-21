#!/usr/bin/env python3
"""Cycle enhancement presets on the live HDMI passthrough.

Deliberately skips input-mode detection. Reading the input mode needs the PYNQ
capture library to lock on the input VTC, which is slow and unreliable right after a
bitstream load (HPD resets, the source re-enumerates, and the library can time out
even while video is already flowing through the kernel). For a passthrough demo the
mode only has to be *set* on the output - it does not have to be read - so this
script takes the mode as an argument.

    sudo python3 -u hdmi_presets.py                      # 1280x720, cycle every 5 s
    sudo python3 -u hdmi_presets.py --mode 1280x720 --cycle 0 --preset document
"""

from __future__ import annotations

import argparse
import time

import hdmi_live as hl

EDID_FPS = {  # modes supported by the 720p clock range in this overlay
    (1280, 720): 60,
}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="1280x720", help="WxH (this overlay is built for 720p60)")
    ap.add_argument("--preset", default="pass", choices=sorted(hl.PRESETS))
    ap.add_argument("--cycle", type=float, default=5.0, help="seconds per preset, 0 = hold")
    ap.add_argument("--rounds", type=int, default=0, help="0 = forever")
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))
    if (width, height) not in EDID_FPS:
        print(f"unsupported mode {args.mode}; the driver accepts "
              f"{sorted(EDID_FPS)}")
        return 2

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None and hpd.mmio.read(0x00) & 0x1 == 0:
        hpd.mmio.write(0x00, 0x1)
        print("HPD raised", flush=True)

    video.hdmi_out.configure(VideoMode(width, height, 24, EDID_FPS[(width, height)]))
    video.hdmi_out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    order = ["pass", "clarity", "document", "night", "invert", "binarize", "split"]
    rnd = 0
    try:
        while True:
            for name in order:
                hl.write_preset(cfg, name)
                n = hl.read_latency(lat)
                txt = ("not measured" if n is None
                       else f"{n} pixel clocks ({n / 74.25:.3f} us at 720p60)")
                print(f"[{time.strftime('%H:%M:%S')}] round {rnd} preset {name:<9} {txt}",
                      flush=True)
                if args.cycle <= 0:
                    print("holding this preset; Ctrl-C to stop", flush=True)
                    while True:
                        time.sleep(1.0)
                time.sleep(args.cycle)
            rnd += 1
            if args.rounds and rnd >= args.rounds:
                break
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
