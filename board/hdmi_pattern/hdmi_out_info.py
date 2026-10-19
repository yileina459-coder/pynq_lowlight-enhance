"""List the video-hierarchy IP addresses and the output driver's capabilities.

The previous attempt read MMIO at addresses taken from a name pattern and hit a
SIGBUS, i.e. it touched unmapped memory. This version only *prints* what the
overlay says, and inspects the driver object, without touching registers.
"""

from __future__ import annotations

from pynq import Overlay

ol = Overlay("enhance_pattern.bit")

print("=== video related ip_dict entries ===")
for name, info in ol.ip_dict.items():
    if any(k in name.lower() for k in ("dynclk", "vtc", "vid_out", "rgb2dvi",
                                       "pixel_unpack", "hdmi_out")):
        addrs = info.get("phys_addr")
        print(f"  {name:<44} type={info.get('type')} addr={addrs if addrs is None else hex(addrs)}")

video = ol.video
out = video.hdmi_out
print("\n=== output driver ===")
print("  out:", type(out).__name__)
fe = out.frontend
print("  frontend:", type(fe).__name__)
disp = getattr(fe, "_display", None)
print("  _display:", type(disp).__name__ if disp is not None else None)
if disp is not None:
    print("  _display methods:", [m for m in dir(disp) if not m.startswith('_')][:30])
    for probe in ("frame_width", "frame_height", "mode", "clock_freq", "freq"):
        fn = getattr(disp, probe, None)
        if fn is None:
            continue
        try:
            print(f"    {probe}() ->", fn() if callable(fn) else fn)
        except Exception as exc:                    # noqa: BLE001
            print(f"    {probe}() raised {exc}")
