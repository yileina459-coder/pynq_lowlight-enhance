"""Compare the stream width our kernel emits with what the video hierarchy expects.

The HDMI output hierarchy is  VDMA -> pixel_unpack -> v_axi4s_vid_out -> rgb2dvi.
pixel_unpack is fed 32-bit words (padded RGB) and emits 24-bit pixels, so the
hierarchy's input port is normally 32 bits wide. Our HLS kernel emits 24-bit pixels.

If the two disagree, the connection still validates (Vivado happily matches a 24-bit
producer to a 32-bit consumer by zero-extending), but every word pixel_unpack reads is
then interpreted with the wrong byte layout - which yields no valid SOF/EOL and no
TMDS at all. That matches the observation exactly: data flows through the kernel
(latency reads 21 clocks) yet the output stage emits nothing.

This script reads the .hwh (the hardware handoff PYNQ also parses) and prints the
width of every relevant stream port.
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

HWH = "board/hdmi_stream_enhance/enhance_hdmi.hwh"
INTEREST = ("in_stream", "out_stream", "s_axis", "m_axis", "TDATA", "TUSER", "TLAST")


def walk(path: str) -> int:
    tree = ET.parse(path)
    root = tree.getroot()

    print(f"{path}")
    print("=" * 78)
    found = 0
    for module in root.iter("MODULE"):
        inst = module.get("INSTANCE") or module.get("FULLNAME") or "?"
        ports = []
        for port in module.iter("PORT"):
            name = port.get("NAME", "")
            direction = port.get("DIR", "")
            left = port.get("LEFT", "")
            right = port.get("RIGHT", "")
            if not any(key in name.upper() for key in INTEREST):
                continue
            try:
                width = abs(int(left) - int(right)) + 1
            except (TypeError, ValueError):
                width = "?"
            ports.append((name, direction, width))
        if ports:
            found += 1
            print(f"\n{inst}")
            for name, direction, width in sorted(ports):
                print(f"   {direction:3} {name:28} width={width}")

    # The hierarchy's input port is what our kernel drives - report it explicitly.
    print()
    print("=" * 78)
    for module in root.iter("MODULE"):
        inst = module.get("INSTANCE", "")
        if "hdmi_out" in inst or "pixel_unpack" in inst or "enhance_0" in inst:
            for port in module.iter("PORT"):
                name = port.get("NAME", "")
                if name.upper().endswith("TDATA") and "stream" in name.lower():
                    left, right = port.get("LEFT"), port.get("RIGHT")
                    try:
                        width = abs(int(left) - int(right)) + 1
                    except (TypeError, ValueError):
                        width = "?"
                    print(f"{inst}.{name}: TDATA width = {width}")
    return found


if __name__ == "__main__":
    sys.exit(0 if walk(HWH) else 1)
