"""Reference test: drive HDMI OUT from the STOCK overlay using its own VDMA.

Why
    Everything we know so far is ambiguous: the driver says the output is running
    (state=1, mode=1280x720), the kernel pipeline is carrying pixels (latency
    stamps move), yet the capture card only ever shows its own no-signal bars.

    The stock base.bit still has the VDMA loopback, so PYNQ can push a known frame
    out the same HDMI connector with no involvement from our design. That splits
    the problem in two:

      * colour appears  -> the board's output and the capture chain are fine, so
                          our overlay is not producing a valid output stream
      * nothing appears -> the output side of the board/cable/card is the problem,
                          independent of anything we built

    It also gives reference values for the timing/clock registers.

    sudo python3 stock_hdmi_out.py
    sudo python3 stock_hdmi_out.py --mode 720p60
    sudo python3 stock_hdmi_out.py --fps 60
"""

from __future__ import annotations

import time
import argparse

import numpy as np

STOCK = "/usr/local/share/pynq-venv/lib/python3.10/site-packages/pynq/overlays/base/base.bit"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("720p60", "1080p30", "1080p60"),
                    default="1080p30", help="HDMI output mode (default: 1080p30)")
    args = ap.parse_args()

    from pynq import MMIO, Overlay
    from pynq.lib.video import VideoMode

    print("loading stock overlay")
    ol = Overlay(STOCK)
    video = ol.video
    out = video.hdmi_out

    width, height, fps = {
        "720p60": (1280, 720, 60),
        "1080p30": (1920, 1080, 30),
        "1080p60": (1920, 1080, 60),
    }[args.mode]
    mode = VideoMode(width, height, 24, fps)
    out.configure(mode)
    # newframe() needs the VDMA write channel to be running (its frame cache is
    # created on start), so start before allocating a frame.
    out.start()
    print(f"configured {out.mode.width}x{out.mode.height} @ {fps} Hz")

    # A frame that is unmistakable: three horizontal bands.
    frame = out.newframe()
    frame[:] = 0
    h = frame.shape[0]
    frame[: h // 3] = (255, 0, 0)          # red
    frame[h // 3: 2 * h // 3] = (0, 255, 0)  # green
    frame[2 * h // 3:] = (0, 0, 255)       # blue
    print("frame prepared:", frame.shape, "-> writing to the display")
    out.writeframe(frame)

    for i in range(3):
        time.sleep(1.0)
        try:
            print(f"  state[{i}] =", out.frontend._display.state())
        except Exception as exc:            # noqa: BLE001
            print("  state read failed:", exc)

    print("\n=== reference registers (stock overlay, output running) ===")
    dc = MMIO(0x43C10000, 0x1000)
    vtc = MMIO(0x43C20000, 0x1000)
    for off, note in ((0x00, "dynclk STATUS"), (0x04, "dynclk CLK0"),
                      (0x08, "dynclk phase"), (0x0C, "dynclk CLK1")):
        print(f"  0x{off:02x} = 0x{dc.read(off):08x}   {note}")
    for off, note in ((0x00, "vtc control"), (0x04, "vtc status")):
        print(f"  0x{off:02x} = 0x{vtc.read(off):08x}   {note}")

    print()
    print("Look at the capture card: three bands (red/green/blue) means the board's")
    print("HDMI OUT works and the fault is in our overlay's output stream.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
