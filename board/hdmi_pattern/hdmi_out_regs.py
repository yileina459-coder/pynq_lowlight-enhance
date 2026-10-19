"""Read the HDMI output clock generator and timing controller registers.

Guessing has cost enough time on this. The two things that must be true before
TMDS leaves the board are:

  * axi_dynclk PLL locked and producing the pixel clock for 720p
  * vtc_out generating timing (not held in reset / not disabled)

Both are memory-mapped in the video hierarchy, so they can just be read.

    sudo python3 hdmi_out_regs.py
"""

from __future__ import annotations

import time

import pattern_demo as pd  # noqa: F401  (keeps the import path working)


def dump(label: str, mmio, offsets) -> None:
    print(f"=== {label} ===")
    for off, note in offsets:
        try:
            print(f"  0x{off:02x} = 0x{mmio.read(off):08x}   {note}")
        except Exception as exc:                    # noqa: BLE001
            print(f"  0x{off:02x} unreadable ({exc})")


def main() -> int:
    from pynq import Overlay
    from pynq.lib.video import VideoMode

    ol = Overlay("enhance_pattern.bit")
    video = ol.video

    # Locate the frontend devices from the IP dictionary, not by guessing names.
    interesting = [n for n in ol.ip_dict
                   if any(k in n.lower() for k in ("dynclk", "vtc", "vid_out", "rgb2dvi"))]
    print("video-related IPs:")
    for n in interesting:
        print(f"  {n}  @ {ol.ip_dict[n].get('phys_addr', 0):#x}")

    out = video.hdmi_out
    print("\nfrontend methods:", [m for m in dir(out.frontend)
                                  if not m.startswith('_')][:20])

    mode = VideoMode(1280, 720, 24, 60)
    out.configure(mode)
    out.start()
    time.sleep(0.5)

    for name in interesting:
        if "dynclk" in name.lower():
            dev = getattr(ol, name.replace("/", "_"), None)
            if dev is None:
                # hierarchies are not attributes; use the mmio from the ip dict
                import pynq
                dev = pynq.MMIO(ol.ip_dict[name]["phys_addr"], 0x1000)
            dump(name, dev.mmio if hasattr(dev, "mmio") else dev,
                 [(0x00, "STATUS (bit0 = PLL locked)"),
                  (0x04, "CLK0 frequency, Hz"),
                  (0x08, "CLK0 phase, mdeg"),
                  (0x0C, "CLK1 frequency, Hz")])

    for name in interesting:
        if "vtc" in name.lower():
            import pynq
            dev = pynq.MMIO(ol.ip_dict[name]["phys_addr"], 0x1000)
            dump(name, dev,
                 [(0x00, "VTC control (enable bit0, gen bit1)"),
                  (0x04, "VTC status"),
                  (0x08, "VTC interrupt status"),
                  (0x0C, "VTC interrupt enable")])

    # what the driver believes
    print("\ndriver view: hdmi_out.mode =", out.mode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
