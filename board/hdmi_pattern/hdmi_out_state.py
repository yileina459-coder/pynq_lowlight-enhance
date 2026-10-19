"""Read axi_dynclk and vtc_out through their real addresses.

Now that the addresses come from the overlay (axi_dynclk 0x43C10000, vtc_out
0x43C20000) the reads are safe. What we want to know:

  * is the pixel clock PLL locked and what frequency does it report
  * is the timing controller enabled and generating
  * what does the PYNQ display driver think its state is

    sudo python3 hdmi_out_state.py
"""

from __future__ import annotations

import time

from pynq import MMIO, Overlay
from pynq.lib.video import VideoMode

DYNCLK = 0x43C10000
VTC_OUT = 0x43C20000


def safe_read(mmio, off):
    try:
        return f"0x{mmio.read(off):08x}"
    except Exception as exc:                        # noqa: BLE001
        return f"<{exc.__class__.__name__}>"


def main() -> int:
    ol = Overlay("enhance_pattern.bit")
    video = ol.video
    out = video.hdmi_out
    disp = out.frontend._display

    def report(tag: str) -> None:
        print(f"--- {tag} ---")
        for probe in ("mode", "frame_width", "frame_height", "state"):
            fn = getattr(disp, probe, None)
            if fn is None:
                continue
            try:
                print(f"  _display.{probe}() = {fn()}")
            except Exception as exc:                # noqa: BLE001
                print(f"  _display.{probe}() raised {exc}")

    report("after load (no configure)")

    print("\n=== axi_dynclk registers before configure ===")
    dc = MMIO(DYNCLK, 0x1000)
    for off, note in ((0x00, "STATUS (bit0 PLL locked)"),
                      (0x04, "CLK0 frequency Hz"),
                      (0x08, "CLK0 phase mdeg"),
                      (0x0C, "CLK1 frequency Hz")):
        print(f"  0x{off:02x} = {safe_read(dc, off)}   {note}")

    mode = VideoMode(1280, 720, 24, 60)
    out.configure(mode)
    time.sleep(0.3)
    report("after configure(1280x720)")

    out.start()
    time.sleep(0.5)
    report("after start()")

    print("\n=== axi_dynclk after start ===")
    for off, note in ((0x00, "STATUS (bit0 PLL locked)"),
                      (0x04, "CLK0 frequency Hz"),
                      (0x08, "CLK0 phase mdeg"),
                      (0x0C, "CLK1 frequency Hz")):
        print(f"  0x{off:02x} = {safe_read(dc, off)}   {note}")

    print("\n=== vtc_out registers ===")
    vtc = MMIO(VTC_OUT, 0x1000)
    for off, note in ((0x00, "control (bit0 enable, bit1 generate)"),
                      (0x04, "status"),
                      (0x08, "irq status"),
                      (0x0C, "irq enable")):
        print(f"  0x{off:02x} = {safe_read(vtc, off)}   {note}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
