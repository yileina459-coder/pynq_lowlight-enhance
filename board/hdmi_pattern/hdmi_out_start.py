"""Start the HDMI output properly and see whether TMDS appears.

Root cause of "the capture card shows bars but nothing changes": those bars were
the capture card's own no-signal fallback. PYNQ's HDMI output frontend needs an
explicit start() after the mode is set -

    self.start = self._display.start
    \"\"\"Start the HDMI output - requires the that mode is already set\"\"\"

configure() only sets the mode, so the VTC and pixel clock were programmed but the
output was never started.

    sudo python3 hdmi_out_start.py
"""

from __future__ import annotations

import time

import pattern_demo as pd


def main() -> int:
    from pynq import Overlay
    from pynq.lib.video import VideoMode

    ol = Overlay("enhance_pattern.bit")
    video = ol.video
    out = video.hdmi_out

    mode = VideoMode(1280, 720, 24, 60)
    out.configure(mode)
    print(f"mode set to {mode.width}x{mode.height}@{mode.fps}")

    # This is the step that was missing.
    out.start()
    print("hdmi_out.start() called")

    cfg = pd.find(ol, "gpio_enh_cfg")
    lat = pd.find(ol, "gpio_enh_lat")

    for name in ("pass", "document", "invert", "binarize", "split"):
        lo, hi = pd.pack(pd.PRESETS[name])
        cfg.mmio.write(0x00, lo)
        cfg.mmio.write(0x08, hi)
        time.sleep(1.5)
        a, b = lat.mmio.read(0x00), lat.mmio.read(0x08)
        n = (b - a) & 0xFFFFFFFF
        print(f"  preset {name:<9} latency {n} clocks (~{n / 142.857:.3f} us)")

    print()
    print("look at the capture card now: it should show colour bars that CHANGE")
    print("with each preset. If the picture appeared only after start(), that was it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
