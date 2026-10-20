#!/usr/bin/env python3
"""Test the HDMI path after the input PLL range fix.

What changed and why it should matter
    dvi2rgb.vhd documents kClkRange as "MULT_F = kClkRange*5 (choose >=120MHz=1,
    >=60MHz=2, >=40MHz=3)". The stock PYNQ design used range 1 (>=120 MHz) while
    its EDID advertises 720p, whose TMDS clock is 74.25 MHz - the PLL would need
    MULT_F = 5, giving a 371 MHz VCO, below the MMCM minimum. That is consistent
    with everything observed: EDID and HPD negotiate, TMDS never locks, and the
    unmodified PYNQ bitstream fails the same way. The rebuilt overlay sets range 2
    (60-120 MHz).

What this script reports
    1. whether the input locks at all (the whole question)
    2. the output mode the driver applied
    3. the two cycle stamps, which move only if pixels flow through the kernel

    sudo python3 hdmi_after_fix.py
    sudo python3 hdmi_after_fix.py --cycle 4      # step presets, watch the picture
"""

from __future__ import annotations

import argparse
import time

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--preset", default="document", choices=sorted(hl.PRESETS))
    ap.add_argument("--cycle", type=float, default=0.0)
    ap.add_argument("--wait", type=float, default=25.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}")
    ol = Overlay(args.bitstream)
    video = ol.video

    out = video.hdmi_out
    out.configure(VideoMode(1280, 720, 24, 60))
    out.start()
    print("hdmi_out configured and started (1280x720)")

    # HPD must be asserted before the source will even read the EDID, and it is a
    # PL register that resets to 0 on every load - this is why the second display
    # only appears after hdmi_hpd_retry.ipynb.
    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        before = hpd.mmio.read(0x00)
        hpd.mmio.write(0x00, 0x1)
        print(f"HPD asserted (was 0x{before:08x}, now 0x{hpd.mmio.read(0x00):08x}); "
              f"Windows should now list the board as a display")
        time.sleep(1.0)
    else:
        print("warning: no gpio_hdmiin in this overlay, HPD not touched")

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    print("waiting for an HDMI input lock...", flush=True)
    mode = None
    deadline = time.monotonic() + args.wait
    started = time.monotonic()
    last_beat = 0.0
    while time.monotonic() < deadline:
        mode = video.hdmi_in.mode
        if mode is not None:
            break
        waited = time.monotonic() - started
        if waited - last_beat >= 10.0:
            last_beat = waited
            print(f"  ... {waited:5.0f}s, still no lock", flush=True)
        time.sleep(0.5)

    if mode is None:
        print("RESULT: still no input lock")
        print("  next: confirm the laptop is set to 1280x720 (or try 1920x1080,")
        print("  which also falls in the PLL's range) and that the cable is in HDMI IN")
        return 2

    print(f"RESULT: INPUT LOCKED -> {mode.width}x{mode.height} @{mode.frame_rate} Hz")

    order = [args.preset] if args.cycle <= 0 else [
        "pass", "clarity", "document", "night", "invert", "binarize", "split"]
    try:
        while True:
            for name in order:
                hl.write_preset(cfg, name)
                n = hl.read_latency(lat)
                stamp = time.strftime("%H:%M:%S")
                txt = ("not measured yet" if n is None
                       else f"{n} pixel clocks (~{n / 142.857:.3f} us)")
                print(f"[{stamp}] preset {name:<9} latency {txt}", flush=True)
                if args.cycle <= 0:
                    raise KeyboardInterrupt
                time.sleep(args.cycle)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
