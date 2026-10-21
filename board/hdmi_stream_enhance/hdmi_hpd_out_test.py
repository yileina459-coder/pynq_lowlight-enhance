#!/usr/bin/env python3
"""Toggle the HDMI-out HPD/enable GPIO and see whether anything appears.

Why this is worth testing
    The base design exposes a 1-bit output called hdmi_out_hpd, driven by an AXI GPIO
    at 0x41230000 (CONFIG.C_ALL_OUTPUTS=1):

        connect_bd_net -net hdmi_out_hpd_video_gpio_io_o \
            [get_bd_pins hdmi_out_hpd_video/gpio_io_o] [get_bd_ports hdmi_out_hpd]

    PYNQ's HDMIOutFrontend only knows about the VTC and the dynamic clock generator
    (its constructor takes exactly those two addresses), so it never writes this GPIO -
    it stays at its reset value of 0 while the pipeline runs. If that pin gates the
    output (an enable or the HPD the sink looks at), no TMDS is emitted no matter how
    correct the video path is, which matches every measurement so far: clocks locked,
    rgb2dvi out of reset, kernel streaming, capture card still on its no-signal pattern.

    sudo python3 -u hdmi_hpd_out_test.py
"""

from __future__ import annotations

import argparse
import time


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bitstream", default="enhance_hdmi.bit")
    ap.add_argument("--mode", default="1280x720")
    ap.add_argument("--hold", type=float, default=20.0)
    args = ap.parse_args(argv)

    from pynq import Overlay
    from pynq.lib.video import VideoMode

    width, height = (int(v) for v in args.mode.lower().split("x"))

    print(f"loading {args.bitstream}", flush=True)
    ol = Overlay(args.bitstream)
    video = ol.video

    # Find the GPIO that drives hdmi_out_hpd.
    names = [n for n in ol.ip_dict if "hpd" in n.lower() and "out" in n.lower()]
    print(f"candidate GPIOs: {names}", flush=True)
    gpio = None
    for name in names:
        if "hdmiin" in name.lower():
            continue
        gpio = getattr(ol, name)
        print(f"using {name} @ 0x{ol.ip_dict[name]['phys_addr']:08x}", flush=True)
        break
    if gpio is None:
        print("no hdmi_out hpd gpio in this overlay")
        return 2

    before = gpio.mmio.read(0x00)
    print(f"current value: 0x{before:08x}", flush=True)

    video.hdmi_out.configure(VideoMode(width, height, 24, 60))
    video.hdmi_out.start()
    print(f"hdmi_out running at {width}x{height}", flush=True)

    for value in (1, 0, 1):
        gpio.mmio.write(0x00, value)
        print(f"\n>>> hdmi_out_hpd = {value}  "
              f"(readback 0x{gpio.mmio.read(0x00):08x}) - watch the capture card now, "
              f"holding {args.hold:.0f}s", flush=True)
        time.sleep(args.hold)

    print("done; left the pin at 1", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
