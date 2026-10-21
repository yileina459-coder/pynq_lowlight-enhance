#!/usr/bin/env python3
"""Keep the HDMI output locked to whatever mode the input is sending.

The core problem this solves
    Loading a bitstream resets HPD, so Windows re-enumerates and usually falls back
    to 1920x1080 whatever was chosen before. This overlay is configured for 720p60:
    both dvi2rgb and rgb2dvi use kClkRange=2 (MULT_F=10), giving a 742.5 MHz VCO at
    the 74.25 MHz pixel clock. 1080p asks for 1485 MHz and is outside the Artix-7 -1
    MMCM range of 600-1200 MHz.

    So: load the bitstream exactly once, then sit in a loop that watches the detected
    input mode and reconfigures the output whenever it changes. Change the display
    resolution in Windows and the FPGA follows within a second, without another
    bitstream load.

    sudo python3 -u hdmi_follow.py --cycle 5
"""

from __future__ import annotations

import argparse
import time

import hdmi_live as hl


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--cycle", type=float, default=5.0)
    ap.add_argument("--arm", type=int, default=300, help="seconds to wait for input")
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video
    out = video.hdmi_out
    frontend = video.hdmi_in._hdmi

    hpd = hl.find(ol, "gpio_hdmiin")
    if hpd is not None and hpd.mmio.read(0x00) & 0x1 == 0:
        hpd.mmio.write(0x00, 0x1)
        print("HPD raised", flush=True)

    cfg = hl.find(ol, "gpio_enh_cfg")
    lat = hl.find(ol, "gpio_enh_lat")

    deadline = time.monotonic() + args.arm
    armed = False
    while time.monotonic() < deadline and not armed:
        try:
            frontend.start(init_timeout=max(5, int(deadline - time.monotonic())))
            armed = True
        except LookupError as exc:
            print(f"  waiting for a signal: {exc}", flush=True)
            time.sleep(2.0)

    if not armed:
        print("RESULT: no input signal")
        return 2

    current = None
    presets = ["pass", "clarity", "document", "night", "invert", "binarize", "split"]
    idx = 0
    last_switch = time.monotonic()

    while True:
        try:
            m = frontend.mode
            detected = (m.width, m.height, getattr(m, "fps", 60) or 60)
        except Exception as exc:                          # noqa: BLE001
            print(f"  mode read failed ({exc}); re-arming", flush=True)
            try:
                frontend.start(init_timeout=20)
            except Exception as exc2:                     # noqa: BLE001
                print(f"  re-arm failed: {exc2}", flush=True)
            time.sleep(2.0)
            continue

        if detected != current and detected[0] and detected[1]:
            print(f"input is now {detected[0]}x{detected[1]}@{detected[2]} "
                  f"-> configuring the output to match", flush=True)
            try:
                out.stop()
            except Exception:                             # noqa: BLE001
                pass
            try:
                out.configure(VideoMode(detected[0], detected[1], 24, detected[2]))
                out.start()
                current = detected
                # Both HDMI clock converters use kClkRange=2 (MULT_F = 10).
                pclk = { (640, 480): 25.175, (800, 600): 40.0,
                         (1280, 720): 74.25, (1280, 1024): 108.0,
                         (1920, 1080): 148.5 }.get(detected[:2], 148.5)
                vco = 10 * pclk
                print(f"  output running at {detected[0]}x{detected[1]}, "
                      f"VCO = {vco:.0f} MHz "
                      f"({'in range' if 600 <= vco <= 1200 else 'OUT OF MMCM RANGE'})",
                      flush=True)
                print(f"  pixel clock {pclk:.2f} MHz, 5x bit clock {5 * pclk:.1f} MHz",
                      flush=True)
            except Exception as exc:                      # noqa: BLE001
                print(f"  output configure failed: {exc}", flush=True)

        if args.cycle > 0 and time.monotonic() - last_switch > args.cycle:
            name = presets[idx % len(presets)]
            idx += 1
            last_switch = time.monotonic()
            hl.write_preset(cfg, name)
            n = hl.read_latency(lat)
            txt = "not measured" if n is None else f"{n} pixel clocks"
            print(f"[{time.strftime('%H:%M:%S')}] preset {name:<9} latency {txt}",
                  flush=True)

        time.sleep(0.5)


if __name__ == "__main__":
    raise SystemExit(main())
