#!/usr/bin/env python3
"""Is the HDMI IN hot-plug-detect pin holding the source back?

Reasoning
    PYNQ's base design exposes `hdmi_in_hpd` as a pin driven by an AXI GPIO
    (axi_gpio_hdmiin). A source will not send TMDS - and Windows will not even read
    the EDID - until the sink asserts HPD. If software never sets it, the laptop
    sees "nothing plugged in", which is exactly the symptom: no second display in
    Windows and `mode: None` on the board, with both our overlay and the stock one.

What this does
    Loads the stock base overlay, lists every GPIO-ish IP, asserts HPD on the one
    that looks like the HDMI-in GPIO, then polls hdmi_in.mode.

    sudo python3 hdmi_hpd_probe.py
"""

from __future__ import annotations

import time

STOCK = "/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit"


def main() -> int:
    from pynq import Overlay

    ol = Overlay(STOCK)
    print(f"stock overlay loaded, IPs: {len(ol.ip_dict)}")

    candidates = [n for n in ol.ip_dict if "gpio" in n.lower()]
    print("gpio-like IPs:", candidates)
    print("video hierarchy:", hasattr(ol, "video"))

    print("mode before HPD:", ol.video.hdmi_in.mode)

    # Assert HPD on every gpio whose name mentions hdmi; harmless for the others.
    touched = []
    for name in candidates:
        if "hdmi" not in name.lower():
            continue
        dev = getattr(ol, name, None)
        if dev is None or not hasattr(dev, "mmio"):
            continue
        try:
            before = dev.mmio.read(0x00)
            dev.mmio.write(0x00, 0x1)          # channel 1 data <- 1
            after = dev.mmio.read(0x00)
            touched.append((name, before, after))
            print(f"  {name}: 0x{before:08x} -> 0x{after:08x} (HPD asserted)")
        except Exception as exc:                # noqa: BLE001
            print(f"  {name}: could not write ({exc})")

    if not touched:
        print("no hdmi gpio found - HPD may already be tied high in this design")
        # try the video-in helper if it exists
        start = getattr(ol.video.hdmi_in, "start", None)
        if callable(start):
            print("calling video.hdmi_in.start()")
            start()

    print()
    for i in range(15):
        mode = ol.video.hdmi_in.mode
        print(f"  [{i}] mode: {mode}")
        if mode is not None:
            print(f"RESULT: SOURCE LOCKED -> {mode.width}x{mode.height} @{mode.frame_rate} Hz")
            return 0
        time.sleep(1.0)

    print("RESULT: still no input mode")
    print("  HPD was asserted (if a gpio was found) and the source still does not")
    print("  respond, so the next suspects are the cable/port and the source itself.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
