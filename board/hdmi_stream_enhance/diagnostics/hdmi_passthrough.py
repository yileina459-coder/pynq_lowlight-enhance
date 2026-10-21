#!/usr/bin/env python3
"""HDMI passthrough with the enhancement kernel, output mode following the input.

Why the earlier attempts showed nothing
    The capture card stayed on its no-signal pattern because the output was configured
    for 720p while the laptop was sending 1080p. ``v_axi4s_vid_out`` locks its output
    timing to the VTC and expects the incoming stream to be that same mode; a 1080p
    stream behind 720p timing produces no valid picture.

    The input mode is only knowable through ``video.hdmi_in.configure()``, which blocks
    until the PYNQ capture library has detected timing - and which also fills in
    ``video.hdmi_in.mode`` (that property reads the VDMA's configured mode, not a live
    detector, so reading it before configure() always yields None).

What this script does
    1. assert HPD so the source sees a sink
    2. configure the input (blocks until timing is detected) and read the mode
    3. configure the output to *that* mode
    4. apply a preset and report the measured pipeline latency
    5. optionally cycle presets so the effect is visible on the monitor

    sudo python3 -u hdmi_passthrough.py
    sudo python3 -u hdmi_passthrough.py --cycle 4
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
    ap.add_argument("--wait", type=float, default=60.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None:
        current = hpd.mmio.read(0x00)
        if current & 0x1 == 0:
            # Only raise HPD when it is low. Toggling it 0->1 while the source already
            # has the link up makes Windows re-enumerate, which drops TMDS for tens of
            # seconds - long enough that the input configure() below times out.
            hpd.mmio.write(0x00, 0x1)
            print("HPD raised (was low)", flush=True)
        else:
            print("HPD already asserted, left alone", flush=True)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    # Loading a bitstream resets HPD to 0, so the source re-enumerates and needs tens
    # of seconds before TMDS returns. HDMIInFrontend.start() takes the timeout as an
    # argument (configure() hardcodes 60 s), so wait in a loop instead of once.
    frontend = video.hdmi_in._hdmi
    deadline = time.monotonic() + args.wait
    in_mode = None
    while time.monotonic() < deadline and in_mode is None:
        remaining = max(5.0, deadline - time.monotonic())
        try:
            print(f"arming the capture (up to {remaining:.0f}s)...", flush=True)
            frontend.start(init_timeout=int(remaining))
            in_mode = frontend.mode
        except LookupError as exc:
            print(f"  no signal yet: {exc}", flush=True)
            time.sleep(2.0)
        except Exception as exc:                          # noqa: BLE001
            print(f"RESULT: input configure failed ({type(exc).__name__}: {exc})")
            return 2

    if in_mode is None:
        print("RESULT: no input signal detected within the timeout")
        return 2

    print(f"input detected: {in_mode.width}x{in_mode.height} "
          f"@{getattr(in_mode, 'fps', 60)} Hz", flush=True)

    out = video.hdmi_out
    out.configure(VideoMode(in_mode.width, in_mode.height, 24,
                            getattr(in_mode, "fps", 60) or 60))
    out.start()
    print(f"output configured to match: {out.mode.width}x{out.mode.height}", flush=True)

    order = [args.preset] if args.cycle <= 0 else [
        "pass", "clarity", "document", "night", "invert", "binarize", "split"]
    try:
        while True:
            for name in order:
                hl.write_preset(cfg, name)
                n = hl.read_latency(lat)
                stamp = time.strftime("%H:%M:%S")
                txt = ("not measured" if n is None
                       else f"{n} pixel clocks (~{n / 74.25:.3f} us at 720p60)")
                print(f"[{stamp}] preset {name:<9} latency {txt}", flush=True)
                if args.cycle <= 0:
                    print("holding; press Ctrl-C to stop", flush=True)
                    while True:
                        time.sleep(1.0)
                time.sleep(args.cycle)
    except KeyboardInterrupt:
        print("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
