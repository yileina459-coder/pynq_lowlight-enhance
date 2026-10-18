#!/usr/bin/env python3
"""Load the HDMI overlay and report what binds, without any display attached.

Loading is the step that carries the version risk (Vivado 2026.1 output on a
PYNQ 3.1.1 image); whether a picture appears needs a monitor or capture card, but
"does the overlay load and does PYNQ bind the video subsystem" does not.

    sudo python3 check_hdmi_overlay.py
"""

from __future__ import annotations


def main() -> int:
    import pynq
    from pynq import Overlay

    print("PYNQ", pynq.__version__)
    print("loading sobel_hdmi.bit ...")
    ol = Overlay("sobel_hdmi.bit")
    print(f"  IPs in design: {len(ol.ip_dict)}")

    names = sorted(ol.ip_dict)
    # sobel_0 deliberately does not appear in ip_dict: the streaming kernel has
    # no AXI-Lite registers, so it never enters the address map. Its presence is
    # proven by the hardware behaviour (the picture), not by this list.
    print(f"  video hierarchy bound: {hasattr(ol, 'video')}")

    if not hasattr(ol, "video"):
        print("FAIL: pynq.lib.video did not bind - the bit/hwh pair may not match")
        return 1

    video = ol.video
    hdmi_in = video.hdmi_in
    hdmi_out = video.hdmi_out
    print(f"  hdmi_in: {hdmi_in}")
    print(f"  hdmi_out: {hdmi_out}")
    print(f"  detected input mode: {hdmi_in.mode}  (None means no source attached)")

    print("RESULT: HDMI overlay loads and the video subsystem binds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
